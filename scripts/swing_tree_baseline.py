"""Cheap same-policy development comparator. Not the requested neural model."""
import torch
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from agentic_alpha_lab.backtest.swing import evaluate
from agentic_alpha_lab.data.training import sha256


def train(a):
    cfg = json.loads((a.dataset / "config.json").read_text())
    manifest = json.loads((a.dataset / "manifest.json").read_text())
    for name, digest in manifest["files"].items():
        if sha256(a.dataset / name) != digest:
            raise ValueError(f"Hash mismatch: {name}")
    if a.output.exists():
        raise FileExistsError("Choose a fresh baseline directory")
    a.output.mkdir(parents=True)
    with np.load(a.dataset / "train.npz", allow_pickle=False) as f:
        x, y = f["features"], f["labels"]
    parameters = {"n_estimators": 100, "max_depth": 8, "min_samples_leaf": 20,
                  "max_features": 0.8, "n_jobs": 2, "random_state": cfg["seed"]}
    # Direct unconditional expectancy includes unfilled=0; same gate is obtained
    # by dividing by predicted fill only when adapting to the conditional schema.
    expected = ExtraTreesRegressor(**parameters).fit(x, y[..., 0])
    fill = ExtraTreesRegressor(**parameters).fit(x, y[..., 1])
    candles = pd.read_parquet(a.dataset / "development_candles.parquet")
    reports = {}
    for split in ("validation", "policy"):
        with np.load(a.dataset / f"{split}.npz", allow_pickle=False) as f:
            features = f["features"]
        net = expected.predict(features)
        prob = np.clip(fill.predict(features), 1e-6, 1 - 1e-6)
        predictions = np.zeros((*net.shape, 6), np.float32)
        predictions[..., 0] = net / prob
        predictions[..., 4] = np.log(prob / (1 - prob))
        decisions = pd.read_parquet(a.dataset / f"{split}_decisions.parquet")
        report, signals, trades = evaluate(predictions, decisions, candles, cfg, split)
        # Comparator has no quantile or conditional-win estimator. Remove placeholder columns.
        signals = signals.drop(columns=["conditional_net_quantiles_percent", "conditional_win_score"], errors="ignore")
        signals.to_parquet(a.output / f"{split}_signals.parquet", index=False)
        trades.to_csv(a.output / f"{split}_trades.csv", index=False)
        report["model"] = "ExtraTrees_unconditional_net_and_fill"
        report["quantiles_estimated"] = False
        (a.output / f"{split}_report.json").write_text(json.dumps(report, indent=2))
        reports[split] = report
    (a.output / "metadata.json").write_text(json.dumps({"parameters": parameters, "config": cfg,
        "dataset_manifest_sha256": sha256(a.dataset / "manifest.json"), "source_sha256": sha256(Path(__file__)),
        "test_opened": False, "checkpoint_exported": False}, indent=2))
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    train(p.parse_args())
