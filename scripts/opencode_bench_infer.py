"""GTX 1650 inference benchmark harness (local only, no training, no orders).

Given a checkpoint dir (config + weights), measures on this host:
  - load time (ms)
  - per-window latency ms for batch 1/8/32 (median over N runs post-warmup)
  - peak VRAM MB (torch.cuda.max_memory_allocated, reset first; 0.0 on CPU)
  - throughput windows/sec per batch size
  - correctness parity: max abs diff vs --ref prediction file if provided,
    else self-consistency reload check (fresh instance, same weights, same input)

Supported checkpoint layouts:
  A) engineered_multiframe_mlp_v1 (e.g. artifacts/checkpoints/mlp_20260905_v2/):
     metadata.json + model.safetensors
  B) generic tiny_mlp (synthetic/test + future tiny heads):
     bench_config.json {"arch":"tiny_mlp","in_features":I,"hidden":H,"out":O}
     + model.safetensors (safetensors state_dict) or model.pt (torch.save state_dict)

CLI: --ckpt <dir> --out <report.json> [--ref <preds.npy|npz|json>]
     [--runs 200] [--warmup 20] [--device auto|cuda|cpu] [--tol 1e-5] [--force]

NOTE: torch is imported BEFORE pandas on Windows (c10.dll load order).
This module has NO pandas dependency at all.
"""

from __future__ import annotations

import argparse
import datetime
import json
import statistics
import subprocess
import time
from pathlib import Path

import torch  # must precede any pandas import on Windows
from torch import nn


HARNESS_VERSION = "opencode_bench_infer v1"
BATCH_SIZES = (1, 8, 32)


# --- model definitions (inline so the harness never depends on src layout) ---

class _MultiHorizonMLP(nn.Module):
    """Verbatim arch of agentic_alpha_lab.models.supervised.MultiHorizonMLP."""

    def __init__(self, features: int, hidden: int, horizons: int):
        super().__init__()
        self.horizons = horizons
        self.network = nn.Sequential(nn.Linear(features, hidden), nn.GELU(),
                                     nn.Linear(hidden, hidden), nn.GELU(),
                                     nn.Linear(hidden, horizons * 6))

    def forward(self, inputs: torch.Tensor):
        outputs = self.network(inputs).reshape(-1, self.horizons, 6)
        center = outputs[..., 4]
        quantiles = torch.stack([center - nn.functional.softplus(outputs[..., 3]), center,
                                 center + nn.functional.softplus(outputs[..., 5])], dim=-1)
        return outputs[..., :3], quantiles


class _TinyMLP(nn.Module):
    """Generic tiny head for synthetic tests: Linear->GELU->Linear."""

    def __init__(self, in_features: int, hidden: int, out: int):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(in_features, hidden), nn.GELU(),
                                 nn.Linear(hidden, out))

    def forward(self, inputs: torch.Tensor):
        return self.net(inputs)


def _first_output(out):
    return out[0] if isinstance(out, (tuple, list)) else out


def _resolve_device(name: str) -> torch.device:
    if name == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("--device cuda requested but torch.cuda unavailable")
        return torch.device("cuda")
    if name == "cpu":
        return torch.device("cpu")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def load_checkpoint(ckpt: Path, device: torch.device):
    """Build model + load weights. Returns (model, info dict, weights_path)."""
    ckpt = Path(ckpt)
    if not ckpt.is_dir():
        raise FileNotFoundError(f"ckpt dir not found: {ckpt}")
    meta_path = ckpt / "metadata.json"
    cfg_path = ckpt / "bench_config.json"
    st_path = ckpt / "model.safetensors"
    pt_path = ckpt / "model.pt"

    if meta_path.exists() and st_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        mtype = str(meta.get("model_type", ""))
        if mtype.startswith("engineered_multiframe_mlp_v1"):
            features = meta["features"]
            hidden = meta["config"]["model"]["hidden"]
            horizons = meta["config"]["horizons"]
            model = _MultiHorizonMLP(len(features), hidden, len(horizons))
            from safetensors.torch import load_file
            model.load_state_dict(load_file(str(st_path), device="cpu"))
            info = {"arch": mtype, "in_features": len(features), "hidden": hidden,
                    "horizons": horizons, "temperature": meta.get("temperature"),
                    "source": "metadata.json+model.safetensors"}
            return model.to(device).eval(), info, st_path
        raise ValueError(f"unsupported metadata model_type: {mtype!r} in {meta_path}")

    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        if cfg.get("arch") != "tiny_mlp":
            raise ValueError(f"unsupported bench_config arch: {cfg.get('arch')!r}")
        model = _TinyMLP(int(cfg["in_features"]), int(cfg["hidden"]), int(cfg["out"]))
        if st_path.exists():
            from safetensors.torch import load_file
            model.load_state_dict(load_file(str(st_path), device="cpu"))
            weights = st_path
        elif pt_path.exists():
            model.load_state_dict(torch.load(str(pt_path), map_location="cpu", weights_only=True))
            weights = pt_path
        else:
            raise FileNotFoundError(f"no weights (model.safetensors|model.pt) in {ckpt}")
        info = {"arch": "tiny_mlp", "in_features": int(cfg["in_features"]),
                "hidden": int(cfg["hidden"]), "out": int(cfg["out"]),
                "source": f"bench_config.json+{weights.name}"}
        return model.to(device).eval(), info, weights

    raise FileNotFoundError(
        f"unrecognized ckpt layout in {ckpt} (need metadata.json+model.safetensors "
        f"or bench_config.json+weights)")


