"""Offline unit tests for oc_liqcheck pure helpers (no network, no repo data)."""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

MOD = Path(__file__).resolve().parents[1] / "research/tournament/oc_liqcheck/liqcheck.py"
spec = importlib.util.spec_from_file_location("oc_liqcheck_mod", MOD)
mod = importlib.util.module_from_spec(spec)
sys.modules["oc_liqcheck_mod"] = mod
spec.loader.exec_module(mod)


def test_minute_floor():
    ms = pd.Series([60_000, 119_999, 120_000])
    assert mod.minute_floor(ms).tolist() == [60_000, 60_000, 120_000]


def test_coverage_gaps_uses_300s_threshold():
    cov = pd.DataFrame({"venue": ["binance"] * 3, "start_ms": [0, 60_000, 400_000],
                        "end_ms": [60_000, 120_000, 460_000]})
    g = mod.coverage_gaps(cov, gap_s=300.0)
    assert len(g) == 0  # 280 s gap is not flagged at the 300 s bar
    cov2 = pd.DataFrame({"venue": ["binance"] * 3, "start_ms": [0, 60_000, 500_000],
                         "end_ms": [60_000, 120_000, 560_000]})
    g2 = mod.coverage_gaps(cov2, gap_s=300.0)
    assert len(g2) == 1 and abs(float(g2.iloc[0]["gap_s"]) - 380.0) < 1e-9


def test_burst_table_sums_and_side_split():
    liq = pd.DataFrame({
        "venue": ["binance", "binance", "bybit"],
        "symbol": ["BTCUSDT"] * 3,
        "side": ["long", "short", "long"],
        "notional_usd": [100.0, 300.0, 50.0],
        "event_time": [60_000, 61_000, 3_660_000]})
    b = mod.burst_table(liq)
    assert b.iloc[0]["minute"] == 60_000 and abs(b.iloc[0]["notional_usd"] - 400.0) < 1e-9
    assert abs(b.iloc[0]["long_notional"] - 100.0) < 1e-9
    assert abs(b.iloc[0]["short_notional"] - 300.0) < 1e-9


def test_path_stats_min_max():
    assert mod.path_stats({"a": -0.5, "b": 0.2}) == {"min": -0.5, "max": 0.2}
    assert mod.path_stats({}) == {}


def test_sanity_frame_flags_bad_rows_and_dups():
    d = pd.DataFrame({
        "venue": ["binance", "binance", "bybit"],
        "symbol": ["BTCUSDT"] * 3,
        "side": ["long", "oops", "long"],
        "raw_side": ["SELL", "BUY", "Buy"],
        "price": [100.0, 0.0, 50.0],
        "qty": [1.0, 1.0, 0.0],
        "notional_usd": [100.0, 10.0, 5.0],
        "event_time": [1_000, 2_000, 1_500],  # unsorted on purpose
        "recv_time": [1_100, 2_100, 1_600]})
    s = mod.sanity_frame(d)
    assert s["bad_side"] == 1 and s["bad_price"] == 1 and s["bad_qty"] == 1
    assert s["event_time_monotonic"] is False
    assert s["notional_inconsistent"] >= 1  # row 2: 0*1 != 10
    # exact duplicate rows collapse on the dedupe key
    dd = pd.concat([d.iloc[[0]], d.iloc[[0]]], ignore_index=True)
    assert mod.sanity_frame(dd)["dups_in_file"] == 1
