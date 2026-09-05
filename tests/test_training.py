from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import zipfile

import torch
import numpy as np
import pandas as pd
import pytest
import yaml

from agentic_alpha_lab.data.training import make_features, make_examples, chronological_splits, validate_source, sha256, verified_split
from agentic_alpha_lab.models.supervised import MultiHorizonMLP, probabilities, classification_metrics


ROOT = Path(__file__).resolve().parents[1]


def source(rows=9000):
    times = pd.date_range("2025-01-01", periods=rows, freq="5min", tz="UTC")
    close = 100 + np.arange(rows) * 0.001 + np.sin(np.arange(rows) / 40)
    return pd.DataFrame({"open_time": times, "close_time": times + pd.Timedelta(minutes=5) - pd.Timedelta(milliseconds=1),
                         "open": close, "high": close + 0.2, "low": close - 0.2, "close": close,
                         "volume": 1.0, "quote_volume": close})


def config():
    return yaml.safe_load((ROOT / "configs/training.yaml").read_text())


def test_features_do_not_change_when_future_is_changed():
    frame = source()
    before = make_features(frame, config()["timeframes"])
    changed = frame.copy()
    changed.loc[1501:, ["open", "high", "low", "close", "volume", "quote_volume"]] *= 10
    after = make_features(changed, config()["timeframes"])
    pd.testing.assert_frame_equal(before.iloc[:1501], after.iloc[:1501])


def test_higher_frame_does_not_appear_before_its_close():
    features = make_features(source(), ["15min"])
    assert pd.isna(features.loc[1, "x_15min_range"])
    assert np.isfinite(features.loc[2, "x_15min_range"])
    assert features.loc[2, "x_15min_range"] == features.loc[3, "x_15min_range"]


def test_purged_splits_have_disjoint_label_windows():
    settings = config()
    examples = make_examples(source(), settings)
    splits = list(chronological_splits(examples, settings).values())
    for left, right in zip(splits, splits[1:]):
        assert left.label_end.max() < right.signal_time.min()
        assert right.signal_time.min() - left.label_end.max() >= pd.Timedelta(minutes=settings["embargo_bars"] * 5)
    assert examples.y_return_12.iloc[0] == pytest.approx(
        source().close.iloc[int(examples.bar_index.iloc[0]) + 12] / examples.close.iloc[0] - 1)


@pytest.mark.parametrize("kind", ["duplicate", "gap", "nan", "bad_close"])
def test_source_rejects_invalid_data(kind):
    frame = source(50)
    if kind == "duplicate":
        frame = pd.concat([frame, frame.iloc[[0]]])
    elif kind == "gap":
        frame = frame.drop(index=2)
    elif kind == "nan":
        frame.loc[2, "close"] = np.nan
    else:
        frame.loc[2, "close_time"] += pd.Timedelta(minutes=5)
    with pytest.raises(ValueError):
        validate_source(frame)


def test_ordered_quantiles_and_calibration_metrics():
    model = MultiHorizonMLP(4, 8, 3)
    logits, quantiles = model(torch.zeros(5, 4))
    assert (quantiles[..., 0] <= quantiles[..., 1]).all()
    assert (quantiles[..., 1] <= quantiles[..., 2]).all()
    probs = probabilities(logits.detach().numpy(), 2)
    assert np.allclose(probs.sum(axis=-1), 1)
    assert 0 <= classification_metrics(probs, np.ones((5, 3), dtype=int))["ece"] <= 1


def test_hash_mismatch_is_rejected(tmp_path):
    path = tmp_path / "train.parquet"
    source(10).to_parquet(path)
    manifest = {"files": {path.name: sha256(path)}}
    source(11).to_parquet(path)
    with pytest.raises(ValueError, match="Hash mismatch"):
        verified_split(tmp_path, "train", manifest)


def test_bundle_excludes_test_and_raw_candles(tmp_path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    for name in ("train", "validation", "calibration", "test", "candles"):
        source(10).to_parquet(dataset / f"{name}.parquet")
    (dataset / "training.yaml").write_text("seed: 1729")
    manifest = {"files": {p.name: sha256(p) for p in dataset.iterdir()}}
    (dataset / "manifest.json").write_text(json.dumps(manifest))
    spec = importlib.util.spec_from_file_location("package_colab", ROOT / "scripts/package_colab.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "bundle.zip"
    module.package(ROOT, dataset, output)
    with zipfile.ZipFile(output) as archive:
        assert "dataset/test.parquet" not in archive.namelist()
        assert "dataset/candles.parquet" not in archive.namelist()
        assert "dataset/train.parquet" in archive.namelist()


def test_notebook_code_cells_compile():
    notebook = json.loads((ROOT / "notebooks/train_colab.ipynb").read_text())
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            compile("".join(cell["source"]), cell["id"], "exec")
