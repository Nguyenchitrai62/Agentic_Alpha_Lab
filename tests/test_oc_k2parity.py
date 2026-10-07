"""oc_k2parity tests: causality/truncation + hand-checked synthetic cases.
CPU-only (no network, no model weights)."""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("kronos_shadow", ROOT / "scripts/kronos_shadow.py")
ks = importlib.util.module_from_spec(SPEC)
sys.modules["kronos_shadow"] = ks
SPEC.loader.exec_module(ks)


def h1_fixture(start="2026-01-01", hours=500):
    t = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    close = 100 + np.sin(np.arange(hours) / 20.0)
    return pd.DataFrame({
        "open_time": t, "open": close, "high": close + 0.2, "low": close - 0.2,
        "close": close, "volume": 1.0, "quote_volume": close * 1.0,
        "close_time": t + pd.Timedelta(hours=1) - pd.Timedelta(milliseconds=1),
        "closed": True})


def test_causality_future_1h_does_not_change_context():
    h1 = h1_fixture(hours=900)
    T = h1["open_time"].iloc[800].floor("4h")
    T = T - pd.Timedelta(hours=int(T.hour) % 4) + pd.Timedelta(hours=int(T.hour) % 4)
    s = int(T.hour) % 4
    # align T onto the shift-s grid
    T = ((T - pd.Timedelta(hours=s)).floor("4h") + pd.Timedelta(hours=s))
    ctx1 = ks.select_context(ks.build_shift_bars(h1, s), T)
    h1f = h1.copy()
    m = h1f["open_time"] >= pd.Timestamp(T)
    h1f.loc[m, ["open", "high", "low", "close"]] *= 10.0
    ctx2 = ks.select_context(ks.build_shift_bars(h1f, s), T)
    pd.testing.assert_frame_equal(ctx1, ctx2)


def test_shift_bar_aggregation_hand_checked():
    t = pd.date_range("2026-09-01", periods=4, freq="h", tz="UTC")
    h1 = pd.DataFrame({
        "open_time": t, "open": [10.0, 11.0, 12.0, 13.0],
        "high": [10.5, 11.5, 12.5, 13.5], "low": [9.5, 10.5, 11.5, 12.5],
        "close": [10.2, 11.2, 12.2, 13.2], "volume": [1.0, 2.0, 3.0, 4.0],
        "quote_volume": [10.0, 20.0, 30.0, 40.0],
        "close_time": t + pd.Timedelta(hours=1) - pd.Timedelta(milliseconds=1),
        "closed": True})
    b = ks.build_shift_bars(h1, 0)
    assert len(b) == 1
    r = b.iloc[0]
    assert r["open"] == 10.0 and r["close"] == 13.2
    assert r["high"] == 13.5 and r["low"] == 9.5
    assert r["volume"] == 10.0 and r["amount"] == 100.0 and r["n_h"] == 4


def test_assign_k2_boundaries_hand_checked():
    q20, q80 = 0.5872428352509342, 2.182801599162049
    # risk = -low1; direction=+1: risk>=q80 -> 1.25, risk<=q20 -> 0.75, else 1.0
    assert ks.assign_k2(-q80, 1, q20, q80) == 1.25      # risk exactly q80 (inclusive)
    assert ks.assign_k2(-q20, 1, q20, q80) == 0.75      # risk exactly q20 (inclusive)
    assert ks.assign_k2(-1.0, 1, q20, q80) == 1.0       # middle
    assert ks.assign_k2(float("nan"), 1, q20, q80) == 1.0
    # frozen constants match fits.json anchor 2025
    import json
    f = json.loads((ROOT / "research/tournament/oc_kronoshidden/fits.json").read_text())["2025-09-24"]
    assert f["direction"] == 1 and abs(f["q20"] - q20) < 1e-12 and abs(f["q80"] - q80) < 1e-12


def test_seed_stable_per_row_and_unique():
    T = pd.Timestamp("2026-09-05T12:00:00Z")
    assert ks.seed_for("BTCUSDT", 0, T) == ks.seed_for("BTCUSDT", 0, T)
    assert len({ks.seed_for("BTCUSDT", 0, T), ks.seed_for("ETHUSDT", 0, T),
                ks.seed_for("BTCUSDT", 1, T)}) == 3
