"""oc_fundhold tests: causality/truncation + hand-checked synthetic cases (no I/O)."""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent / "research/tournament/oc_fundhold"
sys.path.insert(0, str(HERE))
import fundhold as X
from fund_rule import (expensive_flag, last_settled_before, quantile_pool,
                       should_extend)


def test_last_settled_strict_before():
    sns = np.array([100, 200, 300], dtype=np.int64)
    rte = np.array([0.01, 0.02, 0.03])
    # settlement AT the timeout open (300) is 1ms after -> not known: use 200
    out = last_settled_before(sns, rte, np.array([300], dtype=np.int64))
    assert out[0] == 0.02
    out = last_settled_before(sns, rte, np.array([50], dtype=np.int64))
    assert not np.isfinite(out[0])


def test_quantile_pool_min50_and_flag_strict():
    pool = np.arange(60, dtype=float)
    assert np.isfinite(quantile_pool(pool, 0.70))
    assert not np.isfinite(quantile_pool(np.arange(49, dtype=float), 0.70))
    assert expensive_flag(np.array([0.05, 0.05]), 0.05).tolist() == [False, False]
    assert expensive_flag(np.array([0.050001]), 0.05).tolist() == [True]
    assert expensive_flag(np.array([np.nan]), 0.05).tolist() == [False]
    assert expensive_flag(np.array([0.06]), float("nan")).tolist() == [False]
    assert should_extend(0.04, 0.05) is True
    assert should_extend(0.06, 0.05) is False
    assert should_extend(float("nan"), 0.05) is False
    assert should_extend(0.04, float("nan")) is False


def test_find_fill_strict_trade_through():
    assert X.find_fill(np.array([5.0, 5.0, 4.9]), 5.0) == 2  # == does NOT fill
    assert X.find_fill(np.array([5.0, 5.0]), 5.0) is None
    assert X.find_fill(np.array([np.nan, 4.0]), 5.0) == 1  # NaN never fills


def test_hand_base_tp_and_stop_first():
    # flat 240-min bar, fill at f=16, px=100, sg=0.01 -> tp=101, sl=96, bl=92
    n = 240
    O = np.full(n, 100.0)
    C = np.full(n, 100.0)
    H = np.full(n, 100.0)
    L = np.full(n, 100.0)
    H[20] = 101.5  # TP touch (strict >) at t=20
    C[20] = 95.0  # simultaneous close5 stop signal at m=20? (20+1)%5!=0 -> no stop
    ret, x, how = X.outcome_base(H, L, C, O, 16, 100.0, 0.01, 100.0, False)
    assert how == "tp" and x == 20
    assert abs(ret - (101.0 / 100.0 - 1 - 2 * X.MAKER)) < 1e-12
    # same-minute stop+TP -> stop wins: put both at a clock minute m with (m+1)%5==0
    H2 = np.full(n, 100.0)
    L2 = np.full(n, 100.0)
    C2 = np.full(n, 100.0)
    O2 = np.full(n, 100.0)
    H2[24] = 101.5  # TP candidate at t=24
    C2[24] = 95.0  # close5 signal at m=24 ((24+1)%5==0) -> stop wins tie
    ret, x, how = X.outcome_base(H2, L2, C2, O2, 16, 100.0, 0.01, 100.0, False)
    assert how == "stop"


def test_hand_timeout_and_ext8_funding():
    n = 240
    O = np.full(n, 100.0)
    C = np.full(n, 100.0)
    H = np.full(n, 100.0)
    L = np.full(n, 100.0)
    ret, x, how = X.outcome_base(H, L, C, O, 16, 100.0, 0.01, 100.5, True)
    assert how == "time" and x == 240
    assert abs(ret - (100.5 / 100.0 - 1 - X.MAKER - X.TAKER - X.FUND)) < 1e-12
    # extended leg: TP in second bar at absolute 500, mid1 settles, mid2 not
    H2 = np.full(480, 100.0)
    L2 = np.full(480, 100.0)
    C2 = np.full(480, 100.0)
    O2 = np.full(480, 100.0)
    H2[260] = 101.5  # absolute 240+260=500
    ret, x, how = X.outcome_ext8_phase(H2, L2, C2, O2, 100.0, 0.01, 100.0,
                                       True, False, False)
    assert how == "tp" and x == 500
    # held through T+240 (fund) + x>=480 but mid2 False -> one fund
    assert abs(ret - (101.0 / 100.0 - 1 - 2 * X.MAKER - X.FUND)) < 1e-12
    # extended timeout at o4 with all three settling -> 3x fund
    ret, x, how = X.outcome_ext8_phase(np.full(480, 100.0), np.full(480, 100.0),
                                       np.full(480, 100.0), np.full(480, 100.0),
                                       100.0, 0.01, 100.5, True, True, True)
    assert how == "time" and x == 720
    assert abs(ret - (100.5 / 100.0 - 1 - X.MAKER - X.TAKER - 3 * X.FUND)) < 1e-12


def test_hand_conditional_pairs_base_when_expensive_or_notimeout():
    n = 240
    O = np.full(n, 100.0)
    C = np.full(n, 100.0)
    H = np.full(n, 100.0)
    L = np.full(n, 100.0)
    H2 = np.full(480, 100.0)
    L2 = np.full(480, 100.0)
    C2 = np.full(480, 100.0)
    O2 = np.full(480, 100.0)
    H2[0] = 101.5
    b, bx, bh, v, vx, vh, ext = X.outcome_conditional(
        H, L, C, O, 16, 100.0, 0.01, 100.0, False, False,
        H2, L2, C2, O2, 100.0, False, False, False)
    assert bh == "time" and vh == "time" and ext is False and v == b
    b, bx, bh, v, vx, vh, ext = X.outcome_conditional(
        H, L, C, O, 16, 100.0, 0.01, 100.0, False, True,
        H2, L2, C2, O2, 100.0, False, False, False)
    assert ext is True and vh == "tp" and vx == 240
