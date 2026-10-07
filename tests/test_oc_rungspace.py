"""oc_rungspace tests: rung levels, strict fill, n detector, D0 exits, all5 logic."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_rungspace"
sys.path.insert(0, str(OC))
import rungspace as R

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def test_rung_sets_fixed():
    assert tuple(R.BASE_RUNGS) == (2.5, 3.0, 3.5, 4.0, 5.0)
    assert tuple(R.WIDE_RUNGS) == (2.5, 3.25, 4.0, 5.0, 6.0)
    assert R.BASE_RUNGS[0] == R.WIDE_RUNGS[0] == 2.5  # first rung identical


def test_rung_level_formula():
    assert abs(R.rung_level(100.0, 0.01, 2.5) - 97.5) < 1e-12
    assert abs(R.rung_level(100.0, 0.01, 6.0) - 94.0) < 1e-12
    # wider spacing: gap between rung 2 and 3 is 0.75 wide vs 0.5 base
    gap_wide = abs(R.rung_level(100.0, 0.01, 3.25) - R.rung_level(100.0, 0.01, 4.0))
    gap_base = abs(R.rung_level(100.0, 0.01, 3.0) - R.rung_level(100.0, 0.01, 3.5))
    assert abs(gap_wide - 0.75) < 1e-12 and abs(gap_base - 0.5) < 1e-12


def test_n_counts_flushers_exact_boundary():
    cmat = np.array([[97.5, 97.51, np.nan],
                      [90.0, 99.0, 97.5],
                      [100.0, 100.0, 100.0],
                      [97.49, 97.5, 97.5]])
    oo = np.array([100.0, 100.0, 100.0, 100.0])
    ss = np.array([0.01, 0.01, 0.01, 0.01])
    n = R.n_vector(cmat, oo, ss)
    assert n.tolist() == [3, 1, 2]


def test_n_ignores_bad_sigma_and_open():
    cmat = np.array([[50.0], [50.0], [50.0], [50.0]])
    oo = np.array([100.0, np.nan, 100.0, 100.0])
    ss = np.array([0.01, 0.01, np.nan, 0.0])
    assert R.n_vector(cmat, oo, ss).tolist() == [1]


def test_size_mult():
    assert R.size_mult(0) == 1.0
    assert abs(R.size_mult(4) - 0.2) < 1e-12


def test_fill_strict_trade_through():
    lv = 100.0
    assert R.find_fill(np.array([100.0, 100.0]), np.array([lv, lv])) is None
    assert R.find_fill(np.array([100.0, 99.99]), np.array([lv, lv])) == 1
    assert R.find_fill(np.array([np.nan, 99.0]), np.array([lv, lv])) == 1
    assert R.find_fill(np.array([np.nan, np.nan]), np.array([lv, lv])) is None


def test_wide_deepest_fills_less_often():
    # dip to 94.5 with O=100, sg=0.01: base 5.0 rung at 95.0 fills,
    # wide 6.0 rung at 94.0 does not (needs strict trade-through)
    lv_base = R.rung_level(100.0, 0.01, 5.0)
    lv_wide = R.rung_level(100.0, 0.01, 6.0)
    low = np.array([94.5])
    assert R.find_fill(low, np.array([lv_base])) == 0
    assert R.find_fill(low, np.array([lv_wide])) is None


def test_exit_tp_from_fill():
    sg, f = 0.01, 20
    px = 97.5
    O, H, L, C = _flat(o=px)
    tp = px * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how = R.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "tp" and x == 30
    assert abs(ret - (tp / px - 1 - 2 * MK)) < 1e-12


def test_exit_stop_first_same_minute():
    sg, f, px = 0.01, 20, 97.5
    O, H, L, C = _flat(o=px)
    H[29] = px * (1 + sg) + 0.01
    C[29] = px * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    _, _, how = R.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "stop"


def test_exit_backstop_beats_tp():
    sg, f, px = 0.01, 20, 97.5
    O, H, L, C = _flat(o=px)
    H[25] = px * (1 + sg) + 0.01
    L[25] = px * (1 - 8 * sg) - 0.01
    _, x, how = R.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "backstop" and x == 25


def test_exit_timeout_funding():
    sg, f, px, o2 = 0.01, 20, 97.5, 98.1
    O, H, L, C = _flat(o=px)
    r0, _, h0 = R.outcome_from_fill(H, L, C, O, f, px, sg, o2, False)
    r1, _, h1 = R.outcome_from_fill(H, L, C, O, f, px, sg, o2, True)
    assert (h0, h1) == ("time", "time")
    assert abs((r0 - r1) - 0.0001) < 1e-12


def test_causality_fill_uses_only_closed_minutes():
    o, sg = 100.0, 0.01
    thr = o * (1 - 2.5 * sg)
    closes = np.full((4, 3), 100.0)
    closes[0, 1] = thr - 0.01
    n = R.n_vector(closes, np.full(4, o), np.full(4, sg))
    assert n.tolist() == [0, 1, 0]


def test_sigma_known_at_bar_open():
    opens = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    s = pd.Series(opens).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert np.isfinite(s[3]) and not np.isfinite(s[0])
    ref = pd.Series(opens[:4]).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12
