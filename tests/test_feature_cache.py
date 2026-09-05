import json
import numpy as np
import pandas as pd
import pytest
from agentic_alpha_lab.data.feature_cache import read_aligned_features
from agentic_alpha_lab.data.training import sha256


def fixture(tmp_path, mode="ok"):
    dataset, cache = tmp_path / "dataset", tmp_path / "cache"
    dataset.mkdir()
    cache.mkdir()
    (dataset / "manifest.json").write_text("{}")
    dates = pd.to_datetime(["2024-01-10T06:04:59.999Z", "2024-01-10T12:04:59.999Z"], utc=True)
    decisions = pd.DataFrame({"signal_time": dates})
    frame = pd.DataFrame({"signal_time": dates[::-1] if mode == "reordered" else dates,
                          "source_day": pd.Timestamp("2024-01-08T00:00:00Z"),
                          "available_at": pd.Timestamp("2024-01-10T00:00:00Z")})
    if mode == "future":
        frame["available_at"] = pd.Timestamp("2024-01-11T00:00:00Z")
    frame.to_parquet(cache / "availability.parquet", index=False)
    np.savez(cache / "features.npz", features=np.zeros((2, 1), np.float32))
    meta = {"state": "complete_research_scenario", "dataset_manifest_sha256": sha256(dataset / "manifest.json"),
            "names": ["example"], "lag_hours": 48, "point_in_time_availability_verified": False,
            "files": {name: sha256(cache / name) for name in ("features.npz", "availability.parquet")}}
    (cache / "manifest.json").write_text(json.dumps(meta))
    return cache, dataset, decisions


def test_verified_cache_still_rejects_reordered_decisions(tmp_path):
    with pytest.raises(ValueError, match="row alignment"):
        read_aligned_features(*fixture(tmp_path, "reordered"))


def test_verified_cache_rejects_future_availability(tmp_path):
    with pytest.raises(ValueError, match="Future"):
        read_aligned_features(*fixture(tmp_path, "future"))


def test_valid_delayed_cache_and_changed_dataset_identity(tmp_path):
    cache, dataset, decisions = fixture(tmp_path)
    features, meta = read_aligned_features(cache, dataset, decisions)
    assert features.shape == (2, 1)
    assert meta["point_in_time_availability_verified"] is False
    (dataset / "manifest.json").write_text('{"changed": true}')
    with pytest.raises(ValueError, match="identity"):
        read_aligned_features(cache, dataset, decisions)
