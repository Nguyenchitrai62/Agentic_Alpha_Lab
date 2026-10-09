"""oc_vrpgate tests: causality/truncation + hand-checked synthetic gate cases.

POST-HOC INFORMED study; tests verify causality, not profitability.
Run: .venv/Scripts/python.exe -m pytest tests/test_oc_vrpgate.py -q
"""
import math
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                        / "research/tournament/oc_vrpgate"))
import vrp as V
import run_gate as R

H = 3_600_000_000_000
M = 60_000_000_000
YNS = 31_536_000_000_000_000  # ns per 365d year


def test_put_call_parity():
    # r = q = 0 => C - P = S - K exactly.
    for S, K, T, s in [(50000, 50000, 7 / 365, 0.6), (60000, 50000, 7 / 365, 0.9),
                       (40000, 50000, 28 / 365, 0.4), (3000, 2950, 7 / 365, 1.2)]:
        assert abs(V.bs_call(S, K, T, s) - V.bs_put(S, K, T, s) - (S - K)) < 1e-6


def test_atm_straddle_approx():
    S, T, s = 50000.0, 7 / 365, 0.6
    got = V.bs_straddle(S, S, T, s)
    approx = 0.8 * S * s * math.sqrt(T)
    assert abs(got / approx - 1) < 0.03, (got, approx)


def test_fee_caps():
    assert V.fee_per_side(50000, 1650.0) == 0.0003 * 50000
    assert V.fee_per_side(50000, 10.0) == 0.125 * 10.0
    assert V.settle_fee(50000, 0.0) == 0.0
    assert V.settle_fee(50000, 2000.0) == 0.00015 * 50000


def test_gate_boundaries():
    # R087 never gates.
    assert R.gate_decision("R087", float("nan"), float("nan"), float("nan"))[0]
    # G1: gap >= 0.05 trades; NaN never trades. (Off-boundary values: the
    # frozen rule is an exact >=, so exact-boundary float dust is untested.)
    iv = 0.87 * 60.0 / 100.0
    assert R.gate_decision("G1", 60.0, iv - 0.051, 0.5)[0]
    assert not R.gate_decision("G1", 60.0, iv - 0.049, 0.5)[0]
    assert not R.gate_decision("G1", 60.0, float("nan"), 0.5)[0]
    assert not R.gate_decision("G1", float("nan"), 0.1, 0.1)[0]
    # G2: ratio >= 1.15 trades; NaN / zero RV never trades (frozen guard).
    assert R.gate_decision("G2", 60.0, 0.1, iv / 1.16)[0]
    assert not R.gate_decision("G2", 60.0, 0.1, iv / 1.14)[0]
    assert not R.gate_decision("G2", 60.0, 0.1, float("nan"))[0]
    assert not R.gate_decision("G2", 60.0, 0.1, 0.0)[0]


def test_rv_before_causal_truncation():
    # RV at t_gate is unchanged when the panel is truncated to bars < t_gate;
    # a spike after t_gate cannot leak in.
    t0 = pd.Timestamp("2021-09-01 00:00", tz="UTC").value
    mns = np.arange(t0, t0 + 40 * 86400 * 1_000_000_000, M)
    rng = np.random.default_rng(7)
    cl = 50000.0 * np.exp(np.cumsum(rng.normal(0, 0.0005, len(mns))))
    t_gate = pd.Timestamp("2021-09-25 08:00", tz="UTC").value
    full = R.rv_before(t_gate, mns, cl, 7, R.MIN_BARS_7)
    keep = mns < t_gate
    trunc = R.rv_before(t_gate, mns[keep], cl[keep], 7, R.MIN_BARS_7)
    assert np.isfinite(full) and full == trunc
    # spike strictly after t_gate changes nothing
    cl2 = cl.copy()
    cl2[mns >= t_gate] *= 1.5
    assert R.rv_before(t_gate, mns, cl2, 7, R.MIN_BARS_7) == full
    # short history => NaN (coverage rule)
    assert np.isnan(R.rv_before(t_gate, mns[-100:], cl[-100:], 7, R.MIN_BARS_7))
    # dvol_known is strictly as-of too
    ms = np.arange(0, 48) * H
    dcl = 50.0 + np.arange(48, dtype=float)
    T = 30 * H
    assert R.dvol_known(ms, dcl, T) == R.dvol_known(ms[ms + H <= T], dcl[ms + H <= T], T)


