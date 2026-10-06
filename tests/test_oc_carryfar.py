"""Tests for oc_carryfar (FAR tenor: second-next quarterly at the same roll times)."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_carryfar"


def _res():
    return json.loads((HERE / "results.json").read_text())


def test_base_repro_matches_frozen():
    out = _res()
    frozen = json.loads((ROOT / "research/tournament/oc_cashcarry/results.json").read_text())
    frozen_bybit = json.loads(
        (ROOT / "research/data_fetch/bybitq/results_bybit_carry.json").read_text())
    assert abs(out["binance"]["base"]["pooled"]["sum_ret_alloc"]
               - frozen["pooled"]["sum_ret_alloc"]) < 1e-6
    assert abs(out["bybit_inverse"]["base"]["pooled"]["sum_ret_alloc"]
               - frozen_bybit["inverse"]["pooled"]["sum_ret_alloc"]) < 1e-6
    assert out["binance"]["base"]["n_trades"] == 33
    assert out["bybit_inverse"]["base"]["n_trades"] == frozen_bybit["inverse"]["n_trades"]
    assert out["meta"]["base_repro"]["match"] is True


def test_far_threshold_respected():
    out = _res()
    for venue in ("binance", "bybit_inverse"):
        for t in out[venue]["far"]["trades"]:
            assert t["ann_basis"] >= 0.04 - 1e-9, (venue, t)


def test_far_fee_math_handcheck():
    out = _res()
    trades = out["binance"]["far"]["trades"][:6] + out["binance"]["far"]["trades"][-4:] \
        + out["bybit_inverse"]["far"]["trades"][:6]
    for t in trades:
        gross = ((t["S_del"] - t["S_entry"]) / t["S_entry"]
                 + (t["F_entry"] - t["S_del"]) / t["F_entry"])
        assert abs(t["ret_alloc"] - round(gross - 0.00275, 6)) < 1e-9, t
        dte = t["dte_days"]
        basis = float(np.log(t["F_entry"] / t["S_entry"]) * 365.0 / dte)
        assert abs(basis - t["ann_basis"]) < 5e-6, t


def test_far_holds_longer_than_base():
    out = _res()
    for venue in ("binance", "bybit_inverse"):
        fb = np.mean([t["dte_days"] for t in out[venue]["base"]["trades"]])
        ff = np.mean([t["dte_days"] for t in out[venue]["far"]["trades"]])
        assert ff > fb, (venue, fb, ff)


def test_overlap_reported_and_bounded():
    out = _res()
    glo = out["binance"]["far"]["overlap"]
    assert glo["BTC"]["max_open"] <= 2 and glo["ETH"]["max_open"] <= 2
    assert glo["total"]["max_open"] <= 4
    glo_i = out["bybit_inverse"]["far"]["overlap"]
    # live venue transiently reaches 3 per coin / 6 total in roll weeks (reported)
    assert glo_i["total"]["max_open"] == 6
    for venue in ("binance", "bybit_inverse"):
        for arm in ("base", "far"):
            for y in out[venue][arm]["years"]:
                assert "max_open_pairs" in y, (venue, arm, y["year"])
                assert y["max_open_pairs"]["total"] <= out[venue][arm]["overlap"]["total"]["max_open"]


def test_h2h_and_verdict_rule():
    out = _res()
    assert out["binance"]["head_to_head"]["far_win_years"] == 4
    assert out["bybit_inverse"]["head_to_head"]["far_win_years"] == 4
    assert out["meta"]["margin_ok_f025_no_blocked_both_venues"] is True
    for mkey in ("margin_bin", "margin_inv"):
        assert out[mkey]["0.25"]["blocked_any"] is False
        assert out[mkey]["0.25"]["worst_IM_over_balance"] < 0.95
    assert out["verdict"].startswith("FAR BETTER")


def test_far_entry_causal_spot_check():
    """One long-hold FAR entry recomputed from truncated data (closes <= entry)."""
    out = _res()
    cands = [t for t in out["binance"]["far"]["trades"] if t["dte_days"] > 150]
    assert cands
    t = cands[0]
    coin = t["coin"]
    s = pd.read_parquet(ROOT / f"data/raw/spot_majors_20260925/{coin}USDT_spot_4h.parquet",
                         columns=["open_time", "close", "close_time"])
    s["open_time"] = pd.to_datetime(s["open_time"], utc=True)
    s["close_time"] = pd.to_datetime(s["close_time"], utc=True)
    te = pd.Timestamp(t["entry_open"], tz="UTC")
    trunc = s[s["open_time"] <= te]
    assert abs(float(trunc["close"].iloc[-1]) - t["S_entry"]) < 1e-9
    assert float(s["close"].iloc[-1]) != float(trunc["close"].iloc[-1])


def test_far_settlement_is_delivery_bar_spot_close():
    out = _res()
    t = next(r for r in out["binance"]["far"]["trades"]
             if r["coin"] == "BTC" and r["delivery"] == "2024-03-29")
    s = pd.read_parquet(ROOT / "data/raw/spot_majors_20260925/BTCUSDT_spot_4h.parquet",
                         columns=["open_time", "close", "close_time"])
    s["open_time"] = pd.to_datetime(s["open_time"], utc=True)
    s["close_time"] = pd.to_datetime(s["close_time"], utc=True)
    D = pd.Timestamp("2024-03-29 08:00", tz="UTC")
    bars = s[(s["open_time"] <= D) & (D < s["close_time"])]
    assert len(bars) == 1
    assert abs(float(bars["close"].iloc[0]) - t["S_del"]) < 1e-9


def test_no_1m():
    src = (HERE / "analyze_carryfar.py").read_text()
    for bad in ("intraday_20260924", "intraday_20260930", "premium_1m",
                "klines_1m", "aggflow", "_1m.parquet"):
        assert bad not in src, bad


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text()
    out = _res()
    assert "FAR BETTER" in rep and out["verdict"].startswith("FAR BETTER")
    for venue in ("binance", "bybit_inverse"):
        assert str(out[venue]["far"]["pooled"]["sum_ret_alloc"]) in rep
        assert str(out[venue]["base"]["pooled"]["sum_ret_alloc"]) in rep
    assert "1.5x equity" in rep  # live-venue 6-pair transient disclosed
    plan = (HERE / "PLAN.md").read_text()
    assert "SECOND-next" in plan and "FAR BETTER only if" in plan
