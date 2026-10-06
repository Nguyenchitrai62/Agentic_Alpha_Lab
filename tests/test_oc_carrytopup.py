"""Tests for oc_carrytopup (7d delivery-week top-up: causality, fees, cash, verdict)."""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_carrytopup"


def _res():
    return json.loads((HERE / "results.json").read_text())


def test_threshold_and_counts():
    out = _res()
    b, i = out["binance"], out["bybit_inverse"]
    for t in b["trades"] + i["trades"]:
        assert t["ann_basis"] >= 0.04 - 1e-9, t
        assert 6.0 < t["dte_days"] <= 7.5, t  # 7d window respected
    assert (b["n_contracts_seen"], b["n_trades"], b["n_skipped"]) == (50, 14, 32)
    assert (b["n_no_overlap"], b["n_incomplete"]) == (4, 0)
    assert (i["n_contracts_seen"], i["n_trades"], i["n_skipped"]) == (48, 13, 29)
    assert (i["n_no_overlap"], i["n_incomplete"]) == (4, 0)
    assert out["meta"]["f_topup"] == 0.125


def test_fee_math_handcheck():
    out = _res()
    for t in out["binance"]["trades"][:6] + out["bybit_inverse"]["trades"][:6]:
        gross = ((t["S_del"] - t["S_entry"]) / t["S_entry"]
                 + (t["F_entry"] - t["S_del"]) / t["F_entry"])
        assert abs(t["ret_alloc"] - round(gross - 0.00275, 6)) < 1e-9, t


def test_entry_causal_spot_check():
    """Recompute one 7d entry from truncated data (closes <= entry)."""
    out = _res()
    t = next(r for r in out["binance"]["trades"]
             if r["coin"] == "BTC" and r["delivery"] == "2024-03-29")
    s = pd.read_parquet(ROOT / "data/raw/spot_majors_20260925/BTCUSDT_spot_4h.parquet",
                         columns=["open_time", "close", "close_time"])
    s["open_time"] = pd.to_datetime(s["open_time"], utc=True)
    s["close_time"] = pd.to_datetime(s["close_time"], utc=True)
    te = pd.Timestamp(t["entry_open"], tz="UTC")
    trunc = s[s["open_time"] <= te]
    assert abs(float(trunc["close"].iloc[-1]) - t["S_entry"]) < 1e-9
    assert float(s["close"].iloc[-1]) != float(trunc["close"].iloc[-1])
    # entry is ~7d before delivery
    assert pd.Timestamp("2024-03-29 08:00", tz="UTC") - te <= pd.Timedelta(days=8)


def test_settlement_is_delivery_bar_spot_close():
    out = _res()
    t = next(r for r in out["binance"]["trades"]
             if r["coin"] == "BTC" and r["delivery"] == "2024-03-29")
    s = pd.read_parquet(ROOT / "data/raw/spot_majors_20260925/BTCUSDT_spot_4h.parquet",
                         columns=["open_time", "close", "close_time"])
    s["open_time"] = pd.to_datetime(s["open_time"], utc=True)
    s["close_time"] = pd.to_datetime(s["close_time"], utc=True)
    D = pd.Timestamp("2024-03-29 08:00", tz="UTC")
    bars = s[(s["open_time"] <= D) & (D < s["close_time"])]
    assert len(bars) == 1
    assert abs(float(bars["close"].iloc[0]) - t["S_del"]) < 1e-9


def test_year_sums_and_verdict_inputs():
    out = _res()
    for v in (out["binance"], out["bybit_inverse"]):
        tot = 0.0
        for y in v["years"]:
            s = sum(r for _, _, _, r, _ in y["trades"])
            assert abs(s - y["sum_ret_alloc"]) < 1e-6, y["year"]
            assert abs(0.125 * s * 100 / 12 - y["contrib_acct_pct"]["per_month_pct"]) < 1e-3
            tot += s
        assert abs(tot - v["pooled"]["sum_ret_alloc"]) < 1e-6
        assert v["pooled"]["n_years_positive"] == 0
    vi = out["verdict_inputs"]
    assert vi["binance_years_positive"] == 0 and vi["bybit_years_positive"] == 0
    assert vi["borrow_binance"] is True and vi["borrow_bybit"] is True
    assert out["cash"]["binance"]["max_C_live"] > 1.0
    assert out["cash"]["bybit_inverse"]["max_C_live"] > 1.0
    assert out["suggested_verdict"] == "CLOSE"


def test_no_1m():
    src = (HERE / "analyze_carrytopup.py").read_text()
    for bad in ("intraday_20260924", "intraday_20260930", "premium_1m",
                "klines_1m", "aggflow", "_1m.parquet"):
        assert bad not in src, bad


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text()
    out = _res()
    assert "CLOSE" in rep and "USEFUL" in rep  # verdict line present
    assert str(out["binance"]["pooled"]["sum_ret_alloc"]) in rep
    assert str(out["bybit_inverse"]["pooled"]["sum_ret_alloc"]) in rep
    assert str(out["cash"]["binance"]["max_C_live"]) in rep
    for y in out["binance"]["years"] + out["bybit_inverse"]["years"]:
        assert y["year"] in rep
    plan = (HERE / "PLAN.md").read_text()
    assert "0.04 (4 %/yr" in plan and "USEFUL iff" in plan
