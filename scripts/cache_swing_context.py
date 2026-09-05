"""Resume-safe frozen v5 context extraction on development only, no fitting."""
import torch
import argparse
import json
from pathlib import Path
import time
import numpy as np
from safetensors.torch import load_file
from agentic_alpha_lab.models.swing_v5 import SwingKronosV5
from agentic_alpha_lab.data.training import sha256


def cache(a):
    torch.set_num_threads(2)
    meta = json.loads((a.checkpoint / "metadata.json").read_text())
    manifest = json.loads((a.dataset / "manifest.json").read_text())
    if meta["config"]["schema"] != "kronos-base-swing-v5" or meta["runtime"]["smoke"]:
        raise ValueError("Require full v5 checkpoint")
    if sha256(a.dataset / "manifest.json") != meta["dataset_manifest_sha256"]:
        raise ValueError("Dataset provenance mismatch")
    root = Path(__file__).resolve().parents[1]
    for prefix, hashes in ((root, meta["source_hashes"]), (a.dataset, manifest["files"]),
                           (a.upstream, meta["upstream_hashes"]), (a.weights, meta["initial_weights"])):
        for name, digest in hashes.items():
            if sha256(prefix / name) != digest:
                raise ValueError(f"Hash mismatch: {prefix / name}")
    if sha256(a.checkpoint / "swing.safetensors") != meta["checkpoint_sha256"]:
        raise ValueError("Checkpoint hash mismatch")
    device = torch.device(a.device)
    identity = {"checkpoint_sha256": meta["checkpoint_sha256"], "dataset_manifest_sha256": meta["dataset_manifest_sha256"],
                "script_sha256": sha256(Path(__file__)), "batch_size": a.batch_size,
                "chunk_rows": a.chunk_rows, "device": str(device), "torch": torch.__version__,
                "representation": "v5 frozen macro/micro/engineered context before candidate utility head, 3*width",
                "test_included": False, "warning": "v5 selected using validation; downstream validation remains development, not independent evidence."}
    a.output.mkdir(parents=True, exist_ok=True)
    identity_path = a.output / "identity.json"
    if identity_path.exists():
        if json.loads(identity_path.read_text()) != identity:
            raise ValueError("Cache identity changed; choose a new folder")
    else:
        with identity_path.open("x") as f:
            json.dump(identity, f, indent=2)
    model = SwingKronosV5(a.upstream, a.weights, meta["config"]).to(device).eval()
    model.load_state_dict(load_file(str(a.checkpoint / "swing.safetensors")))
    model.requires_grad_(False)
    captured = []
    width = meta["config"]["model"]["width"]
    hook = model.score.register_forward_pre_hook(lambda module, inputs: captured.append(inputs[0][:, 0, :3*width].detach().float().cpu().numpy()))
    files, counts = {}, {}
    started = time.monotonic()
    try:
        for split in ("train", "validation", "policy"):
            with np.load(a.dataset / f"{split}.npz", allow_pickle=False) as f:
                arrays = {key: f[key] for key in ("windows", "stamps", "ages", "features")}
            count = len(arrays["features"])
            counts[split] = count
            for first in range(0, count, a.chunk_rows):
                last = min(first + a.chunk_rows, count)
                target = a.output / f"{split}_{first:06d}_{last:06d}.npz"
                digest_path = target.with_suffix(".sha256")
                if target.exists():
                    if not digest_path.exists() or sha256(target) != digest_path.read_text().strip():
                        raise ValueError(f"Unverified cache chunk: {target}")
                    with np.load(target, allow_pickle=False) as f:
                        if f["context"].shape != (last-first, 3*width) or not np.isfinite(f["context"]).all():
                            raise ValueError("Invalid existing chunk")
                else:
                    rows, predictions = [], []
                    for i in range(first, last, a.batch_size):
                        end = min(i + a.batch_size, last)
                        with torch.no_grad(), torch.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"):
                            p, _ = model(*(torch.from_numpy(arrays[key][i:end]).to(device) for key in arrays))
                        rows.append(captured.pop())
                        predictions.append(p.float().cpu().numpy())
                    context, prediction = np.concatenate(rows), np.concatenate(predictions)
                    if not np.isfinite(context).all() or not np.isfinite(prediction).all():
                        raise ValueError("Nonfinite cached features")
                    with target.open("xb") as f:
                        np.savez_compressed(f, context=context, predictions=prediction)
                    with digest_path.open("x") as f:
                        f.write(sha256(target))
                files[target.name] = sha256(target)
                print(f"{split} {last}/{count}, elapsed {time.monotonic()-started:.1f}s", flush=True)
            del arrays
    finally:
        hook.remove()
    final = {**identity, "rows": counts, "files": files, "elapsed_seconds": time.monotonic()-started, "state": "complete"}
    target = a.output / "manifest.json"
    if not target.exists():
        with target.open("x") as f:
            json.dump(final, f, indent=2)
    print("CACHE_COMPLETE", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--upstream", type=Path, default=Path("../Kronos"))
    p.add_argument("--weights", type=Path, default=Path("artifacts/models"))
    p.add_argument("--device", default="cuda:0")
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--chunk-rows", type=int, default=128)
    a = p.parse_args()
    if a.batch_size < 1 or a.chunk_rows < 1:
        p.error("batch/chunk sizes must be positive")
    cache(a)
