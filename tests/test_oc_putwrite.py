"""oc_putwrite tests: BS/fee/strike hand-checks + as-of causality tests."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_putwrite"
sys.path.insert(0, str(OC))
import putwrite as P
import run_putwrite as RW

H = 3600_000_000_000  # ns


def _N(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs_put_ref(S, K, T, s):
    if T <= 0 or s <= 0:
        return max(K - S, 0.0)
    d1 = (math.log(S / K) + 0.5 * s * s * T) / (s * math.sqrt(T))
    return K * _N(-(d1 - s * math.sqrt(T))) - S * _N(-d1)


# ---- hand-checked synthetic cases ----

def test_bs_put_matches_independent_erf():
    for S, K, T, s in [(100.0, 100.0, 7 / 365, 0.7),
                        (100000.0, 86500.0, 7 / 365, 0.65),
                        (3000.0, 2800.0, 3 / 365, 0.9)]:
        assert abs(P.bs_put(S, K, T, s) - _bs_put_ref(S, K, T, s)) < 1e-9


def test_bs_put_hand_values():
    # T = 0 -> intrinsic; OTM expires worthless
    assert P.bs_put(90.0, 100.0, 0.0, 0.5) == 10.0
    assert P.bs_put(110.0, 100.0, 0.0, 0.5) == 0.0
    # no vol -> intrinsic
    assert P.bs_put(90.0, 100.0, 7 / 365, 0.0) == 10.0
    # ATM 7d 70-vol put ~ 0.4*S*s*sqrt(T) straddle/2 ballpark: sanity band
    v = P.bs_put(100.0, 100.0, 7 / 365, 0.7)
    assert 2.0 < v < 5.0
    # monotonic in K and sigma
    assert P.bs_put(100, 95, 7 / 365, 0.7) < P.bs_put(100, 100, 7 / 365, 0.7)
    assert P.bs_put(100, 100, 7 / 365, 0.5) < P.bs_put(100, 100, 7 / 365, 0.9)


def test_strike_rounds_down_to_grid():
    S, z, se = 100000.0, 1.5, 0.7
    raw = S * math.exp(-z * se * math.sqrt(7 / 365))
    assert 86000.0 < raw < 87000.0
    assert P.strike_from_spot(S, z, se, 1000.0) == 86000.0
    e = P.strike_from_spot(3000.0, 2.0, 0.8, 50.0)
    raw_e = 3000.0 * math.exp(-2.0 * 0.8 * math.sqrt(7 / 365))
    assert e == math.floor(raw_e / 50.0) * 50.0 and e <= raw_e


def test_fee_cap_and_settlement():
    assert P.fee_per_side(100000.0, 270.0) == pytest.approx(min(0.0003 * 100000.0, 33.75))
    assert P.fee_per_side(1000.0, 200.0) == pytest.approx(0.3)
    assert P.settle_fee(100000.0, 500.0) == pytest.approx(min(0.00015 * 100000.0, 62.5))


def test_weekly_pnl_arithmetic():
    assert P.weekly_pnl_per_unit(100.0, 5.0, "tp", exit_mark=20.0, fee_out=5.0) == 70.0
    assert P.weekly_pnl_per_unit(100.0, 5.0, "sl", exit_mark=300.0, fee_out=5.0) == -210.0
    assert P.weekly_pnl_per_unit(100.0, 5.0, "expiry", intrinsic=40.0, settle=2.0) == 53.0


def test_sizing_cash_secured():
    assert P.size_naked(1.0, 86000.0) == 0.5 / 86000.0
    assert P.size_spread(1.0, 86000.0, 76000.0) == 0.5 / 10000.0
    assert P.size_spread(1.0, 76000.0, 86000.0) == 0.0  # inverted width -> 0


# ---- causality / truncation tests ----

def test_iv_known_uses_only_closed_bars():
    t0 = np.array([0, 4 * H, 8 * H])  # bar starts; closes at +4h
    iv = np.array([50.0, 60.0, 70.0])
    assert np.isnan(RW.iv_known(t0, iv, 4 * H - 1))  # bar[0] not closed yet
    assert RW.iv_known(t0, iv, 4 * H) == 50.0  # bar[0] closes exactly at t
    assert RW.iv_known(t0, iv, 8 * H - 1) == 50.0  # bar[1] still open
    assert RW.iv_known(t0, iv, 8 * H) == 60.0  # bar[1] closes exactly at t
    assert np.isnan(RW.iv_known(t0, np.array([np.nan, 60.0, 70.0]), 4 * H))  # NaN -> NaN


def test_dvol_known_uses_only_closed_candles():
    ms = np.array([0, 3600_000])  # candle opens ms; closes +1h
    cl = np.array([80.0, 90.0])
    assert np.isnan(RW.dvol_known(ms, cl, 3600_000_000_000 - 1))
    assert RW.dvol_known(ms, cl, 3600_000_000_000) == 80.0
    assert RW.dvol_known(ms, cl, 2 * 3600_000_000_000) == 90.0


def test_px_at_never_looks_forward():
    ts = np.array([100, 200, 300])
    cl = np.array([1.0, 2.0, 3.0])
    v, exact = RW.px_at(ts, cl, 200)
    assert (v, exact) == (2.0, True)
    v, exact = RW.px_at(ts, cl, 250)  # between bars -> earlier bar, flagged
    assert (v, exact) == (2.0, False)
    v, _ = RW.px_at(ts, cl, 50)
    assert np.isnan(v)  # no past bar -> NaN, never a future bar
