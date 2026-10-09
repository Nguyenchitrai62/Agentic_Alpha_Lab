"""oc_relflush tests: D0 outcome + B1 fill/size + rel-flush tilt causality (synthetic)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research" / "tournament" / "oc_relflush"
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


def test_depth_sigma_hand_checked():
    # P=97.5, O=100, sg=0.01 -> -log(0.975)/0.01 = 2.5317...
    d = K.depth_sigma(97.5, 100.0, 0.01)
    assert abs(d - (-np.log(0.975) / 0.01)) < 1e-12
    assert d > 2.5  # flushes at the 2.5 detector
    d2 = K.depth_sigma(97.6, 100.0, 0.01)
    assert d2 < 2.5  # just above the level does not flush
    # NaN / non-positive legs -> NaN (never flushing, never tilted)
    assert not np.isfinite(K.depth_sigma(np.nan, 100.0, 0.01))
    assert not np.isfinite(K.depth_sigma(97.5, np.nan, 0.01))
    assert not np.isfinite(K.depth_sigma(97.5, 100.0, np.nan))
    assert not np.isfinite(K.depth_sigma(97.5, 0.0, 0.01))
    assert not np.isfinite(K.depth_sigma(-1.0, 100.0, 0.01))
    assert not np.isfinite(K.depth_sigma(97.5, 100.0, 0.0))


def test_rel_overshoot_hand_checked():
    assert abs(K.rel_overshoot(3.0, np.array([2.5, 2.7])) - 0.4) < 1e-12
    assert abs(K.rel_overshoot(2.0, np.array([2.5, 2.7])) - (-0.6)) < 1e-12
    # empty flush set / NaN own -> NaN (tilt falls back to 1.0)
    assert not np.isfinite(K.rel_overshoot(3.0, np.array([])))
    assert not np.isfinite(K.rel_overshoot(float("nan"), np.array([2.5])))
    # NaN members are ignored, not propagated
    assert abs(K.rel_overshoot(3.0, np.array([2.6, np.nan])) - 0.4) < 1e-12
    assert not np.isfinite(K.rel_overshoot(3.0, np.array([np.nan])))


def test_tilts_thresholds_strict_and_n0():
    # R1: strict > / < at +-0.5
    assert K.tilt_r1(0.51, 2) == 1.5
    assert K.tilt_r1(0.5, 2) == 1.0
    assert K.tilt_r1(-0.51, 2) == 0.75
    assert K.tilt_r1(-0.5, 2) == 1.0
    assert K.tilt_r1(0.0, 2) == 1.0
    # R2 mirrors R1 exactly
    assert K.tilt_r2(0.51, 2) == 0.75
    assert K.tilt_r2(-0.51, 2) == 1.5
    assert K.tilt_r2(0.0, 2) == 1.0
    for rel in (2.0, -2.0, 0.0, float("nan")):
        assert K.tilt_r1(rel, 0) == 1.0  # n_fill = 0 keeps w = 1
        assert K.tilt_r2(rel, 0) == 1.0
        assert K.tilt_r3(rel, 0) == 1.0
    # NaN rel -> 1.0 in every arm
    assert K.tilt_r1(float("nan"), 3) == 1.0
    assert K.tilt_r2(float("nan"), 3) == 1.0
    assert K.tilt_r3(float("nan"), 3) == 1.0


def test_tilt_r3_linear_and_clip():
    assert abs(K.tilt_r3(0.4, 1) - 1.1) < 1e-12
    assert abs(K.tilt_r3(-0.4, 1) - 0.9) < 1e-12
    assert abs(K.tilt_r3(0.0, 2) - 1.0) < 1e-12
    assert K.tilt_r3(10.0, 2) == 1.4  # clip top
    assert K.tilt_r3(-10.0, 2) == 0.6  # clip bottom
    assert K.tilt_r3(1.6, 2) == 1.4  # 1+0.25*1.6 = 1.4 boundary inclusive
    assert K.tilt_r3(-1.6, 2) == 0.6


def test_r2_is_mirror_of_r1_over_grid():
    rels = [-2.0, -0.51, -0.5, -0.1, 0.0, 0.1, 0.5, 0.51, 2.0]
    for rel in rels:
        a, b = K.tilt_r1(rel, 2), K.tilt_r2(rel, 2)
        if abs(rel) <= 0.5:
            assert a == 1.0 and b == 1.0
        else:
            # one arm up-weights exactly where the other down-weights
            assert sorted([a, b]) == [0.75, 1.5]


def test_sigma_excludes_current_bar():
    ob = np.full(400, 100.0)
    ob[300] = 200.0  # spike inside bar 300's return must not leak into sig[300]
    sig = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
    ob2 = ob.copy()
    ob2[300] = 100.0
    sig2 = pd.Series(ob2).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
    assert sig[300] == sig2[300]  # own-bar return excluded via shift(1)


def test_fill_and_n_use_only_minute_f_minus_1():
    # Live window offsets 16..18; fill level sits between low[17] values.
    # Changing the close AT the fill minute f must not change n at f;
    # changing the close at f-1 must.
    oo = np.array([100.0])
    ss = np.array([0.01])  # thr = 97.5
    c_at_fm1_flush = np.array([[97.0, 99.0, 99.0]])  # minute f-1 flushes
    c_at_fm1_calm = np.array([[99.0, 99.0, 99.0]])  # minute f-1 calm
    assert K.n_vector(c_at_fm1_flush, oo, ss).tolist() == [1, 0, 0]
    assert K.n_vector(c_at_fm1_calm, oo, ss).tolist() == [0, 0, 0]
    # same for the rel input: depth uses P(f-1), so moving P(f) is invisible
    d_fm1 = K.depth_sigma(97.0, 100.0, 0.01)
    d_f = K.depth_sigma(99.0, 100.0, 0.01)
    assert d_fm1 >= 2.5 > d_f  # flush set membership flips only via f-1
    rel = K.rel_overshoot(3.0, np.array([d_fm1]))
    assert np.isfinite(rel)
    rel2 = K.rel_overshoot(3.0, np.array([d_f]))
    assert abs(rel2 - (3.0 - d_f)) < 1e-12
