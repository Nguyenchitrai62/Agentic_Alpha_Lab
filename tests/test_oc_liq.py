"""Offline unit tests for oc_liq pure helpers (no network, no repo data)."""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

MOD = Path(__file__).resolve().parents[1] / "research/tournament/oc_liq/liq_note.py"
spec = importlib.util.spec_from_file_location("oc_liq_note", MOD)
note = importlib.util.module_from_spec(spec)
sys.modules["oc_liq_note"] = note
spec.loader.exec_module(note)


def test_minute_floor():
    ms = pd.Series([60_000, 119_999, 120_000])
    assert note.minute_floor(ms).tolist() == [60_000, 60_000, 120_000]


def test_coverage_gaps_flags_only_big_gaps():
    cov = pd.DataFrame({"venue": ["bybit"] * 3, "start_ms": [0, 60_000, 300_000],
                        "end_ms": [60_000, 120_000, 360_000]})
    g = note.coverage_gaps(cov, gap_s=60.0)
    assert len(g) == 1 and abs(float(g.iloc[0]["gap_s"]) - 180.0) < 1e-9


def test_sigma_and_rungs_uses_history_ending_at_T_minus_4h():
    idx = pd.date_range("2026-09-01", periods=400, freq="4h", tz="UTC")
    opens = pd.Series(100 + np.arange(400, dtype=float) * 0.01, index=idx)
    t = idx[-1]
    o, sig, levels = note.sigma_and_rungs(opens, t)
    assert o == opens.loc[t]
    hist = opens.pct_change()[opens.index <= t - pd.Timedelta(hours=4)].tail(360).dropna()
    assert abs(sig - float(hist.std())) < 1e-12
    assert set(levels) == {2.5, 3.0, 3.5, 4.0}
    assert levels[4.0] < levels[2.5] < o
    # insufficient history raises
    try:
        note.sigma_and_rungs(opens.iloc[:100], idx[99])
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for short history")


def test_burst_table_sums_and_side_split():
    liq = pd.DataFrame({
        "venue": ["binance", "binance", "bybit"],
        "symbol": ["BTCUSDT"] * 3,
        "side": ["long", "short", "long"],
        "notional_usd": [100.0, 300.0, 50.0],
        "event_time": [60_000, 61_000, 3_660_000]})
    b = note.burst_table(liq)
    assert b.iloc[0]["minute"] == 60_000 and abs(b.iloc[0]["notional_usd"] - 400.0) < 1e-9
    assert abs(b.iloc[0]["long_notional"] - 100.0) < 1e-9
    assert abs(b.iloc[0]["short_notional"] - 300.0) < 1e-9


def test_bar_open_4h_floors_to_session():
    m = pd.Timestamp("2026-10-05T05:37:00Z")
    assert note.bar_open_4h(m) == pd.Timestamp("2026-10-05T04:00:00Z")
