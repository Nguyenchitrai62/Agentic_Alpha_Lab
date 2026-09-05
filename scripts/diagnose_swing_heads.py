"""Inspect saved neural development predictions; no policy search or test opening."""
import torch
import argparse
import json
from pathlib import Path
import numpy as np
from agentic_alpha_lab.data.training import sha256


def diagnostics(train_labels, labels, predictions):
    if predictions.shape[:2] != labels.shape[:2] or predictions.shape[-1] != 6:
        raise ValueError("Prediction/label shape mismatch")
    if not np.isfinite(predictions).all() or not np.isfinite(labels).all():
        raise ValueError("Nonfinite data")
    count = train_labels[..., 1].sum(0)
    if (count == 0).any():
        raise ValueError("A candidate has no filled training observations")
    constant = (train_labels[..., 0] * train_labels[..., 1]).sum(0) / count
    mask = labels[..., 1].astype(bool)
    net, mean = labels[..., 0], predictions[..., 0]
    fill = 1 / (1 + np.exp(-np.clip(predictions[..., 4], -40, 40)))
    expected = fill * mean
    mse = float(np.mean((mean[mask] - net[mask]) ** 2))
    constant_mse = float(np.mean((np.broadcast_to(constant, mean.shape)[mask] - net[mask]) ** 2))
    temporal_std = mean.std(0)
    label_std = [float(net[:, k][mask[:, k]].std()) if mask[:, k].any() else None for k in range(net.shape[1])]
    # Descriptive only: nearby multi-day labels overlap and are not independent draws.
    return {"decisions": len(labels), "filled_candidate_observations": int(mask.sum()),
            "neural_conditional_net_mse": mse, "train_candidate_mean_mse": constant_mse,
            "relative_mse_improvement_over_train_constant": 1 - mse / constant_mse if constant_mse > 0 else None,
            "neural_time_std_by_candidate_percent": temporal_std.tolist(),
            "filled_label_std_by_candidate_percent": label_std,
            "median_neural_time_std_percent": float(np.median(temporal_std)),
            "mean_predicted_fill_score": float(fill.mean()), "actual_candidate_fill_fraction": float(mask.mean()),
            "expected_net_min_median_max_percent": np.quantile(expected, [0, .5, 1]).tolist(),
            "top_candidate_counts": np.bincount(expected.argmax(1), minlength=expected.shape[1]).tolist(),
            "train_conditional_mean_by_candidate_percent": constant.tolist(),
            "warning": "Development diagnostics only; candidate outcomes overlap. MSE and score compression do not establish trading profitability or uniquely identify the cause. Saved predictions used; this is not a full-weight replay."}


def run(a):
    if a.output.exists():
        raise FileExistsError("Choose a new diagnostic folder")
    manifest = json.loads((a.dataset / "manifest.json").read_text())
    meta = json.loads((a.checkpoint / "metadata.json").read_text())
    if sha256(a.dataset / "manifest.json") != meta["dataset_manifest_sha256"]:
        raise ValueError("Checkpoint dataset provenance mismatch")
    for name, digest in manifest["files"].items():
        if sha256(a.dataset / name) != digest:
            raise ValueError(f"Dataset changed: {name}")
    with np.load(a.dataset / "train.npz", allow_pickle=False) as arrays:
        train = arrays["labels"]
    report = {"dataset_manifest_sha256": sha256(a.dataset / "manifest.json"),
              "checkpoint_metadata_sha256": sha256(a.checkpoint / "metadata.json"),
              "script_sha256": sha256(Path(__file__)), "test_opened": False, "splits": {}}
    for split in ("validation", "policy"):
        with np.load(a.dataset / f"{split}.npz", allow_pickle=False) as arrays:
            labels = arrays["labels"]
        path = a.checkpoint / f"{split}_predictions.npy"
        prediction = np.load(path, allow_pickle=False)
        report["splits"][split] = diagnostics(train, labels, prediction)
        report["splits"][split]["predictions_sha256"] = sha256(path)
    a.output.mkdir(parents=True)
    (a.output / "diagnosis.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    run(p.parse_args())
