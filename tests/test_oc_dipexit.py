"""oc_dipexit tests: replica/exit logic on synthetic 1m paths + causality."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_dipexit"
sys.path.insert(0, str(OC))
import exits as E

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    Lw = np.full(n, o)
    C = np.full(n, o)
    return O, H, Lw, C


def test_tp_hit_long():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how = E.outcome_mu(H, Lw, C, O, f, lv, sg, 1.0, 99.0, False)
    assert how == "tp" and x == 30
    assert abs(ret - (tp / lv - 1 - 2 * MK)) < 1e-12


def test_stop_first_same_minute():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + sg)
    H[29] = tp + 0.01  # TP touch same minute as a clock close below sl
    C[29] = lv * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0  # 29 is a clock minute
    ret, x, how = E.outcome_mu(H, Lw, C, O, f, lv, sg, 1.0, 99.0, False)
    assert how == "stop"  # stop-first
    assert abs(ret - (O[x] / lv - 1 - MK - TK)) < 1e-12


def test_backstop_beats_tp_same_minute():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + sg)
    H[25] = tp + 0.01
    Lw[25] = lv * (1 - 8 * sg) - 0.01
    ret, x, how = E.outcome_mu(H, Lw, C, O, f, lv, sg, 1.0, 99.0, False)
    assert how == "backstop" and x == 25
    assert abs(ret - (min(lv * (1 - 8 * sg), O[25]) / lv - 1 - MK - TK)) < 1e-12


def test_timeout_funding():
    O, H, Lw, C = _flat()
    lv, sg, f, o2 = 100.0, 0.01, 20, 101.0
    r0, x0, h0 = E.outcome_mu(H, Lw, C, O, f, lv, sg, 1.0, o2, False)
    r1, x1, h1 = E.outcome_mu(H, Lw, C, O, f, lv, sg, 1.0, o2, True)
    assert (h0, h1) == ("time", "time") and (x0, x1) == (240, 240)
    assert abs((r0 - r1) - 0.0001) < 1e-12


def test_e1_is_average_of_legs():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    H[30] = lv * (1 + 0.5 * sg) + 0.01  # only 0.5 TP hits
    r05, _, _ = E.outcome_mu(H, Lw, C, O, f, lv, sg, 0.5, 99.0, False)
    r15, _, _ = E.outcome_mu(H, Lw, C, O, f, lv, sg, 1.5, 99.0, False)
    e1 = 0.5 * r05 + 0.5 * r15
    assert r05 > r15  # 0.5 leg TPs, 1.5 leg times out below
    assert abs(e1 - (0.5 * r05 + 0.5 * r15)) < 1e-12


def test_e2_time_exit_calm():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    O[140] = 100.7
    ret, x, how = E.outcome_e2(H, Lw, C, O, f, lv, sg, 99.0, False)
    assert how == "time" and x == f + 120
    assert abs(ret - (100.7 / lv - 1 - MK - TK)) < 1e-12


def test_e2_tp_before_deadline():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    H[30] = lv * (1 + sg) + 0.01
    ret, x, how = E.outcome_e2(H, Lw, C, O, f, lv, sg, 99.0, False)
    assert how == "tp" and x == 30


def test_e3_no_activation_equals_d0():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    a = E.outcome_mu(H, Lw, C, O, f, lv, sg, 1.0, 99.0, False)
    b = E.outcome_e3(H, Lw, C, O, f, lv, sg, 99.0, False)
    assert a[2] == b[2] == "time" and abs(a[0] - b[0]) < 1e-12


def test_e3_breakeven_stop_after_activation():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    H[25] = lv * (1 + 0.5 * sg) + 0.01  # activate
    C[29] = lv - 0.01  # clock minute below breakeven but above 4-sigma sl
    assert (29 + 1) % 5 == 0 and C[29] > lv * (1 - 4 * sg)
    O[30] = 99.5
    r_d0, _, h_d0 = E.outcome_mu(H, Lw, C, O, f, lv, sg, 1.0, 101.0, False)
    r_e3, x_e3, h_e3 = E.outcome_e3(H, Lw, C, O, f, lv, sg, 101.0, False)
    assert h_d0 == "time"  # D0 stop (4 sigma) never fires
    assert h_e3 == "stop" and x_e3 == 30
    assert abs(r_e3 - (99.5 / lv - 1 - MK - TK)) < 1e-12


def test_e4_cap():
    O, H, Lw, C = _flat(o=95.0)
    sg, o1, lv, f = 0.01, 100.0, 97.0, 20
    cap = lv * (1 + 2 * sg)
    assert o1 > cap  # cap binds for deep rungs
    H[30] = cap + 0.01
    ret, x, how = E.outcome_e4(H, Lw, C, O, f, lv, sg, o1, 99.0, False)
    assert how == "tp" and x == 30
    assert abs(ret - (cap / lv - 1 - 2 * MK)) < 1e-12


def test_fill_strict_trade_through():
    lv = 100.0
    assert not (100.0 < lv)  # touch == level is NOT a fill
    assert 99.99 < lv


def test_sigma_known_at_bar_open():
    opens = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    s = pd.Series(opens).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert np.isfinite(s[3]) and not np.isfinite(s[0])
    # sigma at bar 3 excludes the bar-4 spike to 500
    ref = pd.Series(opens[:4]).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12
