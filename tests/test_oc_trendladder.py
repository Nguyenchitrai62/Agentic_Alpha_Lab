"""oc_trendladder tests: trend multiplier + static fill + D0-from-fill exit."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_trendladder"
sys.path.insert(0, str(OC))
import trend as T

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def test_trend_mult_branches():
    assert T.trend_mult(0.01) == 0.85
    assert T.trend_mult(1e-9) == 0.85
    assert T.trend_mult(0.0) == 1.15  # zero counts as deeper branch
    assert T.trend_mult(-0.01) == 1.15
    assert T.trend_mult(float("nan")) == 1.15
    assert T.trend_mult(float("inf")) == 1.15


def test_r30_uses_only_rows_before_bar():
    opens = np.array([100.0, 102.0, 104.0, 108.0, 110.0])
    # j=4: O[3]/O[3-180]-> out of range (NaN) here; use small lookback logic check
    # with a longer array: constant 100 then jump
    big = np.full(200, 100.0)
    big[198] = 110.0  # O[j-1] for j=199
    r = T.r30_from_opens(big, 199)  # 110/100-1 = 0.10
    assert abs(r - 0.10) < 1e-12
    # truncated history to j must give the same r (no use of O[j] or later)
    r_trunc = T.r30_from_opens(big[:199], 199 - 0)  # same indices < j
    # big[:199] has len 199, j=199 -> i1=198, i0=18, same values
    assert abs(r_trunc - 0.10) < 1e-12
    # O[j] itself must not matter: change big[199], r unchanged
    big2 = big.copy()
    big2[199] = 500.0
    assert abs(T.r30_from_opens(big2, 199) - 0.10) < 1e-12
    # out-of-range / NaN -> NaN -> deeper branch
    assert np.isnan(T.r30_from_opens(np.array([1.0, 2.0]), 1))
    bad = np.full(200, 100.0)
    bad[198] = np.nan
    assert np.isnan(T.r30_from_opens(bad, 199))
    assert T.trend_mult(T.r30_from_opens(bad, 199)) == 1.15


def test_r30_zero_denominator_nan():
    big = np.full(200, 100.0)
    big[18] = 0.0  # denominator O[j-181] for j=199
    assert np.isnan(T.r30_from_opens(big, 199))


def test_depth_scaling_factors():
    o1, sg, k = 100.0, 0.01, 2.5
    lv_base = o1 * (1 - k * sg)
    lv_up = o1 * (1 - k * 0.85 * sg)  # 2.5 -> 2.125
    lv_dn = o1 * (1 - k * 1.15 * sg)  # 2.5 -> 2.875
    assert abs(lv_base - 97.5) < 1e-12
    assert abs(lv_up - (100 * (1 - 2.125 * 0.01))) < 1e-12
    assert abs(lv_dn - (100 * (1 - 2.875 * 0.01))) < 1e-12
    assert lv_up > lv_base > lv_dn  # up = shallower (higher bid), down = deeper


def test_n_counts_flushers_exact_boundary():
    cmat = np.array([[97.5, 97.51, np.nan],
                      [90.0, 99.0, 97.5],
                      [100.0, 100.0, 100.0],
                      [97.49, 97.5, 97.5]])
    oo = np.array([100.0, 100.0, 100.0, 100.0])
    ss = np.array([0.01, 0.01, 0.01, 0.01])
    n = T.n_vector(cmat, oo, ss)
    assert n.tolist() == [3, 1, 2]


def test_n_ignores_bad_sigma_and_open():
    cmat = np.array([[50.0], [50.0], [50.0], [50.0]])
    oo = np.array([100.0, np.nan, 100.0, 100.0])
    ss = np.array([0.01, 0.01, np.nan, 0.0])
    n = T.n_vector(cmat, oo, ss)
    assert n.tolist() == [1]


def test_size_mult():
    assert T.size_mult(0) == 1.0
    assert abs(T.size_mult(4) - 0.2) < 1e-12


def test_fill_strict_trade_through():
    lv = 100.0
    assert T.find_fill(np.array([100.0, 100.0]), np.array([lv, lv])) is None
    assert T.find_fill(np.array([100.0, 99.99]), np.array([lv, lv])) == 1


def test_shallower_level_fills_where_deeper_does_not():
    sg = 0.01
    lv_base = 97.5
    lv_up = 100 * (1 - 2.5 * 0.85 * sg)  # 97.875, shallower
    low = np.array([97.7])
    assert T.find_fill(low, np.array([lv_up])) == 0  # fills shallow bid
    assert T.find_fill(low, np.array([lv_base])) is None  # too deep, no fill


def test_exit_measured_from_actual_fill():
    sg, f = 0.01, 20
    px = 97.875  # trend actual fill, NOT base lv
    O, H, L, C = _flat(o=px)
    tp = px * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how = T.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "tp" and x == 30
    assert abs(ret - (tp / px - 1 - 2 * MK)) < 1e-12


def test_exit_stop_first_same_minute():
    sg, f, px = 0.01, 20, 98.0
    O, H, L, C = _flat(o=px)
    H[29] = px * (1 + sg) + 0.01
    C[29] = px * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    ret, x, how = T.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "stop"


def test_exit_backstop_beats_tp():
    sg, f, px = 0.01, 20, 98.0
    O, H, L, C = _flat(o=px)
    H[25] = px * (1 + sg) + 0.01
    L[25] = px * (1 - 8 * sg) - 0.01
    ret, x, how = T.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "backstop" and x == 25


def test_exit_timeout_funding():
    sg, f, px, o2 = 0.01, 20, 98.0, 98.1
    O, H, L, C = _flat(o=px)
    r0, _, h0 = T.outcome_from_fill(H, L, C, O, f, px, sg, o2, False)
    r1, _, h1 = T.outcome_from_fill(H, L, C, O, f, px, sg, o2, True)
    assert (h0, h1) == ("time", "time")
    assert abs((r0 - r1) - 0.0001) < 1e-12


def test_causality_fill_uses_only_closed_minutes():
    o, sg = 100.0, 0.01
    thr = o * (1 - 2.5 * sg)
    closes = np.full((4, 3), 100.0)
    closes[0, 1] = thr - 0.01
    n = T.n_vector(closes, np.full(4, o), np.full(4, sg))
    assert n.tolist() == [0, 1, 0]


def test_sigma_known_at_bar_open():
    opens = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    s = pd.Series(opens).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert np.isfinite(s[3]) and not np.isfinite(s[0])
    ref = pd.Series(opens[:4]).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12
