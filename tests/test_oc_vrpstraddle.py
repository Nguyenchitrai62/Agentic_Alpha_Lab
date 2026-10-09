"""oc_vrpstraddle tests: causality/truncation + hand-checked synthetic cases.

Run: .venv/Scripts/python.exe -m pytest tests/test_oc_vrpstraddle.py -q
"""
import math
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research/tournament/oc_vrpstraddle"))
import vrp as V
import run_vrp as R

H = 3_600_000_000_000
M = 60_000_000_000
YNS = 31_536_000_000_000_000  # ns per 365d year


def test_put_call_parity():
    # r = q = 0 => C - P = S - K exactly, several moneyness/vols.
    for S, K, T, s in [(50000, 50000, 7 / 365, 0.6), (60000, 50000, 7 / 365, 0.9),
                       (40000, 50000, 28 / 365, 0.4), (3000, 2950, 7 / 365, 1.2)]:
        assert abs(V.bs_call(S, K, T, s) - V.bs_put(S, K, T, s) - (S - K)) < 1e-6


def test_atm_straddle_approx():
    # Hand-check: ATM straddle ~= 0.8 * S * sigma * sqrt(T) (within 3%).
    S, T, s = 50000.0, 7 / 365, 0.6
    got = V.bs_straddle(S, S, T, s)
    approx = 0.8 * S * s * math.sqrt(T)
    assert abs(got / approx - 1) < 0.03, (got, approx)
    # ATM delta is small positive (d1 = 0.5*s*sqrt(T) > 0).
    d = V.bs_straddle_delta(S, S, T, s)
    assert 0.0 < d < 0.1, d


def test_delta_limits_and_expiry_step():
    assert abs(V.bs_straddle_delta(100000, 50000, 7 / 365, 0.6) - 1.0) < 0.01
    assert abs(V.bs_straddle_delta(20000, 50000, 7 / 365, 0.6) + 1.0) < 0.01
    assert V.bs_straddle_delta(60000, 50000, 0.0, 0.6) == 1.0
    assert V.bs_straddle_delta(40000, 50000, 0.0, 0.6) == -1.0
    # intrinsic fallbacks
    assert V.bs_call(60000, 50000, 7 / 365, 0.0) == 10000.0
    assert V.bs_put(40000, 50000, 7 / 365, -1.0) == 10000.0
    assert V.bs_call(40000, 50000, 7 / 365, 0.6) < 10.0  # 20% OTM, ~1bp of spot
    assert math.isnan(V.bs_call(float("nan"), 50000, 7 / 365, 0.6))


def test_fee_caps_and_settle():
    # cap binds on expensive leg, 0.125*price binds on cheap leg
    assert V.fee_per_side(50000, 1650.0) == 0.0003 * 50000  # 15 < 206.25
    assert V.fee_per_side(50000, 10.0) == 0.125 * 10.0
    assert V.settle_fee(50000, 0.0) == 0.0
    assert V.settle_fee(50000, 2000.0) == 0.00015 * 50000  # 7.5 < 250
    assert V.settle_fee(50000, 10.0) == 0.125 * 10.0


def test_strike_round_nearest_and_size():
    assert V.strike_round(67340, 1000) == 67000.0
    assert V.strike_round(67600, 1000) == 68000.0
    assert V.strike_round(3412, 50) == 3400.0
    assert V.size_q(1.0, 50000.0) == 0.5 / 50000.0
    assert V.size_q(2.0, 50000.0, 0.25) == 0.25 * 2.0 / 50000.0 / 2


def test_dvol_known_causal_truncation():
    # Value at T is unchanged when the panel is truncated to closes <= T.
    ms = np.arange(0, 48) * H  # hourly candle starts
    cl = 50.0 + np.arange(48, dtype=float)  # rising: leak would change values
    T = 30 * H
    full = R.dvol_known(ms, cl, T)
    keep = ms + H <= T
    trunc = R.dvol_known(ms[keep], cl[keep], T)
    assert full == trunc == cl[29]
    # a candle closing after T is not used
    assert R.dvol_known(ms, cl, T) != cl[30]


