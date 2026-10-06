"""Tests for oc_carrymore (same-rule extension to Binance COIN-M BNB/SOL/XRP)."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research" / "tournament" / "oc_carrymore"
CC = ROOT / "research" / "tournament" / "oc_cashcarry"
CCP = ROOT / "research" / "tournament" / "oc_carrycompound"


def _res():
    return json.loads((HERE / "results.json").read_text())


def test_inventory_and_manifest():
    man = json.loads((HERE / "MANIFEST.json").read_text())
    n_cm = sum(len(v) for v in man["inventory"].values())
    assert n_cm == 112, n_cm
    assert set(man["inventory"]) == {"BTC", "ETH", "BNB", "SOL", "XRP"}
    sol = man["inventory"]["SOL"]
    assert len(sol) == 10 and sol[0]["delivery"] == "2024-09-27", sol[0]
    assert man["um_quarterly_coins"] == ["BTC", "ETH"]
    assert man["verify"]["missing"] == [] and man["verify"]["mismatch"] == []
    out = _res()
    assert out["inventory"]["BTC"]["n_contracts"] == 26
    assert out["inventory"]["SOL"]["n_contracts"] == 10
    assert out["inventory"]["BNB"]["n_contracts"] == 25
    assert out["inventory"]["XRP"]["n_contracts"] == 25


def test_threshold_and_fee_math():
    out = _res()
    assert len(out["trades"]) == 55
    for t in out["trades"]:
        assert t["ann_basis"] >= 0.04 - 1e-9, t
        assert t["ret_alloc"] > 0, t
    for t in out["trades"][:8] + out["trades"][-4:]:
        gross = ((t["S_del"] - t["S_entry"]) / t["S_entry"]
                 + (t["F_entry"] - t["S_del"]) / t["F_entry"])
        assert abs(t["ret_alloc"] - round(gross - 0.00275, 6)) < 1e-9, t


def test_entry_causal_spot_check():
    out = _res()
    t = next(r for r in out["trades"] if r["coin"] == "XRP" and r["delivery"] == "2024-06-28")
    s = pd.read_parquet(ROOT / "data/raw/spot_majors_20260925/XRPUSDT_spot_4h.parquet",
                        columns=["open_time", "close", "close_time"])
    s["open_time"] = pd.to_datetime(s["open_time"], utc=True)
    te = pd.Timestamp(t["entry_open"], tz="UTC")
    trunc = s[s["open_time"] <= te]
    assert abs(float(trunc["close"].iloc[-1]) - t["S_entry"]) < 1e-9
    assert float(s["close"].iloc[-1]) != float(trunc["close"].iloc[-1])


def test_settlement_is_delivery_bar_spot_close():
    out = _res()
    t = next(r for r in out["trades"] if r["coin"] == "BNB" and r["delivery"] == "2025-03-28")
    s = pd.read_parquet(ROOT / "data/raw/spot_majors_20260925/BNBUSDT_spot_4h.parquet",
                        columns=["open_time", "close", "close_time"])
    s["open_time"] = pd.to_datetime(s["open_time"], utc=True)
    s["close_time"] = pd.to_datetime(s["close_time"], utc=True)
    D = pd.Timestamp("2025-03-28 08:00", tz="UTC")
    bars = s[(s["open_time"] <= D) & (D < s["close_time"])]
    assert len(bars) == 1
    assert abs(float(bars["close"].iloc[0]) - t["S_del"]) < 1e-9


def test_year_sums_match_trades():
    out = _res()
    tot = 0.0
    for y in out["cm_all_years"]:
        s = sum(r for _, _, _, r, _ in y["trades"])
        assert abs(s - y["sum_ret_alloc"]) < 1e-6, y["year"]
        tot += s
    assert abs(tot - out["cm_all_pooled"]["sum_ret_alloc"]) < 1e-6
    assert out["cm_all_pooled"]["n_trades"] == 36
    assert out["cm_btceth_pooled"]["n_trades"] == 22


def test_sanity_cm_vs_um():
    out = _res()
    san = out["sanity_cm_vs_um_btceth"]
    assert san["n_common_deliveries"] >= 25
    assert san["mean_abs_basis_diff"] < 0.03
    assert san["mean_abs_ret_diff"] < 0.02
    assert abs(out["cm_btceth_pooled"]["sum_ret_alloc"] - 0.509149) < 1e-6
    cc = json.loads((CC / "results.json").read_text())
    assert abs(cc["pooled"]["sum_ret_alloc"] - 0.523436) < 1e-6


def test_compound_reproduces_and_extends():
    out = _res()
    ccp = json.loads((CCP / "results.json").read_text())
    um = out["compound"]["G2_um_BTC+ETH_f0.25_reproduces_oc_carrycompound"]
    exp = ccp["rows"]["G2_f0.25"]
    assert um["R"] == exp["R"] == 5.634
    assert um["W"] == exp["W"] and um["DD"] == exp["DD"]
    assert um["full_path_dd"] == exp["full_path_dd"]
    be = out["compound"]["G2_cm_BTC+ETH_f0.25"]
    assert be["R"] == 5.626 and be["losing"] == 0
    assert abs(be["R"] - um["R"]) < 0.05  # venue check: cm ~= um
    allr = out["compound"]["G2_cm_ALL_f0.25"]
    assert allr["R"] == 5.771 and allr["W"] == 2.853
    assert allr["DD"] == 16.91 and allr["losing"] == 0
    assert allr["full_path_dd"]["full"] == 16.82
    assert out["compound"]["carry_add_pp"]["cm_ALL"] == 0.361


def test_capital_flags():
    out = _res()
    be, allr = out["capital"]["cm_BTC+ETH"], out["capital"]["cm_ALL"]
    assert be["needs_borrow"] is False and be["spot_cash_vs_equity"] <= 1.0
    assert allr["needs_borrow"] is True and allr["spot_cash_vs_equity"] == 2.0


def test_no_1m_and_posthoc_label():
    src = (HERE / "analyze_carrymore.py").read_text()
    for bad in ("intraday_20260924", "intraday_20260930", "premium_1m",
                "klines_1m", "aggflow", "_1m.parquet"):
        assert bad not in src, bad
    assert "POST-HOC" in json.dumps(_res()["meta"])
    rep = (HERE / "REPORT.md").read_text()
    for needle in ("5.771", "2.853", "16.82", "+0.361", "NEEDS BORROW",
                   "POST-HOC", "Ket luan tieng Viet"):
        assert needle in rep, needle
