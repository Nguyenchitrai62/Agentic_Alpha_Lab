"""oc_holdext tests: B1 fill + D0 base exit + extended-bar leg on synthetic paths."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_holdext"
sys.path.insert(0, str(OC))
import holdext as X

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


def test_base_tp_and_fees():
    sg, f, px = 0.01, 20, 100.0
    H, L, C, O = _flat(o=px)
    tp = px * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how = X.outcome_base(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "tp" and x == 30
    assert abs(ret - (tp / px - 1 - 2 * MK)) < 1e-12


def test_base_stop_first_same_minute():
    sg, f, px = 0.01, 20, 100.0
    H, L, C, O = _flat(o=px)
    H[29] = px * (1 + sg) + 0.01
    C[29] = px * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    _, _, how = X.outcome_base(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "stop"


def test_base_timeout_funding():
    sg, f, px, o2 = 0.01, 20, 100.0, 100.1
    H, L, C, O = _flat(o=px)
    r0, _, h0 = X.outcome_base(H, L, C, O, f, px, sg, o2, False)
    r1, _, h1 = X.outcome_base(H, L, C, O, f, px, sg, o2, True)
    assert (h0, h1) == ("time", "time")
    assert abs((r0 - r1) - FD) < 1e-12


def test_pair_non_timeout_needs_no_second_bar():
    # base TP: second-bar arrays all-NaN must be ignored, extended == base
    sg, f, px = 0.01, 20, 100.0
    H, L, C, O = _flat(o=px)
    H[30] = px * (1 + sg) + 0.01
    H1, L1, C1, O1 = _nan240()
    b, bx, bh, e, ex, eh, extd = X.outcome_pair(
        H, L, C, O, f, px, sg, 99.0, False, H1, L1, C1, O1, np.nan, False)
    assert extd is False and bh == eh == "tp" and bx == ex == 30
    assert abs(b - e) < 1e-12


def test_base_stop_at_239_is_stop_not_extended():
    # close5 signal at the last clock minute exits at o2 but counts as STOP
    sg, f, px = 0.01, 20, 100.0
    H, L, C, O = _flat(o=px)
    assert (239 + 1) % 5 == 0
    C[239] = px * (1 - 4 * sg) - 0.01
    b, bx, bh, _, _, _, extd = X.outcome_pair(
        H, L, C, O, f, px, sg, 101.0, False, *_nan240(), np.nan, False)
    assert bh == "stop" and bx == 240 and extd is False


def test_pair_timeout_runs_extension_tp_with_mid_fund():
    sg, f, px = 0.01, 20, 100.0
    H, L, C, O = _flat(o=px)  # base: pure timeout
    H1, L1, C1, O1 = _flat(o=px)
    tp = px * (1 + sg)
    H1[10] = tp + 0.01
    b, _, bh, e, ex, eh, extd = X.outcome_pair(
        H, L, C, O, f, px, sg, 100.0, True, H1, L1, C1, O1, 100.0, False)
    assert bh == "time" and extd is True
    assert eh == "tp" and ex == 250
    assert abs(e - (tp / px - 1 - 2 * MK - FD)) < 1e-12  # mid fund (held T+240)


def test_ext_timeout_funding_zero_one_two():
    sg, f, px = 0.01, 20, 100.0
    H, L, C, O = _flat(o=px)
    H1, L1, C1, O1 = _flat(o=px)  # second bar flat -> timeout at o3
    o3 = 101.0
    base_net = o3 / px - 1 - MK - TK
    r, x, h = X.outcome_ext_phase(H1, L1, C1, O1, px, sg, o3, False, False)
    assert (x, h) == (480, "time") and abs(r - base_net) < 1e-12
    r, _, _ = X.outcome_ext_phase(H1, L1, C1, O1, px, sg, o3, True, False)
    assert abs(r - (base_net - FD)) < 1e-12
    r, _, _ = X.outcome_ext_phase(H1, L1, C1, O1, px, sg, o3, True, True)
    assert abs(r - (base_net - 2 * FD)) < 1e-12


def test_ext_clock_continuity_first_clock_is_244():
    # offset 240 (i=0, (241)%5=1) is NOT a clock minute; first is i=4 (offset 244)
    sg, f, px = 0.01, 20, 100.0
    H, L, C, O = _flat(o=px)
    H1, L1, C1, O1 = _flat(o=px)
    sl = px * (1 - 4 * sg)
    C1[0] = sl - 0.01  # not a clock minute -> ignored
    C1[4] = sl - 0.01  # clock minute -> stop, exit at open of i=5
    O1[5] = 99.0
    r, x, h = X.outcome_ext_phase(H1, L1, C1, O1, px, sg, 101.0, False, False)
    assert h == "stop" and x == 245
    assert abs(r - (99.0 / px - 1 - MK - TK)) < 1e-12


def test_ext_stop_beats_tp_same_minute():
    sg, f, px = 0.01, 20, 100.0
    H, L, C, O = _flat(o=px)
    H1, L1, C1, O1 = _flat(o=px)
    C1[9] = px * (1 - 4 * sg) - 0.01  # i=9 -> offset 249, (250)%5==0 clock
    H1[9] = px * (1 + sg) + 0.01
    assert (249 + 1) % 5 == 0
    _, _, h = X.outcome_ext_phase(H1, L1, C1, O1, px, sg, 101.0, False, False)
    assert h == "stop"


def test_ext_backstop_beats_tp_and_gap_pays_open():
    sg, f, px = 0.01, 20, 100.0
    H, L, C, O = _flat(o=px)
    H1, L1, C1, O1 = _flat(o=px)
    bl = px * (1 - 8 * sg)
    H1[25] = px * (1 + sg) + 0.01
    L1[25] = bl - 0.01
    O1[25] = bl - 0.50  # gap below bl pays the open
    r, x, h = X.outcome_ext_phase(H1, L1, C1, O1, px, sg, 101.0, False, False)
    assert h == "backstop" and x == 265
    assert abs(r - ((bl - 0.50) / px - 1 - MK - TK)) < 1e-12


def test_ext_stop_at_479_exits_at_o3():
    sg, f, px = 0.01, 20, 100.0
    H, L, C, O = _flat(o=px)
    H1, L1, C1, O1 = _flat(o=px)
    assert (479 + 1) % 5 == 0
    C1[239] = px * (1 - 4 * sg) - 0.01
    r, x, h = X.outcome_ext_phase(H1, L1, C1, O1, px, sg, 102.0, True, True)
    assert h == "stop" and x == 480
    assert abs(r - (102.0 / px - 1 - MK - TK - 2 * FD)) < 1e-12


def test_pair_double_timeout_nan_o3():
    sg, f, px = 0.01, 20, 100.0
    H, L, C, O = _flat(o=px)
    H1, L1, C1, O1 = _flat(o=px)
    b, _, bh, e, _, eh, extd = X.outcome_pair(
        H, L, C, O, f, px, sg, 100.0, False, H1, L1, C1, O1, np.nan, False)
    assert bh == "time" and extd is True
    assert eh == "time" and np.isnan(e) and np.isfinite(b)  # caller drops pair


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
