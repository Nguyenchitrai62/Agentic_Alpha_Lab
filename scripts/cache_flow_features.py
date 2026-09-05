"""Build versioned causal activity cache for the same v5 development decisions."""
import torch
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from agentic_alpha_lab.data.flow_features import flow_features
from agentic_alpha_lab.data.training import sha256, validate_source


def cache(a):
    if a.output.exists():
        raise FileExistsError("Choose new feature cache")
    meta = json.loads((a.dataset / "manifest.json").read_text())
    for name, digest in meta["files"].items():
        if sha256(a.dataset / name) != digest:
            raise ValueError(f"Dataset changed: {name}")
    candles = validate_source(pd.read_parquet(a.dataset / "development_candles.parquet"))
    a.output.mkdir(parents=True)
    rows, files = {}, {}
    for split in ("train", "validation", "policy"):
        decisions = pd.read_parquet(a.dataset / f"{split}_decisions.parquet")
        features, names = flow_features(candles, decisions.signal_time)
        target = a.output / f"{split}_000000_{len(features):06d}.npz"
        np.savez_compressed(target, context=features)
        rows[split], files[target.name] = len(features), sha256(target)
    report = {"state": "complete", "dataset_manifest_sha256": sha256(a.dataset / "manifest.json"),
              "representation": "causal closed flow/activity40", "feature_names": names, "rows": rows, "files": files,
              "feature_source_sha256": sha256(Path(__file__).resolve().parents[1] / "src/agentic_alpha_lab/data/flow_features.py"),
              "script_sha256": sha256(Path(__file__)), "test_included": False}
    (a.output / "manifest.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    cache(p.parse_args())
