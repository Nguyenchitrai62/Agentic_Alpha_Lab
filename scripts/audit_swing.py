"""Verify downloaded swing checkpoint and replay development predictions, never test."""
import torch
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from safetensors.torch import load_file
from agentic_alpha_lab.models.swing import SwingKronos
from agentic_alpha_lab.data.training import sha256
from agentic_alpha_lab.backtest.swing import evaluate


def audit(a):
    meta = json.loads((a.checkpoint / "metadata.json").read_text())
    dataset_meta = json.loads((a.dataset / "manifest.json").read_text())
    if sha256(a.checkpoint / "swing.safetensors") != meta["checkpoint_sha256"]:
        raise ValueError("Checkpoint mismatch")
    if sha256(a.dataset / "manifest.json") != meta["dataset_manifest_sha256"]:
        raise ValueError("Dataset manifest mismatch")
    for prefix, hashes in ((a.dataset, dataset_meta["files"]), (a.upstream, meta["upstream_hashes"]),
                           (a.weights, meta["initial_weights"]), (Path(__file__).resolve().parents[1], meta["source_hashes"])):
        for name, digest in hashes.items():
            if sha256(prefix / name) != digest:
                raise ValueError(f"Provenance mismatch: {prefix / name}")
    if not meta["full_trunk_updated"] or not all(v > 0 for v in meta["best_block_weight_delta_probe"]):
        raise ValueError("No evidence of full trunk update")
    device = torch.device(a.device or ("cuda:0" if torch.cuda.is_available() else "cpu"))
    model = SwingKronos(a.upstream, a.weights, meta["config"]).to(device).eval()
    model.load_state_dict(load_file(str(a.checkpoint / "swing.safetensors")))
    report = {"hashes_verified": True, "test_read": False, "runtime": meta["runtime"], "splits": {}}
    candles = pd.read_parquet(a.dataset / "development_candles.parquet")
    for split in ("validation", "policy"):
        stored = np.load(a.checkpoint / f"{split}_predictions.npy", allow_pickle=False)
        indices = np.linspace(0, len(stored)-1, min(8, len(stored)), dtype=int)
        with np.load(a.dataset / f"{split}.npz", allow_pickle=False) as f:
            inputs = {k: f[k][indices] for k in ("windows", "stamps", "ages", "features")}
        replay = []
        with torch.no_grad():
            for i in range(len(indices)):
                with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"):
                    p, _ = model(*(torch.from_numpy(inputs[k][i:i+1]).to(device) for k in inputs))
                replay.append(p.float().cpu().numpy()[0])
        error = float(np.abs(np.stack(replay) - stored[indices]).max())
        # FP16 fused-kernel differences are expected across GPU/torch versions.
        if not np.isfinite(error) or error > 0.1:
            raise ValueError(f"Replay mismatch: {split}: {error}")
        decisions = pd.read_parquet(a.dataset / f"{split}_decisions.parquet").iloc[:len(stored)]
        reproduced, _, _ = evaluate(stored, decisions, candles, meta["config"], split)
        original = json.loads((a.checkpoint / f"{split}_report.json").read_text())
        for field in ("final_equity", "gross_pnl", "fees", "funding", "max_drawdown", "trades"):
            if not np.isclose(original["result"][field], reproduced["result"][field], atol=1e-7):
                raise ValueError(f"Backtest mismatch: {split}/{field}")
        report["splits"][split] = {"replay_samples": len(indices), "max_prediction_error": error,
                                    "backtest_verified": True, "result": reproduced["result"]}
    if a.output.exists():
        raise FileExistsError("Choose new audit path")
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--upstream", type=Path, default=Path("../Kronos"))
    p.add_argument("--weights", type=Path, default=Path("artifacts/models"))
    p.add_argument("--device")
    audit(p.parse_args())
