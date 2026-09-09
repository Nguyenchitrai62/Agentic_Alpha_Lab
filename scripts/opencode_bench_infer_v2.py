"""GTX 1650 inference benchmark harness v2 (local only, no training, no orders).

v2 = v1 (scripts/opencode_bench_infer.py, UNCHANGED) + loader do cho arch moi:
  C) rankonly_ssm_v55 (v55c: Selective-SSM + 1 rank head, 597409 params):
     bench_config.json {"arch":"rankonly_ssm_v55", ...} + model.safetensors
     (safetensors state_dict cua RankOnlySSM). Model class TAI DUNG tu
     scripts/opencode_r17b_rankonly_model.py (khong duplicate arch);
     candidates dung lai tu dataset cfg grid (cung builder nhu train).

Inputs kep: sequence [b,5,128,6] + flat [b,133] (float32, seed-co-dinh).
Do: load_ms; latency ms/window batch 1/8/32 (median 200 runs, warmup 20);
VRAM peak (max_memory_allocated, reset first); throughput wps;
parity reload self-consistency (fresh instance + same weights + fixed input).

CLI: --ckpt <dir> --out <report.json> [--runs 200] [--warmup 20]
     [--device auto|cuda|cpu] [--tol 1e-5] [--seed 0] [--force]

NOTE: torch import truoc moi thu (c10.dll load order tren Windows).
"""

from __future__ import annotations

import argparse
import datetime
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

import torch  # must precede any pandas import on Windows

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

HARNESS_VERSION = "opencode_bench_infer v2 (+rankonly_ssm_v55)"
BATCH_SIZES = (1, 8, 32)
SEQ_SHAPE = (5, 128, 6)
N_FLAT = 133


def _git_sha() -> str:
    try:
        p = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                           text=True, timeout=15)
        return p.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _resolve_device(name: str) -> torch.device:
    if name == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("--device cuda requested but torch.cuda unavailable")
        return torch.device("cuda")
    if name == "cpu":
        return torch.device("cpu")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _sync(device: torch.device):
    if device.type == "cuda":
        torch.cuda.synchronize()


def build_rankonly_model():
    """Dung lai train builder: plan dims + candidates tu dataset cfg grid."""
    import numpy as np
    from opencode_r17b_rankonly_model import RankOnlySSM
    plan = json.loads((ROOT / "configs/opencode_v80_v55c.json").read_text(encoding="utf-8"))
    cfg = json.loads((ROOT / plan["dataset"] / "config.json").read_text(encoding="utf-8"))
    candidates = np.asarray(
        [[s, e, *b, d] for s in (1, -1) for e in cfg["entry_atr_5m"]
         for b in cfg["brackets_atr_4h"] for d in cfg["holding_days"]], np.float32)
    if candidates.shape != (16, 6):
        raise ValueError("Unsupported candidate schema")
    net = dict(plan["architecture"].get("frame_encoder", {}))
    return RankOnlySSM(
        candidates, n_flat=N_FLAT,
        frame_dim=net.get("d_model", 64), frame_state=net.get("d_state", 16),
        frame_layers=net.get("layers", 2),
        cross_state=plan["architecture"].get("cross_frame", {}).get("d_state", 16),
        dropout=plan["architecture"].get("dropout", 0.1))


def load_checkpoint(ckpt: Path, device: torch.device):
    ckpt = Path(ckpt)
    if not ckpt.is_dir():
        raise FileNotFoundError(f"ckpt dir not found: {ckpt}")
    cfg_path = ckpt / "bench_config.json"
    st_path = ckpt / "model.safetensors"
    if not (cfg_path.exists() and st_path.exists()):
        raise FileNotFoundError(f"need bench_config.json+model.safetensors in {ckpt}")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    if cfg.get("arch") != "rankonly_ssm_v55":
        raise ValueError(f"v2 harness chi ho tro rankonly_ssm_v55, got {cfg.get('arch')!r} "
                         f"(dung v1 cho mlp/tiny_mlp)")
    from safetensors.torch import load_file
    model = build_rankonly_model()
    model.load_state_dict(load_file(str(st_path), device="cpu"))
    model.to(device).eval()
    info = {"arch": "rankonly_ssm_v55", "inputs": {"sequence": list(SEQ_SHAPE), "flat": N_FLAT},
            "source": "bench_config.json+model.safetensors (RankOnlySSM tai dung train module)"}
    return model, info, st_path


def _rand_inputs(b: int, device: torch.device, seed: int):
    g = torch.Generator(device="cpu").manual_seed(seed + b)
    seq = torch.randn(b, *SEQ_SHAPE, generator=g, dtype=torch.float32).to(device)
    flat = torch.randn(b, N_FLAT, generator=g, dtype=torch.float32).to(device)
    return seq, flat


