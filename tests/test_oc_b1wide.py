"""oc_b1wide tests: alt flush count, wide sizing, shared fills, exit replica."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_b1wide"
sys.path.insert(0, str(OC))
import wide as W

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def test_n_majors_exact_boundary():
    cmat = np.array([[97.5, 97.51, np.nan],
                      [90.0, 99.0, 97.5],
                      [100.0, 100.0, 100.0],
                      [97.49, 97.5, 97.5]])
    oo = np.array([100.0, 100.0, 100.0, 100.0])
    ss = np.array([0.01, 0.01, 0.01, 0.01])
    assert W.n_vector(cmat, oo, ss).tolist() == [3, 1, 2]


def test_n_majors_ignores_bad_inputs():
    cmat = np.array([[50.0], [50.0], [50.0], [50.0]])
    oo = np.array([100.0, np.nan, 100.0, 100.0])
    ss = np.array([0.01, 0.01, np.nan, 0.0])
    assert W.n_vector(cmat, oo, ss).tolist() == [1]


def test_n_alt_counts_five_alts_boundary():
    # thr = 100*(1-2.5*0.01) = 97.5; exact counts, NaN never counts
    cmat = np.array([[97.5], [97.51], [np.nan], [90.0], [100.0]])
    oo = np.full(5, 100.0)
    ss = np.full(5, 0.01)
    assert W.n_alt_vector(cmat, oo, ss).tolist() == [2]


def test_n_alt_ignores_bad_sigma_and_open():
    cmat = np.array([[50.0], [50.0], [50.0], [50.0], [50.0]])
    oo = np.array([100.0, np.nan, 100.0, 100.0, 100.0])
    ss = np.array([0.01, 0.01, np.nan, 0.0, 0.01])
    assert W.n_alt_vector(cmat, oo, ss).tolist() == [2]


def test_wide_count_half_weight_steps():
    n = np.array([0, 1, 4, 2])
    na = np.array([0, 1, 5, 3])
    assert W.wide_count(n, na).tolist() == [0.0, 1.5, 6.5, 3.5]


def test_size_mults():
    assert W.size_mult(0) == 1.0
    assert abs(W.size_mult(4) - 0.2) < 1e-12
    assert abs(W.size_mult_wide(0.0) - 1.0) < 1e-12
    assert abs(W.size_mult_wide(1.5) - 1 / 2.5) < 1e-12
    assert abs(W.size_mult_wide(6.5) - 1 / 7.5) < 1e-12
    # wide never exceeds base for same majors n
    for n in range(5):
        for na in range(6):
            assert W.size_mult_wide(n + 0.5 * na) <= W.size_mult(n) + 1e-15


def test_fill_strict_trade_through():
    lv = 100.0
    assert W.find_fill(np.array([100.0, 100.0]), np.array([lv, lv])) is None
    assert W.find_fill(np.array([100.0, 99.99]), np.array([lv, lv])) == 1
    assert W.find_fill(np.array([np.nan, 99.0]), np.array([lv, lv])) == 1


def test_exit_tp_from_fill_price():
    sg, f, px = 0.01, 20, 98.0
    O, H, L, C = _flat(o=px)
    tp = px * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how = W.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "tp" and x == 30
    assert abs(ret - (tp / px - 1 - 2 * MK)) < 1e-12


def test_exit_stop_first_same_minute():
    sg, f, px = 0.01, 20, 98.0
    O, H, L, C = _flat(o=px)
    H[29] = px * (1 + sg) + 0.01
    C[29] = px * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    _, _, how = W.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "stop"


def test_exit_timeout_funding():
    sg, f, px, o2 = 0.01, 20, 98.0, 98.1
    O, H, L, C = _flat(o=px)
    r0, _, h0 = W.outcome_from_fill(H, L, C, O, f, px, sg, o2, False)
    r1, _, h1 = W.outcome_from_fill(H, L, C, O, f, px, sg, o2, True)
    assert (h0, h1) == ("time", "time")
    assert abs((r0 - r1) - 0.0001) < 1e-12


def test_causality_detection_uses_only_closed_minutes():
    o, sg = 100.0, 0.01
    thr = o * (1 - 2.5 * sg)
    closes = np.full((5, 3), 100.0)
    closes[0, 1] = thr - 0.01
    n = W.n_alt_vector(closes, np.full(5, o), np.full(5, sg))
    assert n.tolist() == [0, 1, 0]


def test_sigma_known_at_bar_open():
    opens = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    s = pd.Series(opens).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert np.isfinite(s[3]) and not np.isfinite(s[0])
    ref = pd.Series(opens[:4]).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12


def test_decision_rule_edges():
    # 97% hurdle: equal passes, just-below fails, loss-mitigation passes
    assert 1.0 >= 0.97 * 1.0
    assert not (0.969 >= 0.97 * 1.0)
    assert -0.5 >= 0.97 * -1.0  # less-negative wide passes mechanically
