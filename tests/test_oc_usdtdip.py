"""oc_usdtdip tests: D0 outcome + B1 fill/size + USDT tilt causality (synthetic)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research" / "tournament" / "oc_usdtdip"
sys.path.insert(0, str(OC))
import core as K

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def test_outcome_tp_win():
    O, H, L, C = _flat()
    f, lv, sg = 50, 100.0, 0.01
    H[f + 1:] = 102.0  # high > tp = 101 from the first post minute
    ret, x, how = K.outcome_mu(H, L, C, O, f, lv, sg, 1.0, 100.0, False)
    assert how == "tp" and x == f + 1
    assert abs(ret - (101.0 / 100.0 - 1 - 2 * MK)) < 1e-12


def test_outcome_stop_first_same_minute():
    O, H, L, C = _flat()
    f, lv, sg = 18, 100.0, 0.01  # f+1 = 19 is a clock minute ((19+1)%5==0)
    H[19] = 102.0  # TP touched the same minute ...
    C[19] = 95.0  # ... as the close5 stop (sl = 96)
    O[20] = 95.0
    ret, x, how = K.outcome_mu(H, L, C, O, f, lv, sg, 1.0, 100.0, False)
    assert how == "stop" and x == 20  # stop wins ties
    assert abs(ret - (95.0 / 100.0 - 1 - MK - TK)) < 1e-12


def test_outcome_backstop_top_priority_and_gap():
    O, H, L, C = _flat()
    f, lv, sg = 30, 100.0, 0.01  # bl = 92
    L[31] = 91.0
    O[31] = 95.0  # gap: min(bl, open) = bl
    H[31] = 105.0  # TP also touched -> backstop still wins
    ret, x, how = K.outcome_mu(H, L, C, O, f, lv, sg, 1.0, 100.0, False)
    assert how == "backstop" and x == 31
    assert abs(ret - (92.0 / 100.0 - 1 - MK - TK)) < 1e-12


def test_outcome_timeout_and_funding():
    O, H, L, C = _flat()
    f, lv, sg = 100, 100.0, 0.01
    ret, x, how = K.outcome_mu(H, L, C, O, f, lv, sg, 1.0, 100.0, False)
    assert how == "time" and x == 240
    assert abs(ret - (0.0 - MK - TK)) < 1e-12
    ret2, _, _ = K.outcome_mu(H, L, C, O, f, lv, sg, 1.0, 100.0, True)
    assert abs(ret2 - (0.0 - MK - TK - 0.0001)) < 1e-12


def test_n_counts_flushers_exact_boundary():
    cmat = np.array([[97.5, 97.51, np.nan],
                      [90.0, 99.0, 97.5],
                      [100.0, 100.0, 100.0],
                      [97.49, 97.5, 97.5]])
    oo = np.array([100.0, 100.0, 100.0, 100.0])
    ss = np.array([0.01, 0.01, 0.01, 0.01])
    assert K.n_vector(cmat, oo, ss).tolist() == [3, 1, 2]
    assert K.size_mult(0) == 1.0
    assert abs(K.size_mult(4) - 0.2) < 1e-12


def test_find_fill_strict_trade_through():
    low = np.array([100.0, 99.0, np.nan, 98.0])
    assert K.find_fill(low, 99.0) == 3  # equality never fills; NaN never fills
    assert K.find_fill(low, 50.0) is None


def test_tilt_mult_thresholds_and_nan():
    assert K.tilt_mult(1.5) == 1.2
    assert K.tilt_mult(-1.5) == 0.8
    assert K.tilt_mult(0.0) == 1.0
    assert K.tilt_mult(1.0) == 1.0  # strict >
    assert K.tilt_mult(-1.0) == 1.0  # strict <
    assert K.tilt_mult(np.nan) == 1.0  # warm-up never tilted


def test_asof_strictly_before_bar_open():
    T = 100_000 * K.NS
    ends = np.array([90_000, 93_600, 97_200, 99_600, 99_998, 100_000], dtype=np.int64) * K.NS
    ii = K.asof_index(ends, np.array([T]))
    assert int(ii[0]) == 4  # end == T excluded; earlier hours included
    ii2 = K.asof_index(ends, np.array([90_000 * K.NS], dtype=np.int64))
    assert int(ii2[0]) == -1  # nothing strictly before -> warm-up


def test_sigma_excludes_current_bar():
    ob = np.full(400, 100.0)
    ob[300] = 200.0  # spike inside bar 300's return must not leak into sig[300]
    sig = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
    ob2 = ob.copy()
    ob2[300] = 100.0
    sig2 = pd.Series(ob2).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
    assert sig[300] == sig2[300]  # own-bar return excluded via shift(1)


def test_control_is_year_phase_constant():
    rng = np.random.default_rng(0)
    w = rng.random(12) + 0.5
    mult = np.array([1.2, 1.2, 0.8, 1.0] * 3)
    avg = float(mult.mean())
    w_ctrl = w * avg
    assert abs(avg - 1.05) < 1e-12
    assert np.allclose(w_ctrl / w, 1.05)
    # with unit weights the rule and its own constant coincide exactly
    w1 = np.ones(12)
    y = np.full(12, 0.01)
    assert abs(float(((w1 * mult) * y).sum() - ((w1 * avg) * y).sum())) < 1e-9