def measure_latency(model, device, runs, warmup, seed):
    lat, thr = {}, {}
    with torch.no_grad():
        for b in BATCH_SIZES:
            seq, flat = _rand_inputs(b, device, seed)
            for _ in range(warmup):
                model(seq, flat)
            _sync(device)
            times = []
            for _ in range(runs):
                t0 = time.perf_counter()
                model(seq, flat)
                _sync(device)
                times.append((time.perf_counter() - t0) * 1000.0)
            med = statistics.median(times)
            ordered = sorted(times)
            lat[str(b)] = {"median_ms": med,
                           "p95_ms": ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))],
                           "runs": runs, "warmup": warmup}
            thr[str(b)] = b * 1000.0 / med if med > 0 else 0.0
    return lat, thr


def measure_vram(model, device, seed):
    if device.type != "cuda":
        return 0.0, "cpu device: no CUDA memory"
    torch.cuda.reset_peak_memory_stats(device)
    with torch.no_grad():
        for b in BATCH_SIZES:
            seq, flat = _rand_inputs(b, device, seed)
            model(seq, flat)
    _sync(device)
    peak = float(torch.cuda.max_memory_allocated(device)) / (1024.0 ** 2)
    return peak, "torch.cuda.max_memory_allocated after reset, batch 1/8/32 forward (seq+flat)"


def self_consistency(model, weights_path: Path, device, seed):
    from safetensors.torch import load_file
    fresh = build_rankonly_model()
    fresh.load_state_dict(load_file(str(weights_path), device="cpu"))
    fresh = fresh.to(device).eval()
    seq, flat = _rand_inputs(32, device, seed)
    with torch.no_grad():
        a = model(seq, flat).float().cpu()
        b = fresh(seq, flat).float().cpu()
    return float((a - b).abs().max())


def run_bench(ckpt, out, runs=200, warmup=20, device_name="auto", tol=1e-5, seed=0, force=False):
    ckpt, out = Path(ckpt), Path(out)
    if out.exists() and not force:
        raise FileExistsError(f"refusing to overwrite existing {out} (pass --force)")
    device = _resolve_device(device_name)
    t0 = time.perf_counter()
    model, info, weights = load_checkpoint(ckpt, device)
    _sync(device)
    load_ms = (time.perf_counter() - t0) * 1000.0
    params = sum(p.numel() for p in model.parameters())
    lat, thr = measure_latency(model, device, runs, warmup, seed)
    vram_mb, vram_note = measure_vram(model, device, seed)
    diff = self_consistency(model, weights, device, seed)
    report = {
        "harness": HARNESS_VERSION,
        "ckpt": str(ckpt), "weights": weights.name,
        "device": str(device),
        "cuda_available": torch.cuda.is_available(),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "torch_version": torch.__version__,
        "arch": info["arch"], "inputs": info["inputs"],
        "params": params, "precision": "float32",
        "load_ms": load_ms,
        "latency_ms": lat, "throughput_wps": thr,
        "vram_peak_mb": vram_mb, "vram_note": vram_note,
        "parity": {"mode": "reload", "ref": None, "max_abs_diff": diff,
                   "tol": tol, "pass": bool(diff <= tol),
                   "note": "fresh RankOnlySSM + same weights + fixed seed input (32 windows seq+flat)"},
        "runs": runs, "warmup": warmup, "seed": seed,
        "loader_adaptation": "v1 khong ho tro SSM (chi mlp/tiny_mlp flat-input); "
                             "v2 them loader rankonly_ssm_v55: tai dung RankOnlySSM tu "
                             "scripts/opencode_r17b_rankonly_model.py + candidates tu dataset cfg "
                             "grid (cung builder nhu train), inputs kep seq+flat",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "git_sha": _git_sha(),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description="Benchmark SSM inference latency/VRAM/parity (local only)")
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--runs", type=int, default=200)
    ap.add_argument("--warmup", type=int, default=20)
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    ap.add_argument("--tol", type=float, default=1e-5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    rep = run_bench(a.ckpt, a.out, a.runs, a.warmup, a.device, a.tol, a.seed, a.force)
    print(json.dumps({"out": str(a.out), "device": rep["device"], "params": rep["params"],
                      "load_ms": rep["load_ms"], "latency_ms": rep["latency_ms"],
                      "vram_peak_mb": rep["vram_peak_mb"], "parity": rep["parity"]}, indent=2))


if __name__ == "__main__":
    main()
