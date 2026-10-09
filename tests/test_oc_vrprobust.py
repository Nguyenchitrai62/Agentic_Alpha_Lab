"""oc_vrprobust tests: causality + hand-checked synthetic cases."""
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "research/tournament/oc_vrprobust"))
import vrprobust as V


def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def test_bs_matches_hand_calc():
    # S=100, K=100, T=0.25, sigma=0.60: d1 = (0 + 0.5*0.36*0.25)/(0.6*0.5)
    S, K, T, s = 100.0, 100.0, 0.25, 0.60
    sqt = s * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * s * s * T) / sqt
    d2 = d1 - sqt
    assert abs(V.bs_call(S, K, T, s) - (S * ncdf(d1) - K * ncdf(d2))) < 1e-9
    assert abs(V.bs_put(S, K, T, s) - (K * ncdf(-d2) - S * ncdf(-d1))) < 1e-9
    # put-call parity (r=q=0): C - P = S - K
    assert abs((V.bs_call(S, K, T, s) - V.bs_put(S, K, T, s)) - (S - K)) < 1e-9
    # ATM straddle delta = 2*N(d1) - 1 (positive: d1 = 0.5*s*sqrt(T) > 0)
    assert abs(V.bs_straddle_delta(S, K, T, s) - (2.0 * ncdf(d1) - 1.0)) < 1e-12
    # expiry intrinsics
    assert V.bs_call(110.0, 100.0, 0.0, s) == 10.0
    assert V.bs_put(90.0, 100.0, 0.0, s) == 10.0
    assert V.bs_straddle(90.0, 100.0, 1.0, 0.0) == 10.0


def test_fee_caps_hand_checked():
    # min(0.0003*S, 0.125*price): S=50000, price=1000 -> min(15, 125) = 15
    assert abs(V.fee_per_side(50000.0, 1000.0) - 15.0) < 1e-9
    # S=50000, price=10 -> min(15, 1.25) = 1.25
    assert abs(V.fee_per_side(50000.0, 10.0) - 1.25) < 1e-9
    # Bybit-style cap_frac=0.07: min(15, 70) = 15; cheap leg min(15, 0.7)=0.7
    assert abs(V.fee_per_side(50000.0, 1000.0, 0.0003, 0.07) - 15.0) < 1e-9
    assert abs(V.fee_per_side(50000.0, 10.0, 0.0003, 0.07) - 0.7) < 1e-9
    # settlement: ITM intrinsic 500 at S=50000 -> min(7.5, 62.5) = 7.5
    assert abs(V.settle_fee(50000.0, 500.0) - 7.5) < 1e-9
    # OTM pays nothing
    assert V.settle_fee(50000.0, 0.0) == 0.0
    # strike rounding to nearest grid
    assert V.strike_round(67430.0, 1000.0) == 67000.0
    assert V.strike_round(67680.0, 1000.0) == 68000.0
    # size: q = 0.5*f*E/S
    assert V.size_q(2.0, 50000.0, 0.25) == 0.5 * 0.25 * 2.0 / 50000.0


def test_sell_mult_scales_premium_monotonically():
    # lower k -> lower premium (causality of the pricing knob; no forward data)
    S, K, T = 60000.0, 60000.0, (7 * 24 * 60 - 5) / (365 * 24 * 60)
    dvol = 60.0
    prems = [V.bs_straddle(S, K, T, k * dvol / 100.0) for k in (0.97, 0.92, 0.88, 0.85, 0.80)]
    assert all(b < a for a, b in zip(prems, prems[1:])), prems
    # SL threshold (-1x gross premium) tightens with k as well
    assert prems[-1] < prems[0]


def test_truncation_causality_dvol_known():
    """dvol_known must use the candle close <= t (no peeking at the live candle)."""
    sys.path.insert(0, str(HERE.parent / "research/tournament/oc_vrprobust"))
    import run_robust as R
    # hourly candles starting at ms 0,1h,... with closes 50,51,52
    ms = np.array([0, 3600_000, 7200_000], dtype=np.int64) * 1_000_000
    cl = np.array([50.0, 51.0, 52.0])
    # candle-start 0 closes at 1h; candle-start 1h closes at 2h.
    # nothing is known before the first close; each close is known exactly at
    # its timestamp and not a nanosecond earlier.
    assert not np.isfinite(R.dvol_known(ms, cl, 3600_000_000_000 - 1))
    assert R.dvol_known(ms, cl, 3600_000_000_000) == 50.0
    assert R.dvol_known(ms, cl, 2 * 3600_000_000_000 - 1) == 50.0
    assert R.dvol_known(ms, cl, 2 * 3600_000_000_000) == 51.0
    # px_at: exact bar open returns its close; between bars returns prior close
    ts = np.array([0, 60_000_000_000, 120_000_000_000], dtype=np.int64)
    px = np.array([100.0, 101.0, 102.0])
    assert R.px_at(ts, px, 60_000_000_000) == (101.0, True)
    assert R.px_at(ts, px, 90_000_000_000)[0] == 101.0  # last bar open strictly before
    assert R.px_at(ts, px, 60_000_000_000 - 1)[0] == 100.0


def test_b_present_months_match_plan():
    import json
    b = json.loads((HERE.parent / "research/tournament/oc_vrprobust/tmp/B.json").read_text())
    assert set(b["months"]["BTC"]) == {"2021-01", "2021-02", "2021-03", "2021-04",
                                       "2021-05", "2021-06", "2021-07", "2023-03", "2025-06"}
    assert len(b["months"]["ETH"]) == 11
    have_r = [r for r in b["fridays"] if r["r"] is not None]
    assert len(have_r) == b["dist"]["pooled"]["n"] > 0
    for r in have_r:
        assert 0.3 < r["r"] < 3.0, r  # sanity band on traded-IV/DVOL ratio
        assert r["n_rows"] > 0 and r["amount"] > 0
