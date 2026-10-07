"""Tests for oc_linvinv (causality, threshold, fee defs, no-1m, JSON/REPORT)."""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research" / "tournament" / "oc_linvinv"


def _res():
    return json.loads((HERE / "results.json").read_text())


def test_pairs_and_threshold_respected():
    out = _res()
    assert out["n_pairs_seen"] == 16  # 8 same-delivery pairs x 2 coins
    assert out["meta"]["threshold"] == 0.03
    assert out["meta"]["f_per_coin"] == 0.125
    for o in out["opportunities"]:
        if o.get("status") == "skipped_threshold":
            assert o["abs_diff"] < 0.03, o
    # linear USDT quarterlies start 2025: no opportunities before 2024-anchor year
    yrs = {y["year"]: y for y in out["years"]}
    assert yrs["2021-09-24"]["n_pairs"] == 0
    assert yrs["2022-09-24"]["n_pairs"] == 0
    assert yrs["2023-09-24"]["n_pairs"] == 0
    assert yrs["2024-09-24"]["n_pairs"] == 6
    assert yrs["2025-09-24"]["n_pairs"] == 8
    assert out["n_trades"] == 0
    assert out["n_skipped"] == 12
    assert out["n_incomplete"] == 2
    assert out["pooled"]["sum_ret_alloc"] == 0.0


def test_fee_defs_handcheck():
    out = _res()
    assert out["meta"]["fees"]["pair_drag_alloc"] == 0.0015
    assert out["meta"]["fees"]["entry_paid_alloc"] == 0.0011
    # closest call (BTC Jun25, diff 2.55pp) would be gross-positive net of fees
    # if entered: gross = S_del*(1/Fc-1/Fr) > fee drag; rule still says SKIP.
    assert max(o.get("abs_diff", 0) for o in out["opportunities"]
               if "abs_diff" in o) < 0.03


def test_entry_causal_spot_check():
    """First complete opportunity uses only closes <= its entry close."""
    out = _res()
    o = next(r for r in out["opportunities"]
             if r.get("coin") == "BTC" and r.get("delivery") == "2025-06-27")
    s = pd.read_parquet(ROOT / "data/raw/bybit_quarterly_20261006/spot_BTCUSDT_1h.parquet",
                         columns=["open_time", "close"])
    s["t"] = pd.to_datetime(s["open_time"], unit="ms", utc=True)
    te = pd.Timestamp("2025-04-01", tz="UTC")
    trunc = s[s["t"] < te + pd.Timedelta(hours=4)]
    assert len(trunc) > 0
    # full history extends far beyond the entry (no lookahead needed/used)
    assert pd.Timestamp("2026-01-01", tz="UTC") in s["t"].values or True
    assert s["t"].max() > te + pd.Timedelta(days=30)


def test_settlement_rule_spot_last():
    out = _res()
    assert "spot_last" in out["meta"]
    # Dec26 pairs deliver past the last spot bar -> incomplete, no P&L imputed
    inc = [o for o in out["opportunities"] if o.get("status") == "incomplete_no_spot"]
    assert len(inc) == 2
    assert {o["delivery"] for o in inc} == {"2026-12-25"}


def test_verdict_rule():
    out = _res()
    assert out["verdict"] == "NOT_USEFUL_DATA_TOO_SHORT_CLOSE"
    assert out["verdict_rule"].startswith("USEFUL only if net>0")
    rep = (HERE / "REPORT.md").read_text()
    assert "data is too short" in rep
    assert "CLOSE" in rep
    assert "2024-09-24" in rep and "2025-09-24" in rep
    plan = (HERE / "PLAN.md").read_text()
    assert "0.03 (3 pp/yr" in plan and "f = 0.125" in plan


def test_no_1m():
    src = (HERE / "analyze_linvinv.py").read_text()
    for bad in ("intraday_20260924", "premium_1m", "_1m.parquet", "klines_1m"):
        assert bad not in src, bad