def _synth(S0=50000.0, dvol0=60.0, pre=None):
    """Synthetic BTC-only world: 1m from 2021-08-31, grid Fri 2021-10-01 04:00
    -> 2021-10-09 12:00 (single Friday 2021-10-01). pre='noisy'|'wild' alters
    the 7d/30d lookback before the Friday 08:00 gate."""
    grid = pd.date_range(pd.Timestamp("2021-10-01 04:00", tz="UTC"),
                         pd.Timestamp("2021-10-09 12:00", tz="UTC"), freq="1h")
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    m0 = pd.Timestamp("2021-08-31 00:00", tz="UTC").value
    m1 = pd.Timestamp("2021-10-08 09:00", tz="UTC").value
    mns = np.arange(m0, m1 + 1, M)
    cl = np.full(len(mns), S0)
    t_gate = pd.Timestamp("2021-10-01 08:00", tz="UTC").value
    if pre == "noisy":  # +-0.01% alternating in the lookback: per-minute
        # std ~0.0002 -> RV ~0.145, gap ~+0.38, ratio ~3.6 (both gates pass)
        alt = ((np.arange(len(mns)) % 2) * 2 - 1).astype(float)
        cl[mns < t_gate] = S0 * (1 + 0.0001 * alt[mns < t_gate])
    elif pre == "wild":  # +-2% alternating -> RV7/RV30 >> DVOL
        alt = ((np.arange(len(mns)) % 2) * 2 - 1).astype(float)
        cl[mns < t_gate] = S0 * (1 + 0.02 * alt[mns < t_gate])
    d0 = pd.Timestamp("2021-08-30 00:00", tz="UTC").value
    dms = np.arange(d0, m1 + 1, H)
    dcl = np.full(len(dms), dvol0)
    data = {"BTC": {"d_ms": dms, "d_cl": dcl, "m_ts": mns, "m_cl": cl}}
    px = np.array([R.px_at(mns, cl, int(t) - M)[0] for t in gn])
    dv = np.array([R.dvol_known(dms, dcl, int(t)) for t in gn])
    gh = {"BTC": {"px": px, "dv": dv}}
    return grid, gh, data


def _btc_traded(grid, gh, data, row):
    with patch.object(R, "COINS", ["BTC"]):
        pos = R.build_positions(grid, gh, data, row)
    return [p for p in pos if not p.get("skip")]


def test_synthetic_flat_week_r087_and_g1_trade_g2_skips_on_zero_rv():
    grid, gh, data = _synth()
    r087 = _btc_traded(grid, gh, data, "R087")
    assert len(r087) == 1
    assert r087[0]["K"] == 50000.0 and r087[0]["S"] == 50000.0
    T = (r087[0]["expiry_t"] - r087[0]["entry_t"]) / YNS
    hand = 2 * V.bs_call(50000, 50000, T, 0.97 * 0.87 * 0.6)
    assert abs(r087[0]["gross"] / hand - 1) < 1e-9  # r=0.87 in the price
    assert r087[0]["exit_kind"] == "tp"  # flat week decays into TP
    # flat lookback: RV7 = RV30 = 0 -> gap huge (G1 trades), ratio guarded (G2 skips)
    g1 = _btc_traded(grid, gh, data, "G1")
    assert len(g1) == 1 and g1[0]["gap7"] > 0.5
    g2 = _btc_traded(grid, gh, data, "G2")
    assert len(g2) == 0


def test_synthetic_noisy_week_both_gates_trade():
    grid, gh, data = _synth(pre="noisy")
    g1 = _btc_traded(grid, gh, data, "G1")
    g2 = _btc_traded(grid, gh, data, "G2")
    assert len(g1) == 1 and len(g2) == 1
    assert g1[0]["gap7"] >= 0.05 and g2[0]["ratio30"] >= 1.15


def test_synthetic_wild_week_both_gates_skip_r087_trades():
    grid, gh, data = _synth(pre="wild")
    assert len(_btc_traded(grid, gh, data, "R087")) == 1
    assert len(_btc_traded(grid, gh, data, "G1")) == 0
    assert len(_btc_traded(grid, gh, data, "G2")) == 0
