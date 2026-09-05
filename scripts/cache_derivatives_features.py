"""Build a disclosed delayed-archive feature scenario on immutable development decisions."""
import torch
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from agentic_alpha_lab.data.training import sha256
from agentic_alpha_lab.data import derivatives_features


def run(a):
    source = json.loads((a.source/"manifest.json").read_text())
    dataset = json.loads((a.dataset/"manifest.json").read_text())
    if source["state"] != "complete_audit_only" or source["quality"]["duplicate_timestamps"]:
        raise ValueError("Need completed unique-timestamp archive audit")
    for directory,manifest in ((a.source,source),(a.dataset,dataset)):
        for name,digest in manifest["files"].items():
            if sha256(directory/name) != digest:
                raise ValueError(f"Changed data: {name}")
    if a.output.exists():
        raise FileExistsError("Choose a new immutable feature cache")
    metrics = pd.read_parquet(a.source/"metrics.parquet")
    decisions = pd.read_parquet(a.dataset/"decisions.parquet")
    context = derivatives_features.daily_context(metrics,a.lag_hours)
    features,names,availability = derivatives_features.asof_features(context,decisions.signal_time)
    a.output.mkdir(parents=True)
    np.savez_compressed(a.output/"features.npz",features=features)
    availability.to_parquet(a.output/"availability.parquet",index=False)
    context.to_parquet(a.output/"daily_context.parquet",index=False)
    manifest = {"state":"complete_research_scenario","rows":len(features),"names":names,"lag_hours":a.lag_hours,
                "source_manifest_sha256":sha256(a.source/"manifest.json"),"dataset_manifest_sha256":sha256(a.dataset/"manifest.json"),
                "script_sha256":sha256(Path(__file__)),"feature_source_sha256":sha256(Path(derivatives_features.__file__)),
                "missing_fraction_by_feature":dict(zip(names[:20],features[:,20:].mean(axis=0).tolist())),
                "point_in_time_availability_verified":False,"live_approved":False,
                "warning":"Daily historical archive availability is proxied by source_day+lag_hours, NOT observed receipt time. Use only disclosed exploratory lag sensitivity. Missing values are zero with explicit mask, never forward/backward-filled.",
                "files":{name:sha256(a.output/name) for name in ("features.npz","availability.parquet","daily_context.parquet")}}
    (a.output/"manifest.json").write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2),flush=True)


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",type=Path,default=Path("data/processed/btc_derivatives_metrics_20260905_v1"))
    p.add_argument("--dataset",type=Path,default=Path("data/processed/swing_regime_research_v4"))
    p.add_argument("--lag-hours",type=int,choices=[48,72],required=True)
    p.add_argument("--output",type=Path,required=True)
    run(p.parse_args())
