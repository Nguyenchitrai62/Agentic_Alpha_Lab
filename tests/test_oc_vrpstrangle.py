"""oc_vrpstrangle tests: causality/truncation + hand-checked synthetic cases."""
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "research/tournament/oc_vrpstrangle"))
import strangle as ST
import run_strangle as R


def test_iv_known_strictly_asof():
    # 4h bars starting 00:00 and 04:00 -> known at 04:00 and 08:00.
    t0 = np.array([np.datetime64("2021-10-01T00:00").astype("datetime64[ns]").astype(np.int64),
                   np.datetime64("2021-10-01T04:00").astype("datetime64[ns]").astype(np.int64)])
    put = np.array([60.0, 70.0])
    call = np.array([62.0, 72.0])
    entry = np.datetime64("2021-10-01T08:05").astype("datetime64[ns]").astype(np.int64)
    ivp, ivc = R.iv_known(t0, put, call, int(entry))
    # last bar with close (start+4h) <= 08:05 is the 04:00 bar
    assert (ivp, ivc) == (70.0, 72.0)
    # one ns before the 08:00 close -> still the 00:00 bar
    just_before = np.datetime64("2021-10-01T08:00").astype("datetime64[ns]").astype(np.int64) - 1
    ivp2, _ = R.iv_known(t0, put, call, int(just_before))
    assert ivp2 == 60.0
    # query before any close -> NaN (truncation, not forward fill)
    early = np.datetime64("2021-10-01T03:00").astype("datetime64[ns]").astype(np.int64)
    ivp3, _ = R.iv_known(t0, put, call, int(early))
    assert np.isnan(ivp3)


def test_dvol_known_strictly_asof():
    ms = np.array([np.datetime64("2021-10-01T06:00").astype("datetime64[ns]").astype(np.int64)])
    cl = np.array([55.0])
    at_close = np.datetime64("2021-10-01T07:00").astype("datetime64[ns]").astype(np.int64)
    assert R.dvol_known(ms, cl, int(at_close)) == 55.0
    before = int(at_close) - 1
    assert np.isnan(R.dvol_known(ms, cl, before))


def test_px_at_exact_vs_fallback():
    ts = np.array([100, 200, 300])
    cl = np.array([10.0, 11.0, 12.0])
    px, exact = R.px_at(ts, cl, 200)
    assert (px, exact) == (11.0, True)
    px2, exact2 = R.px_at(ts, cl, 250)  # no bar open at 250 -> last before
    assert (px2, exact2) == (11.0, False)


def test_put_call_parity_r0():
    # hand-checked: C - P = S - K when r = q = 0.
    S, K, T, sig = 60000.0, 59000.0, (7 * 86400 - 300) / (365 * 86400), 0.6
    assert abs(ST.bs_call(S, K, T, sig) - ST.bs_put(S, K, T, sig) - (S - K)) < 1e-6


def test_strangle_strikes_direction_and_grid():
    S, T, grid = 60000.0, (7 * 86400 - 300) / (365 * 86400), 1000.0
    Kp, Kc = ST.strangle_strikes(S, 0.6, 0.62, T, 0.5, grid)
    assert Kp < S < Kc
    assert Kp % grid == 0 and Kc % grid == 0
    raw_p = S * math.exp(-0.5 * 0.6 * math.sqrt(T))
    raw_c = S * math.exp(+0.5 * 0.62 * math.sqrt(T))
    assert Kp <= raw_p and Kc >= raw_c  # put DOWN, call UP
    # wider z -> wider wings
    Kp2, Kc2 = ST.strangle_strikes(S, 0.6, 0.62, T, 1.0, grid)
    assert Kp2 <= Kp and Kc2 >= Kc
    # bad inputs -> nan, never a trade
    assert all(math.isnan(v) for v in ST.strangle_strikes(-1.0, 0.6, 0.6, T, 0.5, grid))
    assert all(math.isnan(v) for v in ST.strangle_strikes(S, 0.0, 0.6, T, 0.5, grid))


def test_fees_and_size():
    # fee cap binds on expensive legs, 12.5% binds on cheap legs
    assert ST.fee_per_side(60000.0, 1000.0) == 0.0003 * 60000.0
    assert ST.fee_per_side(60000.0, 1.0) == 0.125 * 1.0
    assert ST.settle_fee(60000.0, 0.0) == 0.0
    assert ST.settle_fee(60000.0, 5000.0) == 0.00015 * 60000.0
    assert ST.settle_fee(60000.0, 1.0) == 0.125 * 1.0
    assert ST.size_q(1.0, 60000.0, 1.0) == 0.5 / 60000.0


def test_sl_tp_trigger_arithmetic():
    # hand-checked: premium 100/unit, opt_cash 99; SL iff 99 - mark_sl <= -100.
    gross, opt_cash = 100.0, 99.0
    assert (opt_cash - 199.0) <= -gross  # SL trips at mark 199
    assert not ((opt_cash - 198.0) <= -gross)  # not at 198
    assert 29.9 <= 0.3 * gross  # TP trips at mark 29.9
    assert not (30.1 <= 0.3 * gross)
