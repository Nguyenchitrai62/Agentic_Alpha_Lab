"""Reproduce proven development comparator and freeze safe checkpoint BEFORE test."""
import torch
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from agentic_alpha_lab.models.tree_pipeline import export_forests, PortableForest
from agentic_alpha_lab.data.training import sha256
from agentic_alpha_lab.backtest.swing import evaluate


def train(a):
    plan = json.loads(a.plan.read_text())
    config = json.loads((a.dataset / "config.json").read_text())
    manifest = json.loads((a.dataset / "manifest.json").read_text())
    for name, digest in manifest["files"].items():
        if sha256(a.dataset / name) != digest:
            raise ValueError(f"Dataset changed: {name}")
    with np.load(a.dataset / "train.npz", allow_pickle=False) as f:
        x, y = f["features"], f["labels"]
    forests = {name: ExtraTreesRegressor(**plan["model"]).fit(x, y[..., column])
               for name, column in (("expected", 0), ("fill", 1))}
    export_forests(forests, a.output)
    portable = PortableForest(a.output)
    for name, original in forests.items():
        np.testing.assert_allclose(portable.predict(name, x), original.predict(x), rtol=1e-10, atol=1e-10)
    # Exposure reduction threshold is fitted to TRAIN ensemble disagreement only.
    _, uncertainty = portable.predict("expected", x, True)
    uncertainty_scale = float(np.median(uncertainty))
    results = {}
    for split in ("validation", "policy"):
        with np.load(a.dataset / f"{split}.npz", allow_pickle=False) as f:
            p, _ = portable.swing_prediction(f["features"])
        report, signals, trades = evaluate(p, pd.read_parquet(a.dataset / f"{split}_decisions.parquet"),
                          pd.read_parquet(a.dataset / "development_candles.parquet"), config, split)
        signals = signals.drop(columns=["conditional_net_quantiles_percent", "conditional_win_score"], errors="ignore")
        signals.to_parquet(a.output / f"{split}_signals.parquet", index=False)
        trades.to_csv(a.output / f"{split}_trades.csv", index=False)
        (a.output / f"{split}_report.json").write_text(json.dumps(report, indent=2))
        results[split] = report["result"]
    root = Path(__file__).resolve().parents[1]
    source_files = [*sorted((root / "src").rglob("*.py")), Path(__file__)]
    metadata = {"config": config, "research_plan": plan, "model": "ExtraTrees multi-timeframe swing",
                "dataset_manifest_sha256": sha256(a.dataset / "manifest.json"), "checkpoint_sha256": sha256(a.output / "forests.npz"),
                "uncertainty_train_median": uncertainty_scale, "test_opened_at_freeze": False,
                "quantiles_estimated": False, "probabilities_calibrated": False, "approved_for_live": False,
                "source_hashes": {p.relative_to(root).as_posix(): sha256(p) for p in source_files}}
    (a.output / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps({"checkpoint": str(a.output), "train_export_verified": True, "development": results}, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, default=Path("configs/tree_research_plan.json"))
    p.add_argument("--dataset", type=Path, default=Path("data/processed/kronos_swing_20260905_v2"))
    p.add_argument("--output", type=Path, required=True)
    train(p.parse_args())
