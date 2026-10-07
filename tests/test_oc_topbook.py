"""Offline unit tests for oc_topbook pure helpers (no network, no repo data)."""
import importlib.util
import sys
from pathlib import Path

import pandas as pd

MOD = Path(__file__).resolve().parents[1] / "research/tournament/oc_topbook/load_topbook.py"
spec = importlib.util.spec_from_file_location("oc_topbook_load", MOD)
tb = importlib.util.module_from_spec(spec)
sys.modules["oc_topbook_load"] = tb
spec.loader.exec_module(tb)


def test_spread_bps_midpoint_math():
    out = tb.spread_bps(pd.Series([100.0]), pd.Series([100.01]))
    assert abs(float(out.iloc[0]) - 0.99995) < 1e-6


def test_sizes_usd_multiply():
    bu, au = tb.sizes_usd(pd.Series([10.0]), pd.Series([2.0]),
                           pd.Series([11.0]), pd.Series([3.0]))
    assert float(bu.iloc[0]) == 20.0 and float(au.iloc[0]) == 33.0


def test_valid_mask_rejects_crossed_and_nonpositive():
    df = pd.DataFrame({"bid": [1.0, 2.0, 1.0, 1.0], "bid_qty": [1.0, 1.0, 0.0, 1.0],
                       "ask": [1.1, 2.0, 1.1, -1.0], "ask_qty": [1.0, 1.0, 1.0, 1.0]})
    assert tb.valid_mask(df).tolist() == [True, False, False, False]


def test_minute_floor_ms():
    ms = pd.Series([60_000, 119_999, 120_000])
    assert tb.minute_floor_ms(ms).tolist() == [60_000, 60_000, 120_000]


def test_floor_4h_ms():
    m = pd.Timestamp("2026-10-05T05:37:00Z").value // 10 ** 6
    floored = tb.floor_4h_ms(pd.Series([m])).iloc[0]
    assert pd.Timestamp(floored, unit="ms", tz="UTC") == pd.Timestamp("2026-10-05T04:00:00Z")


def test_coverage_gaps_flags_only_big_gaps():
    cov = pd.DataFrame({"venue": ["binance"] * 3, "start_ms": [0, 60_000, 300_000],
                        "end_ms": [60_000, 120_000, 360_000]})
    g = tb.coverage_gaps(cov, gap_ms=60_000)
    assert len(g) == 1 and abs(float(g.iloc[0]["gap_ms"]) - 180_000) < 1e-9


def test_aggregate_book_table_spread_and_wide():
    df = pd.DataFrame({
        "bucket_ms": [60_000, 60_000, 3_660_000],
        "venue": ["binance", "binance", "bybit"],
        "symbol": ["BTCUSDT"] * 3,
        "spread_bps": [1.0, 9.0, 2.0],
        "bid_usd": [100.0, 200.0, 50.0],
        "ask_usd": [110.0, 210.0, 55.0]})
    out = tb.aggregate_book_table(df)
    row = out[(out["bucket_ms"] == 60_000) & (out["venue"] == "binance")].iloc[0]
    assert row["n"] == 2 and abs(row["spread_mean_bps"] - 5.0) < 1e-9
    assert abs(row["spread_max_bps"] - 9.0) < 1e-9
    assert abs(row["frac_wide"] - 0.5) < 1e-9
    assert abs(row["bid_usd_mean"] - 150.0) < 1e-9


def test_lag_summary_reports_negatives():
    s = tb.lag_summary(pd.Series([-100, -50, 200]))
    assert s["n"] == 3 and s["median"] == -50.0
    assert abs(s["share_negative"] - 2 / 3) < 1e-3