def _sync(device: torch.device):
    if device.type == "cuda":
        torch.cuda.synchronize()


def measure_latency(model, in_features: int, device: torch.device,
                    runs: int, warmup: int, seed: int):
    """Median/p95 per-window latency ms + throughput for batch 1/8/32."""
    lat, thr = {}, {}
    g = torch.Generator(device=device.type).manual_seed(seed)
    with torch.no_grad():
        for b in BATCH_SIZES:
            x = torch.randn(b, in_features, generator=g,
                            dtype=torch.float32, device=device)
            for _ in range(warmup):
                _first_output(model(x))
            _sync(device)
            times = []
            for _ in range(runs):
                t0 = time.perf_counter()
                _first_output(model(x))
                _sync(device)
                times.append((time.perf_counter() - t0) * 1000.0)
            med = statistics.median(times)
            ordered = sorted(times)
            lat[str(b)] = {"median_ms": med,
                           "p95_ms": ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))],
                           "runs": runs, "warmup": warmup}
            thr[str(b)] = b * 1000.0 / med if med > 0 else 0.0
    return lat, thr


def measure_vram(model, in_features: int, device: torch.device, seed: int):
    if device.type != "cuda":
        return 0.0, "cpu device: no CUDA memory"
    torch.cuda.reset_peak_memory_stats(device)
    g = torch.Generator(device="cpu").manual_seed(seed)
    with torch.no_grad():
        for b in BATCH_SIZES:
            x = torch.randn(b, in_features, generator=g,
                            dtype=torch.float32).to(device)
            _first_output(model(x))
    _sync(device)
    peak = float(torch.cuda.max_memory_allocated(device)) / (1024.0 ** 2)
    return peak, "torch.cuda.max_memory_allocated after reset, batch 1/8/32 forward"


def self_consistency(model, info, weights_path: Path, device: torch.device, seed: int):
    """Reload same weights into a fresh instance; max abs diff on fixed input."""
    if info["arch"].startswith("engineered_multiframe_mlp"):
        fresh = _MultiHorizonMLP(info["in_features"], info["hidden"], len(info["horizons"]))
    else:
        fresh = _TinyMLP(info["in_features"], info["hidden"], info["out"])
    if weights_path.suffix == ".pt":
        fresh.load_state_dict(torch.load(str(weights_path), map_location="cpu", weights_only=True))
    else:
        from safetensors.torch import load_file
        fresh.load_state_dict(load_file(str(weights_path), device="cpu"))
    fresh = fresh.to(device).eval()
    g = torch.Generator(device="cpu").manual_seed(seed)
    x = torch.randn(32, info["in_features"], generator=g,
                    dtype=torch.float32).to(device)
    with torch.no_grad():
        a = _first_output(model(x)).float().cpu()
        b = _first_output(fresh(x)).float().cpu()
    return float((a - b).abs().max())


