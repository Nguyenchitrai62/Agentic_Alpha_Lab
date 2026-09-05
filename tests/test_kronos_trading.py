import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import torch
from agentic_alpha_lab.data.kronos_trading import WindowStore, candidates, bracket_prices, candidate_labels, decode_suggestion
from agentic_alpha_lab.models.kronos_trading import BracketFusion, trading_loss
from agentic_alpha_lab.backtest.engine import run_backtest, CostModel, ExecutionConfig


def config():
    return json.loads((Path(__file__).resolve().parents[1] / "configs/kronos_trading.json").read_text())


def candles(n=4000):
    t = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC")
    close = 100 + np.sin(np.arange(n) / 20)
    return pd.DataFrame({"open_time": t, "close_time": t + pd.Timedelta(minutes=5) - pd.Timedelta(milliseconds=1),
                         "open": close, "high": close + 0.2, "low": close - 0.2, "close": close,
                         "volume": 1.0, "quote_volume": close})


def test_windows_are_as_of_and_ignore_future():
    c, cfg = candles(), config()
    index = 3500
    original = WindowStore(c, cfg).at(c.close_time.iloc[index])
    c.loc[index + 1:, ["open", "high", "low", "close", "volume", "quote_volume"]] *= 10
    altered = WindowStore(c, cfg).at(c.close_time.iloc[index])
    for a, b in zip(original, altered):
        np.testing.assert_array_equal(a, b)
    assert original[0].shape == (4, 64, 6)
    assert ((original[2] >= 0) & (original[2] < 1)).all()


def test_incomplete_higher_timeframe_not_visible():
    c, cfg = candles(), config()
    store = WindowStore(c, cfg)
    a = store.at(c.close_time.iloc[3503])[0]  # closes a 4h bucket
    b = store.at(c.close_time.iloc[3504])[0]
    np.testing.assert_array_equal(a[-1], b[-1])
    with pytest.raises(ValueError, match="Insufficient"):
        store.at(c.close_time.iloc[10])


def test_brackets_are_ordered_and_wait_gates():
    cfg = config()
    for candidate in candidates(cfg):
        s = bracket_prices(100, 0.1, candidate, cfg)
        levels = [s[k] for k in ("stop_loss", "entry_limit", "take_profit_1", "take_profit_2")]
        assert np.all(np.diff(levels) * s["direction"] > 0)
    prediction = np.zeros((8, 6))
    assert decode_suggestion(prediction, 100, 0.1, cfg)["action"] == "WAIT"
    prediction[4, 0], prediction[4, 5] = 1, 2
    s = decode_suggestion(prediction, 100, 0.1, cfg)
    assert s["action"] == "SHORT" and s["leverage"] == 1 and not s["calibrated"]
    prediction[0, 0] = np.nan
    with pytest.raises(ValueError):
        decode_suggestion(prediction, 100, 0.1, cfg)


def test_labels_match_existing_execution_engine_and_reject_truncation():
    c, cfg = candles(100), config()
    labels = candidate_labels(c, 10, 0.2, cfg)
    for i, candidate in enumerate(candidates(cfg)):
        s = {"bar_index": 10, **bracket_prices(float(c.close.iloc[10]), 0.2, candidate, cfg)}
        result, trades = run_backtest(c, pd.DataFrame([s]), 100, CostModel(**cfg["costs"]),
                                     ExecutionConfig(max_holding_bars=48))
        np.testing.assert_allclose(labels[i], [result.net_profit, bool(trades), result.net_profit > 0], atol=1e-6)
    with pytest.raises(ValueError, match="Truncated"):
        candidate_labels(c, 60, 0.2, cfg)


def test_fusion_shapes_quantile_order_and_gradients():
    model = BracketFusion(512, config())
    prediction = model(torch.randn(3, 4, 512), torch.zeros(3, 4))
    assert prediction.shape == (3, 8, 6)
    assert torch.all(prediction[..., 1] < prediction[..., 2])
    assert torch.all(prediction[..., 2] < prediction[..., 3])
    loss = trading_loss(prediction, torch.zeros(3, 8, 3))
    loss.backward()
    assert torch.isfinite(loss) and model.timeframe.grad.abs().sum() > 0


def test_kaggle_bundle_allowlist_privacy_and_hash_guard(tmp_path):
    import importlib.util
    import zipfile
    from agentic_alpha_lab.data.training import sha256
    project = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("kaggle_packager_test", project / "scripts/package_kaggle.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root, upstream, dataset = tmp_path / "repo", tmp_path / "upstream", tmp_path / "data"
    fixture_files = [root / "src/module.py", upstream / "model/__init__.py", upstream / "LICENSE",
                     root / "scripts/train_kronos_trading.py", root / "scripts/infer_kronos_trading.py",
                     root / "scripts/kaggle_bootstrap.py", root / "access_token", dataset / "test.parquet"]
    for folder in ("Kronos-mini", "Kronos-Tokenizer-2k"):
        fixture_files.extend(root / "artifacts/models" / folder / n for n in ("config.json", "model.safetensors"))
    for path in fixture_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
    names = ["config.json", "train.npz", "validation.npz", "train_decisions.parquet",
             "validation_decisions.parquet", "development_candles.parquet"]
    for name in names:
        (dataset / name).write_text("fixture-data")
    manifest = {"smoke_only": False, "test_included": False, "calibration_included": False,
                "files": {n: sha256(dataset / n) for n in names}}
    (dataset / "manifest.json").write_text(json.dumps(manifest))
    output = tmp_path / "stage"
    module.package(root, dataset, upstream, output, "example", "btc-test")
    with zipfile.ZipFile(output / "dataset/alpha-lab-bundle.zip") as archive:
        assert not any("access_token" in n or "test.parquet" in n for n in archive.namelist())
        hashes = json.loads(archive.read("bundle-hashes.json"))
        assert set(hashes) == set(archive.namelist()) - {"bundle-hashes.json"}
    metadata = json.loads((output / "kernel/kernel-metadata.json").read_text())
    assert metadata["is_private"] is True and metadata["machine_shape"] == "NvidiaTeslaT4"
    (dataset / "train.npz").write_text("tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        module.package(root, dataset, upstream, tmp_path / "stage2", "example", "btc-test")
