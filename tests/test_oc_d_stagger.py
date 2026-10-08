"""oc_d_stagger tests: hand-checked synthetic cases + causality/truncation."""
import numpy as np
import pandas as pd

import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
STAG = HERE.parent / "research" / "tournament" / "oc_d_stagger"
sys.path.insert(0, str(STAG))
import stagger_rule as sr


def test_windows_frozen():
    assert sr.windows_V1() == ((5, 64), (35, 94))
    assert sr.windows_V2() == ((5, 64), (95, 154))
    assert sr.WIN_REF == (16, 238)


def test_find_fill_strict_and_nan():
    low = np.full(240, 100.0)
    low[10] = 99.0  # below level 99.5 -> fills at 10
    assert sr.find_fill_in(low, 99.5, 5, 64) == 10
    # touch == never fills
    low2 = np.full(240, 100.0)
    low2[10] = 99.5
    assert sr.find_fill_in(low2, 99.5, 5, 64) is None
    # NaN never fills
    low3 = np.full(240, np.nan)
    assert sr.find_fill_in(low3, 99.5, 5, 64) is None
    # minute-5 ban: touch at offset 3 is outside window
    low4 = np.full(240, 100.0)
    low4[3] = 50.0
    assert sr.find_fill_in(low4, 99.5, 5, 64) is None
    # expiry: touch at 70 outside A window, inside nothing
    low5 = np.full(240, 100.0)
    low5[70] = 50.0
    assert sr.find_fill_in(low5, 99.5, 5, 64) is None
    assert sr.find_fill_in(low5, 99.5, 35, 94) == 70


def test_split_halves_same_price_handcheck():
    # one bar, level 100, A window touch at 10, B_V1 touch at 40
    low = np.full(240, 101.0)
    low[10] = 99.0
    low[40] = 99.0
    lv = 100.0
    fA = sr.find_fill_in(low, lv, 5, 64)
    fB1 = sr.find_fill_in(low, lv, 35, 94)
    fB2 = sr.find_fill_in(low, lv, 95, 154)
    assert fA == 10
    assert fB1 == 40
    assert fB2 is None  # no touch in 95..154
    # same price, halved weights sum to base when n equal
    wA = sr.half_weight(0)
    wB = sr.half_weight(0)
    assert abs((wA + wB) - 1.0) < 1e-12


def test_n_at_v399_exact():
    # 100*(1-2.5*0.05) = 87.5; 90 > 87.5 -> NOT flushing
    assert sr.n_at(np.array([90.0]), np.array([100.0]), np.array([0.05])) == 0
    assert sr.n_at(np.array([87.5]), np.array([100.0]), np.array([0.05])) == 1
    # exact boundary counts (<=)
    o, sg = 100.0, 0.04
    thr = o * (1 - 2.5 * sg)  # 90.0
    assert sr.n_at(np.array([thr]), np.array([o]), np.array([sg])) == 1
    assert sr.n_at(np.array([thr + 1e-9]), np.array([o]), np.array([sg])) == 0
    # NaN never counts
    assert sr.n_at(np.array([np.nan]), np.array([o]), np.array([sg])) == 0
    # own coin never counted here (caller excludes own)


def test_outcome_stop_first_handcheck():
    # flat bar: fill at 10, TP far, stop far -> timeout at o2
    n = 240
    O = np.full(n, 100.0)
    H = np.full(n, 100.5)
    L = np.full(n, 99.5)
    C = np.full(n, 100.0)
    lv, sg = 100.0, 0.01
    # sl=96, bl=92, tp=101 -> H max 100.5 never > 101, C never <= 96 -> timeout
    ret, x, how = sr.outcome_mu(H, L, C, O, 10, lv, sg, 1.0, 100.0, False)
    assert how == "time"
    assert abs(ret - (100.0 / 100.0 - 1 - sr.MAKER - sr.TAKER)) < 1e-12
    # TP touch wins when strictly earlier than stop
    H2 = H.copy()
    H2[15] = 102.0  # high > tp=101 at t=15
    ret2, x2, how2 = sr.outcome_mu(H2, L, C, O, 10, lv, sg, 1.0, 100.0, False)
    assert how2 == "tp"
    assert x2 == 15
    # backstop wins ties (kb <= kt): low <= bl=92 at same t as TP
    L3 = L.copy()
    L3[15] = 90.0
    ret3, x3, how3 = sr.outcome_mu(H2, L3, C, O, 10, lv, sg, 1.0, 100.0, False)
    assert how3 == "backstop"


def test_truncation_causality():
    # find_fill_in on truncated low array == kept prefix of full run
    rng = np.random.default_rng(0)
    low = 100 + rng.normal(0, 1, 240)
    cut = 120
    f_full_A = sr.find_fill_in(low, 99.0, 5, 64)
    f_tr_A = sr.find_fill_in(low[:cut], 99.0, 5, 64)
    # if full fill is before cut, truncated agrees; else truncated is None-or-same
    if f_full_A is not None and f_full_A < cut:
        assert f_tr_A == f_full_A
    # sigma uses only past opens (shift-1): last value drops when truncated
    opens = 100 + np.cumsum(rng.normal(0, 0.1, 500))
    s_full = sr.compute_sigma(opens)
    s_tr = sr.compute_sigma(opens[:400])
    assert np.allclose(s_tr[:399], s_full[:399], equal_nan=True)