def _synth(S0=50000.0, dvol0=60.0, jump=None, dvol1=None, drift_end=None):
    """Synthetic BTC-only world on grid Fri 2021-10-01 04:00 -> 2021-10-09 12:00."""
    grid = pd.date_range(pd.Timestamp("2021-10-01 04:00", tz="UTC"),
                         pd.Timestamp("2021-10-09 12:00", tz="UTC"), freq="1h")
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    m0 = pd.Timestamp("2021-10-01 00:00", tz="UTC").value
    m1 = pd.Timestamp("2021-10-08 09:00", tz="UTC").value
    exp_ns = pd.Timestamp("2021-10-08 08:00", tz="UTC").value
    mns = np.arange(m0, m1 + 1, 60_000_000_000)
    cl = np.full(len(mns), S0)
    if drift_end is not None:
        w = np.clip((mns - m0) / (exp_ns - m0), 0, 1)
        cl = S0 + (drift_end - S0) * w
    if jump is not None:
        jt, jl = jump
        cl[mns >= jt] = jl
    d0 = pd.Timestamp("2021-09-30 00:00", tz="UTC").value
    dms = np.arange(d0, m1 + 1, H)
    dcl = np.full(len(dms), dvol0)
    if dvol1 is not None:
        ct, cv = dvol1
        dcl[dms >= ct] = cv
    data = {"BTC": {"iv_t0": np.array([d0]), "iv_put": np.array([np.nan]),
                     "iv_call": np.array([np.nan]),
                     "d_ms": dms, "d_cl": dcl, "m_ts": mns, "m_cl": cl}}
    px = np.array([R.px_at(mns, cl, int(t) - M)[0] for t in gn])
    dv = np.array([R.dvol_known(dms, dcl, int(t)) for t in gn])
    gh = {"BTC": {"px": px, "dv": dv, "otm": np.full(len(gn), np.nan)}}
    return grid, gh, data


def _btc_positions(grid, gh, data):
    with patch.object(R, "COINS", ["BTC"]):
        pos = R.build_positions(grid, gh, data, "V2")
    pos = [p for p in pos if not p.get("skip")]
    assert len(pos) == 1
    return pos[0]


def test_synthetic_flat_week_tp_late_profit():
    # Flat price at the strike: theta decays the ATM mark below 0.3 x premium
    # in the last ~36h, so TP (not expiry) exits with most of the premium kept.
    grid, gh, data = _synth()
    p = _btc_positions(grid, gh, data)
    assert p["K"] == 50000.0 and p["S"] == 50000.0
    T = (p["expiry_t"] - p["entry_t"]) / YNS
    hand = 2 * V.bs_call(50000, 50000, T, 0.97 * 0.6)
    assert abs(p["gross"] / hand - 1) < 1e-9
    assert p["exit_kind"] == "tp", p["exit_kind"]
    assert p["exit_step"] > p["expiry_step"] - 36  # late exit only
    assert p["pnl_u"] > 0.5 * p["gross"]  # most of the premium kept


def test_synthetic_jump_triggers_sl():
    jt = pd.Timestamp("2021-10-02 12:00", tz="UTC").value
    grid, gh, data = _synth(jump=(jt, 60000.0))
    p = _btc_positions(grid, gh, data)
    assert p["exit_kind"] == "sl", p["exit_kind"]
    assert p["exit_step"] < p["expiry_step"]
    assert p["pnl_u"] < 0


def test_synthetic_late_jump_expiry_settlement():
    # Slow +8% drift over the week: mark stays too high for TP (intrinsic
    # grows), loss too small for SL -> expiry with exactly-wired settlement.
    grid, gh, data = _synth(drift_end=54000.0)
    p = _btc_positions(grid, gh, data)
    assert p["exit_kind"] == "expiry", p["exit_kind"]
    assert p["S_settle"] > 53000.0
    fee_in = 2 * 0.0003 * p["S"]  # cap binds (0.125 x leg >> 15); S has drifted
    payoff = p["S_settle"] - 50000.0  # call ITM, put OTM
    stl = min(0.00015 * p["S_settle"], 0.125 * payoff)
    assert abs(p["pnl_u"] - (p["gross"] - fee_in - payoff - stl)) < 1e-6


def test_synthetic_iv_collapse_triggers_tp():
    ct = pd.Timestamp("2021-10-02 12:00", tz="UTC").value
    grid, gh, data = _synth(dvol1=(ct, 8.0))
    p = _btc_positions(grid, gh, data)
    assert p["exit_kind"] == "tp", p["exit_kind"]
    assert p["pnl_u"] > 0
