"""oc_earlystart tests: window edges, strict fills, n at own fill minute, D0 exits."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_earlystart"
sys.path.insert(0, str(OC))
import early as E

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def test_windows():
    assert (E.BASE_A, E.BASE_B) == (16, 238)
    assert (E.EARLY_A, E.EARLY_B) == (6, 238)


def test_fill_strict_trade_through():
    lv = 100.0
    assert E.find_fill(np.array([100.0, 100.0]), lv) is None
    assert E.find_fill(np.array([100.0, 99.99]), lv) == 1


def test_base_is_suffix_of_early_window():
    # early window slots 0..232 map to offsets 6..238; BASE starts at slot 10 (=16)
    lv = 100.0
    low = np.full(233, 100.0)
    low[3] = 99.0  # offset 9 -> EARLY-only region
    assert E.find_fill(low, lv) == 3
    assert E.find_fill(low[10:], lv) is None  # BASE sees no fill
    low2 = np.full(233, 100.0)
    low2[3] = 99.0
    low2[20] = 98.0  # offset 26 -> both arms fill, EARLY first
    assert E.find_fill(low2, lv) == 3
    assert E.find_fill(low2[10:], lv) == 10  # 20 - 10


def test_n_counts_flushers_exact_boundary():
    cmat = np.array([[97.5, 97.51, np.nan],
                      [90.0, 99.0, 97.5],
                      [100.0, 100.0, 100.0],
                      [97.49, 97.5, 97.5]])
    oo = np.array([100.0, 100.0, 100.0, 100.0])
    ss = np.array([0.01, 0.01, 0.01, 0.01])
    n = E.n_vector(cmat, oo, ss)
    assert n.tolist() == [3, 1, 2]


def test_n_ignores_bad_sigma_and_open():
    cmat = np.array([[50.0], [50.0], [50.0], [50.0]])
    oo = np.array([100.0, np.nan, 100.0, 100.0])
    ss = np.array([0.01, 0.01, np.nan, 0.0])
    n = E.n_vector(cmat, oo, ss)
    assert n.tolist() == [1]


def test_size_mult():
    assert E.size_mult(0) == 1.0
    assert abs(E.size_mult(4) - 0.2) < 1e-12


def test_exit_tp_from_fill_price():
    sg, f, px = 0.01, 20, 98.0
    O, H, L, C = _flat(o=px)
    tp = px * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how = E.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "tp" and x == 30
    assert abs(ret - (tp / px - 1 - 2 * MK)) < 1e-12


def test_exit_stop_first_same_minute():
    sg, f, px = 0.01, 20, 98.0
    O, H, L, C = _flat(o=px)
    H[29] = px * (1 + sg) + 0.01
    C[29] = px * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    ret, x, how = E.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "stop"


def test_exit_backstop_beats_tp():
    sg, f, px = 0.01, 20, 98.0
    O, H, L, C = _flat(o=px)
    H[25] = px * (1 + sg) + 0.01
    L[25] = px * (1 - 8 * sg) - 0.01
    ret, x, how = E.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "backstop" and x == 25


def test_exit_timeout_funding():
    sg, f, px, o2 = 0.01, 20, 98.0, 98.1
    O, H, L, C = _flat(o=px)
    r0, _, h0 = E.outcome_from_fill(H, L, C, O, f, px, sg, o2, False)
    r1, _, h1 = E.outcome_from_fill(H, L, C, O, f, px, sg, o2, True)
    assert (h0, h1) == ("time", "time")
    assert abs((r0 - r1) - 0.0001) < 1e-12


def test_causality_fill_uses_only_closed_minutes():
    o, sg = 100.0, 0.01
    thr = o * (1 - 2.5 * sg)
    closes = np.full((4, 3), 100.0)
    closes[0, 1] = thr - 0.01
    n = E.n_vector(closes, np.full(4, o), np.full(4, sg))
    assert n.tolist() == [0, 1, 0]


def test_sigma_known_at_bar_open():
    opens = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    s = pd.Series(opens).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert np.isfinite(s[3]) and not np.isfinite(s[0])
    ref = pd.Series(opens[:4]).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12
