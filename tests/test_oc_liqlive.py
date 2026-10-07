"""Offline unit tests for oc_liqlive pure helpers (no network, no repo data)."""
import importlib.util
import sys
from pathlib import Path

import pandas as pd

MOD = Path(__file__).resolve().parents[1] / "research/tournament/oc_liqlive/load_liq.py"
spec = importlib.util.spec_from_file_location("oc_liqlive_load", MOD)
liq = importlib.util.module_from_spec(spec)
sys.modules["oc_liqlive_load"] = liq
spec.loader.exec_module(liq)


def test_minute_floor_ms():
    ms = pd.Series([60_000, 119_999, 120_000])
    assert liq.minute_floor_ms(ms).tolist() == [60_000, 60_000, 120_000]


def test_floor_4h_ms():
    m = pd.Timestamp("2026-10-05T05:37:00Z").value // 10 ** 6
    floored = liq.floor_4h_ms(pd.Series([m])).iloc[0]
    assert pd.Timestamp(floored, unit="ms", tz="UTC") == pd.Timestamp("2026-10-05T04:00:00Z")


def test_coverage_gaps_flags_only_big_gaps():
    cov = pd.DataFrame({"venue": ["binance"] * 3, "start_ms": [0, 60_000, 300_000],
                        "end_ms": [60_000, 120_000, 360_000]})
    g = liq.coverage_gaps(cov, gap_ms=60_000)
    assert len(g) == 1 and abs(float(g.iloc[0]["gap_ms"]) - 180_000) < 1e-9


def test_aggregate_event_table_sums_and_side_split():
    df = pd.DataFrame({
        "bucket_ms": [60_000, 60_000, 3_660_000],
        "venue": ["binance", "binance", "bybit"],
        "symbol": ["BTCUSDT"] * 3,
        "side": ["long", "short", "long"],
        "notional_usd": [100.0, 300.0, 50.0]})
    out = liq.aggregate_event_table(df)
    row = out[(out["bucket_ms"] == 60_000) & (out["venue"] == "binance")].iloc[0]
    assert row["n"] == 2 and abs(row["total_notional"] - 400.0) < 1e-9
    assert row["n_long"] == 1 and row["n_short"] == 1
    assert abs(row["long_notional"] - 100.0) < 1e-9
    assert abs(row["short_notional"] - 300.0) < 1e-9


def test_covered_minutes_per_venue():
    cov = pd.DataFrame({"venue": ["binance", "binance"],
                        "start_ms": [0, 300_000], "end_ms": [60_000, 360_000]})
    mins = liq.covered_minutes_per_venue(cov)
    assert mins["binance"] == {0, 300_000}


def test_skew_summary_reports_negatives():
    s = liq.skew_summary(pd.Series([-100, -50, 200]))
    assert s["n"] == 3 and s["median"] == -50.0
    assert abs(s["share_negative"] - 2 / 3) < 1e-3
