"""Tests for oc_cashcarry (causality, fee math, threshold, no-1m, JSON/REPORT)."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_cashcarry"


def _res():
    return json.loads((HERE / "results.json").read_text())


def test_threshold_respected():
    out = _res()
    for t in out["trades"]:
        assert t["ann_basis"] >= 0.04 - 1e-9, t
    assert out["n_trades"] == 33  # 25 in-window + 8 pre-window
    assert out["pooled"]["n_trades"] == 25
    assert out["n_skipped"] == 13
    assert out["n_incomplete"] == 2


def test_fee_math_handcheck():
    out = _res()
    for t in out["trades"][:8] + out["trades"][-4:]:
        gross = ((t["S_del"] - t["S_entry"]) / t["S_entry"]
                 + (t["F_entry"] - t["S_del"]) / t["F_entry"])
        expect = round(gross - 0.00275, 6)
        assert abs(t["ret_alloc"] - expect) < 1e-9, t


def test_entry_causal_spot_check():
    """Recompute one mid-history entry from truncated data (closes <= entry)."""
    out = _res()
    t = next(r for r in out["trades"]
             if r["coin"] == "BTC" and r["delivery"] == "2023-06-30")
    s = pd.read_parquet(ROOT / "data/raw/spot_majors_20260925/BTCUSDT_spot_4h.parquet",
                        columns=["open_time", "close", "close_time"])
    s["open_time"] = pd.to_datetime(s["open_time"], utc=True)
    s["close_time"] = pd.to_datetime(s["close_time"], utc=True)
    te = pd.Timestamp(t["entry_open"], tz="UTC")
    trunc = s[s["open_time"] <= te]
    assert abs(float(trunc["close"].iloc[-1]) - t["S_entry"]) < 1e-9
    # full-history last row must not leak into the truncated entry value
    assert float(s["close"].iloc[-1]) != float(trunc["close"].iloc[-1])


def test_settlement_is_delivery_bar_spot_close():
    out = _res()
    t = next(r for r in out["trades"]
             if r["coin"] == "ETH" and r["delivery"] == "2024-03-29")
    s = pd.read_parquet(ROOT / "data/raw/spot_majors_20260925/ETHUSDT_spot_4h.parquet",
                        columns=["open_time", "close", "close_time"])
    s["open_time"] = pd.to_datetime(s["open_time"], utc=True)
    s["close_time"] = pd.to_datetime(s["close_time"], utc=True)
    D = pd.Timestamp("2024-03-29 08:00", tz="UTC")
    bars = s[(s["open_time"] <= D) & (D < s["close_time"])]
    assert len(bars) == 1
    assert abs(float(bars["close"].iloc[0]) - t["S_del"]) < 1e-9


def test_year_sums_match_trades():
    out = _res()
    tot = 0.0
    for y in out["years"]:
        s = sum(r for _, _, _, r, _ in y["trades"])
        assert abs(s - y["sum_ret_alloc"]) < 1e-6, y["year"]
        tot += s
    assert abs(tot - out["pooled"]["sum_ret_alloc"]) < 1e-6
    assert out["pooled"]["per_f"]["0.25"]["geom_per_month_pct"] >= 0.10
    # verdict rule inputs: year-worst account MtM at f=0.25 >= -1.0%
    worst = min(y["worst_acct_pct"]["0.25"] for y in out["years"])
    assert worst >= -1.0, worst
    for f in ("0.25", "0.5"):
        assert out["margin"][f]["blocked_any"] is False
        assert out["margin"][f]["worst_IM_over_equity"] < 0.95


def test_no_1m():
    src = (HERE / "analyze_cashcarry.py").read_text()
    for bad in ("intraday_20260924", "intraday_20260930", "premium_1m",
                "klines_1m", "aggflow", "_1m.parquet"):
        assert bad not in src, bad


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text()
    out = _res()
    assert "USEFUL ADD-ON: YES" in rep
    for y in out["years"]:
        assert y["year"] in rep
        assert f'{y["sum_ret_alloc"]:.4f}' in rep or str(y["sum_ret_alloc"]) in rep
    assert str(out["pooled"]["per_f"]["0.25"]["geom_per_month_pct"]) in rep
    plan = (HERE / "PLAN.md").read_text()
    assert "0.04 (4 %/yr" in plan and "USEFUL ADD-ON" in plan
