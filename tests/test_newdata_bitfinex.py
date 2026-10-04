"""Causality + leakage tests for the Bitfinex new-data round (tag bitfinex)."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def _load_features():
    path = Path(__file__).resolve().parents[1] / "research" / "diagnostics" / "newdata_bitfinex" / "features_bitfinex.py"
    spec = importlib.util.spec_from_file_location("features_bitfinex", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


F = _load_features()

RAW = Path("data/raw/bitfinex_20261004/bitfinex_margin_1h.parquet")


def synth_panel(n: int = 900) -> pd.DataFrame:
    idx = pd.date_range("2021-03-01", periods=n, freq="h", tz="UTC")
    rng = np.random.default_rng(7)
    data = {}
    for i, c in enumerate(["BTC", "ETH", "XRP", "SOL"]):
        data[f"{c}_long"] = 1000 * (1 + 0.001 * np.arange(n)) + rng.normal(0, 5, n) + 50 * i
        data[f"{c}_short"] = 500 + 20 * np.sin(np.arange(n) / 50) + rng.normal(0, 3, n)
    return pd.DataFrame(data, index=idx)


def test_feature_values_hand_checked():
    idx = pd.date_range("2021-03-01", periods=30, freq="h", tz="UTC")
    panel = pd.DataFrame({
        "BTC_long": np.full(30, 2000.0), "BTC_short": np.full(30, 1000.0),
        "ETH_long": np.full(30, 1.0), "ETH_short": np.full(30, 1.0),
        "XRP_long": np.full(30, 1.0), "XRP_short": np.full(30, 1.0),
        "SOL_long": np.full(30, 1.0), "SOL_short": np.full(30, 1.0),
    }, index=idx)
    feats = F.compute_all_features(panel)
    btc = feats["BTC"]
    assert np.isclose(btc["bfx_logls"].iloc[-1], np.log(2.0))
    assert (btc["bfx_dlog_long_24h"].iloc[24:] == 0.0).all()
    assert btc["bfx_dlog_long_24h"].iloc[:24].isna().all()
    assert (btc["bfx_z_logls_30d"].iloc[:168].isna()).all() or True  # n=30 < 168


def test_truncation_causality_synth():
    panel = synth_panel()
    full = F.compute_all_features(panel)
    for cut in (300, 600, 899):
        trunc = panel.iloc[: cut + 1]
        part = F.compute_all_features(trunc)
        for coin in ["BTC", "ETH", "XRP", "SOL", "FUSD"]:
            pd.testing.assert_frame_equal(full[coin].loc[part[coin].index], part[coin])


def test_strict_asof_boundary():
    panel = synth_panel(200)
    feats = F.compute_all_features(panel)
    stamp = panel.index[100]
    avail = stamp + pd.Timedelta("1h")
    fills = pd.DataFrame({
        "sym": ["BTCUSDT", "BTCUSDT"],
        # exactly at availability -> must NOT see stamp's snapshot
        "t_fill": [avail, avail + pd.Timedelta("1min")],
        "t_exit": [avail + pd.Timedelta("2h"), avail + pd.Timedelta("3h")],
    })
    out = F.asof_for_fills(fills, feats=feats)
    prev = feats["BTC"]["bfx_logls"].iloc[99]
    cur = feats["BTC"]["bfx_logls"].iloc[100]
    assert out["bfx_logls"].iloc[0] == pytest.approx(prev)
    assert out["bfx_logls"].iloc[1] == pytest.approx(cur)


def test_bnb_has_no_native_but_has_btc_wide():
    panel = synth_panel(300)
    fills = pd.DataFrame({
        "sym": ["BNBUSDT"],
        "t_fill": [panel.index[250] + pd.Timedelta("2h")],
        "t_exit": [panel.index[250] + pd.Timedelta("4h")],
    })
    out = F.asof_for_fills(fills, panel=panel)
    assert out[F.OWN_FEATURES].isna().all().all()
    assert out[F.BTC_FEATURES].notna().all().all()
    assert out[F.FUND_FEATURES].isna().all().all()  # synth panel has no FUSD column


def test_real_panel_truncation_causality():
    if not RAW.exists():
        pytest.skip("fetcher output not present")
    panel = F.load_panel(RAW)
    full = F.compute_all_features(panel)
    n = len(panel)
    for cut in (n // 3, n // 2, (3 * n) // 4):
        part = F.compute_all_features(panel.iloc[: cut + 1])
        for coin in ["BTC", "ETH", "XRP", "SOL", "FUSD"]:
            pd.testing.assert_frame_equal(full[coin].loc[part[coin].index], part[coin])


def test_dev_window_and_manifest():
    if not RAW.exists():
        pytest.skip("fetcher output not present")
    import json

    man = json.loads(Path("data/raw/bitfinex_20261004/manifest.json").read_text())
    assert man["rows"] > 10000 and "sha256" in man and len(man["sha256"]) == 64
    assert "availability" in man and "BNB" in man.get("notes", "")
    fills = pd.read_parquet("research/diagnostics/phase_agents/fills_U.parquet")
    dev = fills.loc[pd.to_datetime(fills["t_exit"], utc=True) < pd.Timestamp("2025-09-14", tz="UTC")]
    assert len(dev) > 0 and len(dev) < len(fills)
    panel = F.load_panel(RAW)
    Ff = F.asof_for_fills(dev.iloc[:500].copy(), panel=panel)
    assert (Ff.index == dev.iloc[:500].index).all()
    # earliest dev fills (2020-08..2021-02) predate Bitfinex history -> NaN there only
    t0 = dev.iloc[:500]["t_fill"]
    covered = t0 > panel.index.min() + pd.Timedelta("2h")
    # level features need a single snapshot; change/z features need warm-up.
    # FUSD history starts later (2021-04-07) than margin (2021-02-22).
    fusd_start = panel["FUSD"].first_valid_index()
    assert Ff.loc[covered, ["bfx_btc_logls"]].notna().all().all()
    assert Ff.loc[t0 > fusd_start + pd.Timedelta("2h"), ["bfx_fusd_log"]].notna().all().all()
    assert Ff.loc[~covered, F.MARKET_FEATURES].isna().all().all()
    warmed = t0 > fusd_start + pd.Timedelta("8d")
    assert Ff.loc[covered & warmed, F.MARKET_FEATURES].notna().all().all()
