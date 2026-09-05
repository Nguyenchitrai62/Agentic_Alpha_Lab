"""Validate derivatives feature provenance and per-row as-of alignment before fitting."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from agentic_alpha_lab.data.training import sha256


def read_aligned_features(cache, dataset, decisions):
    meta = json.loads((cache / "manifest.json").read_text())
    if meta["state"] != "complete_research_scenario" or meta["dataset_manifest_sha256"] != sha256(dataset / "manifest.json"):
        raise ValueError("Feature cache dataset identity mismatch")
    for name, digest in meta["files"].items():
        if Path(name).name != name or sha256(cache / name) != digest:
            raise ValueError("Invalid feature cache file/hash")
    with np.load(cache / "features.npz", allow_pickle=False) as f:
        features = f["features"]
    availability = pd.read_parquet(cache / "availability.parquet")
    if features.shape != (len(decisions), len(meta["names"])) or not np.isfinite(features).all():
        raise ValueError("Invalid feature matrix")
    observed = pd.DatetimeIndex(availability.signal_time)
    expected = pd.DatetimeIndex(decisions.signal_time)
    if not observed.equals(expected):
        raise ValueError("Feature decision row alignment mismatch")
    known = availability.available_at.notna()
    delay = availability.signal_time[known] - availability.available_at[known]
    if (delay < pd.Timedelta(0)).any() or (delay >= pd.Timedelta(days=1)).any():
        raise ValueError("Future or stale feature context")
    if not ((availability.available_at[known] - availability.source_day[known]) == pd.Timedelta(hours=meta["lag_hours"])).all():
        raise ValueError("Feature lag contract mismatch")
    return features, {"path": str(cache), "manifest_sha256": sha256(cache / "manifest.json"),
                      "lag_hours": meta["lag_hours"], "names": meta["names"],
                      "point_in_time_availability_verified": meta["point_in_time_availability_verified"]}
