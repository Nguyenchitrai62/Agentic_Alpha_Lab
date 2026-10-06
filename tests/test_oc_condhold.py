"""oc_condhold tests: B1 fill + D0 base exit + conditional (+4h iff in profit)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_condhold"
sys.path.insert(0, str(OC))
import condhold as X

MK, TK, FD = 0.0002, 0.00055, 0.0001


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return H, L, C, O


def _nan240():
    n = np.full(240, np.nan)
    return n, n.copy(), n.copy(), n.copy()


def test_n_counts_flushers_exact_boundary():
    cmat = np.array([[97.5, 97.51, np.nan],
                      [90.0, 99.0, 97.5],
                      [100.0, 100.0, 100.0],
                      [97.49, 97.5, 97.5]])
    oo = np.array([100.0, 100.0, 100.0, 100.0])
    ss = np.array([0.01, 0.01, 0.01, 0.01])
    assert X.n_vector(cmat, oo, ss).tolist() == [3, 1, 2]


def test_size_mult():
    assert X.size_mult(0) == 1.0
    assert abs(X.size_mult(4) - 0.2) < 1e-12


def test_fill_strict_trade_through():
    lv = 100.0
    assert X.find_fill(np.array([100.0, 100.0]), lv) is None
    assert X.find_fill(np.array([100.0, 99.99]), lv) == 1


def test_gate_boundary_flat_is_not_profit():
    # exactly flat net (o2 = px*(1+MK+TK)) -> gate FALSE, no fund
    px = 100.0
    o2 = px * (1 + MK + TK)
    assert X.in_profit(o2, px, False) is False
    assert X.in_profit(o2 + 1e-9, px, False) is True
    assert X.in_profit(o2 - 1e-9, px, False) is False


def test_gate_with_mid_funding():
    px = 100.0
    # without funding o2=100.1 would be profit; with mid fund it is not
    o2 = 100.08  # net ex-fund = 0.00005 > 0, net with fund = -0.00005 < 0
    assert X.in_profit(o2, px, False) is True
    assert X.in_profit(o2, px, True) is False
    o2b = px * (1 + MK + TK + FD)  # exactly flat with fund -> FALSE
    assert X.in_profit(o2b, px, True) is False
    assert X.in_profit(o2b + 1e-9, px, True) is True


def test_gate_nan_o2_never_profit():
    assert X.in_profit(np.nan, 100.0, False) is False
    assert X.in_profit(101.0, np.nan, False) is False


def test_pair_gate_false_needs_no_second_bar():
    # base timeout at a loss: second-bar all-NaN must be ignored, cond == base
    sg, f, px = 0.01, 20, 100.0
    H, L, C, O = _flat(o=px)  # base: pure timeout
    o2 = 99.0  # loss
    H1, L1, C1, O1 = _nan240()
    b, bx, bh, c, cx, ch, extd, gate = X.outcome_pair(
        H, L, C, O, f, px, sg, o2, False, H1, L1, C1, O1, np.nan, False)
    assert bh == "time" and gate is False and extd is False
    assert ch == "time" and cx == bx == 240
    assert abs(b - c) < 1e-12


def test_pair_non_timeout_needs_no_second_bar():
    sg, f, px = 0.01, 20, 100.0
    H, L, C, O = _flat(o=px)
    H[30] = px * (1 + sg) + 0.01
    H1, L1, C1, O1 = _nan240()
    b, bx, bh, c, cx, ch, extd, gate = X.outcome_pair(
        H, L, C, O, f, px, sg, 99.0, False, H1, L1, C1, O1, np.nan, False)
    assert extd is False and gate is False and bh == ch == "tp" and bx == cx == 30
    assert abs(b - c) < 1e-12


def test_pair_gate_true_runs_extension_tp_with_mid_fund():
    sg, f, px = 0.01, 20, 100.0
    H, L, C, O = _flat(o=px)  # base: pure timeout
    o2 = 100.10  # profit ex fees: 0.001 - 0.00075 = +0.00025 > 0
    H1, L1, C1, O1 = _flat(o=px)
    tp = px * (1 + sg)
    H1[10] = tp + 0.01
    b, _, bh, c, cx, ch, extd, gate = X.outcome_pair(
        H, L, C, O, f, px, sg, o2, True, H1, L1, C1, O1, 100.0, False)
    assert bh == "time" and gate is True and extd is True
    assert ch == "tp" and cx == 250
    assert abs(c - (tp / px - 1 - 2 * MK - FD)) < 1e-12
    assert b > 0  # gate only fires on winners


def test_pair_gate_true_timeout_pays_mid_plus_final_fund():
    sg, f, px = 0.01, 20, 100.0
    H, L, C, O = _flat(o=px)
    o2 = 100.10
    H1, L1, C1, O1 = _flat(o=px)  # second bar flat -> timeout at o3
    o3 = 101.0
    b, _, bh, c, cx, ch, extd, gate = X.outcome_pair(
        H, L, C, O, f, px, sg, o2, True, H1, L1, C1, O1, o3, True)
    assert bh == "time" and gate is True and extd is True
    assert (cx, ch) == (480, "time")
    assert abs(c - (o3 / px - 1 - MK - TK - 2 * FD)) < 1e-12


def test_base_stop_at_239_is_stop_not_gated():
    sg, f, px = 0.01, 20, 100.0
    H, L, C, O = _flat(o=px)
    assert (239 + 1) % 5 == 0
    C[239] = px * (1 - 4 * sg) - 0.01
    b, bx, bh, _, _, _, extd, gate = X.outcome_pair(
        H, L, C, O, f, px, sg, 101.0, False, *_nan240(), np.nan, False)
    assert bh == "stop" and bx == 240 and extd is False and gate is False


def test_ext_stop_beats_tp_same_minute_gated():
    sg, f, px = 0.01, 20, 100.0
    H, L, C, O = _flat(o=px)
    o2 = 100.10
    H1, L1, C1, O1 = _flat(o=px)
    C1[9] = px * (1 - 4 * sg) - 0.01  # i=9 -> offset 249, clock
    H1[9] = px * (1 + sg) + 0.01
    assert (249 + 1) % 5 == 0
    _, _, _, _, _, ch, extd, gate = X.outcome_pair(
        H, L, C, O, f, px, sg, o2, False, H1, L1, C1, O1, 101.0, False)
    assert gate is True and extd is True and ch == "stop"


def test_pair_double_timeout_nan_o3_drops():
    sg, f, px = 0.01, 20, 100.0
    H, L, C, O = _flat(o=px)
    H1, L1, C1, O1 = _flat(o=px)
    b, _, bh, c, _, ch, extd, gate = X.outcome_pair(
        H, L, C, O, f, px, sg, 100.10, False, H1, L1, C1, O1, np.nan, False)
    assert bh == "time" and gate is True and extd is True
    assert ch == "time" and np.isnan(c) and np.isfinite(b)  # caller drops pair


def test_causality_fill_uses_only_closed_minutes():
    o, sg = 100.0, 0.01
    thr = o * (1 - 2.5 * sg)
    closes = np.full((4, 3), 100.0)
    closes[0, 1] = thr - 0.01
    n = X.n_vector(closes, np.full(4, o), np.full(4, sg))
    assert n.tolist() == [0, 1, 0]


def test_sigma_known_at_bar_open():
    opens = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    s = pd.Series(opens).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert np.isfinite(s[3]) and not np.isfinite(s[0])
    ref = pd.Series(opens[:4]).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12
