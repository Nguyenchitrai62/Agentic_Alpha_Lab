"""oc_rungcap tests: cap ordering + vendored B1/D0 spot checks (synthetic)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_rungcap"
sys.path.insert(0, str(OC))
import b1core as D


def test_cap_keeps_all_when_le3():
    assert D.cap_keep_mask([10, 20], [2.5, 5.0]) == [True, True]
    assert D.cap_keep_mask([10, 20, 30], [2.5, 3.0, 5.0]) == [True, True, True]
    assert D.cap_keep_mask([], []) == []


def test_cap_keeps_first3_by_f():
    # 5 fills in one bar: keep earliest 3, drop latest 2
    f = [200, 50, 100, 150, 30]
    k = [2.5, 2.5, 3.0, 4.0, 5.0]
    mask = D.cap_keep_mask(f, k)
    # ordered by f: idx4(30), idx1(50), idx2(100) kept
    assert mask == [False, True, True, False, True]


def test_cap_tie_break_shallow_first():
    # same fill minute: shallower k first (price falls through shallow levels first)
    f = [100, 100, 100, 100, 100]
    k = [5.0, 4.0, 3.5, 3.0, 2.5]
    mask = D.cap_keep_mask(f, k)
    # keep k=2.5, 3.0, 3.5 -> indices 4, 3, 2
    assert mask == [False, False, True, True, True]


def test_cap_exactly3_boundary():
    f = [10, 20, 30, 40]
    k = [2.5, 3.0, 3.5, 4.0]
    assert D.cap_keep_mask(f, k) == [True, True, True, False]


def test_b1_find_fill_strict():
    lv = 100.0
    assert D.find_fill(np.array([100.0, 100.0]), np.array([lv, lv])) is None
    assert D.find_fill(np.array([100.0, 99.99]), np.array([lv, lv])) == 1


def test_b1_n_vector_boundary():
    cmat = np.array([[97.5, 97.51], [90.0, 99.0], [100.0, 100.0], [97.49, 97.5]])
    oo = np.array([100.0, 100.0, 100.0, 100.0])
    ss = np.array([0.01, 0.01, 0.01, 0.01])
    assert D.n_vector(cmat, oo, ss).tolist() == [3, 1]


def test_b1_exit_tp_from_fill():
    sg, f, px = 0.01, 20, 98.0
    n = 240
    O = np.full(n, px)
    H = np.full(n, px)
    L = np.full(n, px)
    C = np.full(n, px)
    tp = px * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how = D.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "tp" and x == 30
    assert abs(ret - (tp / px - 1 - 2 * D.MAKER)) < 1e-12


def test_b1_exit_stop_first_same_minute():
    sg, f, px = 0.01, 20, 98.0
    n = 240
    O = np.full(n, px)
    H = np.full(n, px)
    L = np.full(n, px)
    C = np.full(n, px)
    H[29] = px * (1 + sg) + 0.01
    C[29] = px * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    _, _, how = D.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "stop"
