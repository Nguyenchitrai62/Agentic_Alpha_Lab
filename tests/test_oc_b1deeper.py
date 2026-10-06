"""oc_b1deeper tests: dynamic-level fill + D0-from-fill exit on synthetic paths."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_b1deeper"
sys.path.insert(0, str(OC))
import deeper as D

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def test_n_counts_flushers_exact_boundary():
    # other opens 100, sg 0.01 -> thr = 100*(1-0.025) = 97.5; <= counts
    cmat = np.array([[97.5, 97.51, np.nan],
                      [90.0, 99.0, 97.5],
                      [100.0, 100.0, 100.0],
                      [97.49, 97.5, 97.5]])
    oo = np.array([100.0, 100.0, 100.0, 100.0])
    ss = np.array([0.01, 0.01, 0.01, 0.01])
    n = D.n_vector(cmat, oo, ss)
    assert n.tolist() == [3, 1, 2]  # exact 97.5 counts; NaN never counts


def test_n_ignores_bad_sigma_and_open():
    cmat = np.array([[50.0], [50.0], [50.0], [50.0]])
    oo = np.array([100.0, np.nan, 100.0, 100.0])
    ss = np.array([0.01, 0.01, np.nan, 0.0])
    n = D.n_vector(cmat, oo, ss)
    assert n.tolist() == [1]  # only leg 0 valid; NaN open/sigma, sg<=0 ignored


def test_size_mult():
    assert D.size_mult(0) == 1.0
    assert abs(D.size_mult(4) - 0.2) < 1e-12


def test_level_formula_and_return_to_lv():
    lv, sg = 100.0, 0.01
    n = np.array([0, 1, 2, 4, 0])
    lvl = D.level_vector(lv, sg, n)
    assert lvl[0] == lv and lvl[4] == lv  # n=0 -> back to lv
    assert abs(lvl[1] - 100 * (1 - 0.5 * 1 * 0.01)) < 1e-12
    assert abs(lvl[3] - 100 * (1 - 0.5 * 4 * 0.01)) < 1e-12


def test_fill_strict_trade_through():
    lv = 100.0
    assert D.find_fill(np.array([100.0, 100.0]), np.array([lv, lv])) is None
    assert D.find_fill(np.array([100.0, 99.99]), np.array([lv, lv])) == 1


def test_deeper_avoids_shallow_then_fills_deeper():
    lv, sg = 100.0, 0.01
    # minute0: n=2 -> level 99.0; low 99.5 dips below lv but NOT below 99.0
    # minute1: n=0 -> level back to 100; low 99.9 fills at lv
    n = np.array([2, 0])
    lvl = D.level_vector(lv, sg, n)
    low = np.array([99.5, 99.9])
    assert D.find_fill(low[:1], lvl[:1]) is None  # shallow dip avoided
    assert D.find_fill(low, lvl) == 1
    # fill price is the level in force (lv again after n returns to 0)
    assert lvl[1] == lv


def test_deeper_fill_price_is_deep_level():
    lv, sg = 100.0, 0.01
    n = np.array([4, 4])
    lvl = D.level_vector(lv, sg, n)  # 98.0
    low = np.array([97.9, 99.0])
    assert D.find_fill(low, lvl) == 0


def test_exit_measured_from_actual_fill():
    sg, f = 0.01, 20
    px = 98.0  # deeper actual fill, NOT lv=100
    O, H, L, C = _flat(o=px)
    tp = px * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how = D.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "tp" and x == 30
    assert abs(ret - (tp / px - 1 - 2 * MK)) < 1e-12


def test_exit_stop_first_same_minute():
    sg, f, px = 0.01, 20, 98.0
    O, H, L, C = _flat(o=px)
    H[29] = px * (1 + sg) + 0.01
    C[29] = px * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    ret, x, how = D.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "stop"


def test_exit_backstop_beats_tp():
    sg, f, px = 0.01, 20, 98.0
    O, H, L, C = _flat(o=px)
    H[25] = px * (1 + sg) + 0.01
    L[25] = px * (1 - 8 * sg) - 0.01
    ret, x, how = D.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "backstop" and x == 25


def test_exit_timeout_funding():
    sg, f, px, o2 = 0.01, 20, 98.0, 98.1
    O, H, L, C = _flat(o=px)
    r0, _, h0 = D.outcome_from_fill(H, L, C, O, f, px, sg, o2, False)
    r1, _, h1 = D.outcome_from_fill(H, L, C, O, f, px, sg, o2, True)
    assert (h0, h1) == ("time", "time")
    assert abs((r0 - r1) - 0.0001) < 1e-12


def test_causality_fill_uses_only_closed_minutes():
    # n at live minute m uses C at T+m-1 only: a close flush visible at
    # minute 10 moves the level at minute 11, not at minute 10.
    o, sg = 100.0, 0.01
    thr = o * (1 - 2.5 * sg)
    closes = np.full((4, 3), 100.0)
    closes[0, 1] = thr - 0.01  # flush closes at second slot (m-1 for minute 11)
    n = D.n_vector(closes, np.full(4, o), np.full(4, sg))
    assert n.tolist() == [0, 1, 0]


def test_sigma_known_at_bar_open():
    opens = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    s = pd.Series(opens).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert np.isfinite(s[3]) and not np.isfinite(s[0])
    ref = pd.Series(opens[:4]).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12