def reference_parity(model, info, ref_path: Path, device: torch.device, seed: int):
    """Compare model output on deterministic input vs reference prediction file."""
    rp = Path(ref_path)
    if rp.suffix == ".npy":
        import numpy as np
        ref = np.load(str(rp))
    elif rp.suffix == ".npz":
        import numpy as np
        z = np.load(str(rp))
        ref = z["predictions"] if "predictions" in z else z[z.files[0]]
    elif rp.suffix == ".json":
        payload = json.loads(rp.read_text(encoding="utf-8"))
        import numpy as np
        ref = np.asarray(payload["predictions"] if isinstance(payload, dict) else payload,
                         dtype=np.float64)
    else:
        raise ValueError(f"unsupported ref format: {rp.suffix} (use .npy/.npz/.json)")
    import numpy as np
    ref = np.asarray(ref, dtype=np.float64)
    n = int(ref.shape[0])
    g = torch.Generator(device="cpu").manual_seed(seed)
    x = torch.randn(n, info["in_features"], generator=g,
                    dtype=torch.float32).to(device)
    with torch.no_grad():
        got = _first_output(model(x)).float().cpu().numpy().astype(np.float64)
    if got.shape != ref.shape:
        # try flattened comparison only when element counts match
        if got.size != ref.size:
            return None, (f"shape mismatch: model {tuple(got.shape)} vs "
                          f"ref {tuple(ref.shape)} (elements {got.size} vs {ref.size})")
        got, ref = got.reshape(-1), ref.reshape(-1)
        note = f"flattened compare (model {tuple(got.shape)} vs ref {tuple(ref.shape)})"
    else:
        note = f"exact-shape compare {tuple(ref.shape)}"
    return float(np.abs(got - ref).max()), note


def _git_sha() -> str:
    try:
        p = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                           text=True, timeout=15)
        return p.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def run_bench(ckpt, out, ref=None, runs=200, warmup=20,
              device_name="auto", tol=1e-5, seed=0, force=False):
    ckpt, out = Path(ckpt), Path(out)
    if out.exists() and not force:
        raise FileExistsError(f"refusing to overwrite existing {out} (pass --force)")
    device = _resolve_device(device_name)
    t0 = time.perf_counter()
    model, info, weights = load_checkpoint(ckpt, device)
    _sync(device)
    load_ms = (time.perf_counter() - t0) * 1000.0
    params = sum(p.numel() for p in model.parameters())

    lat, thr = measure_latency(model, info["in_features"], device, runs, warmup, seed)
    vram_mb, vram_note = measure_vram(model, info["in_features"], device, seed)

    if ref is not None:
        diff, note = reference_parity(model, info, ref, device, seed)
        if diff is None:
            parity = {"mode": "reference", "ref": str(ref), "max_abs_diff": None,
                      "tol": tol, "pass": False, "note": note}
        else:
            parity = {"mode": "reference", "ref": str(ref), "max_abs_diff": diff,
                      "tol": tol, "pass": bool(diff <= tol), "note": note}
    else:
        diff = self_consistency(model, info, weights, device, seed)
        parity = {"mode": "reload", "ref": None, "max_abs_diff": diff,
                  "tol": tol, "pass": bool(diff <= tol),
                  "note": "fresh instance + same weights + fixed seed-0 input (32 windows)"}

    report = {
        "harness": HARNESS_VERSION,
        "ckpt": str(ckpt), "weights": weights.name,
        "device": str(device),
        "cuda_available": torch.cuda.is_available(),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "torch_version": torch.__version__,
        "arch": info["arch"], "in_features": info["in_features"],
        "params": params, "precision": "float32",
        "load_ms": load_ms,
        "latency_ms": lat, "throughput_wps": thr,
        "vram_peak_mb": vram_mb, "vram_note": vram_note,
        "parity": parity,
        "runs": runs, "warmup": warmup, "seed": seed,
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "git_sha": _git_sha(),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description="Benchmark inference latency/VRAM/parity (local only)")
    ap.add_argument("--ckpt", required=True, help="checkpoint dir")
    ap.add_argument("--out", required=True, help="report JSON path (new file unless --force)")
    ap.add_argument("--ref", default=None, help="reference prediction file (.npy/.npz/.json)")
    ap.add_argument("--runs", type=int, default=200)
    ap.add_argument("--warmup", type=int, default=20)
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    ap.add_argument("--tol", type=float, default=1e-5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    rep = run_bench(a.ckpt, a.out, a.ref, a.runs, a.warmup, a.device, a.tol, a.seed, a.force)
    print(json.dumps({"out": str(a.out), "device": rep["device"],
                      "load_ms": rep["load_ms"], "latency_ms": rep["latency_ms"],
                      "vram_peak_mb": rep["vram_peak_mb"], "parity": rep["parity"]}, indent=2))


if __name__ == "__main__":
    main()
