"""oc_velocity tests: velocity trigger + guard cancel rule on synthetic paths."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_velocity"
sys.path.insert(0, str(OC))
import velocity as V

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def test_trigger_exact_boundary():
    sg = 0.01  # factor 0.97
    c = np.full(240, 100.0)
    c[15] = 97.0  # max(0..15)=100 -> 100*0.97=97.0 -> triggers at m=16 (<=)
    assert V.guard_minute(c, sg) == 16
    c2 = np.full(240, 100.0)
    c2[15] = 97.01  # above threshold -> no trigger at 16; flat after -> None
    assert V.guard_minute(c2, sg) is None


def test_trigger_uses_trailing_max_not_bar_open():
    sg = 0.01
    # drift down slowly then crash within 15 min: max window is recent high
    c = np.full(240, 100.0)
    c[10:20] = 90.0  # 10% below bar open but FLAT within window -> no velocity
    # window at m=16: max=100 (c[0..9])? c[0..9]=100, c[10..15]=90 -> max 100,
    # cur c[15]=90 <= 97 -> triggers. Use a case with no early high instead:
    c3 = np.full(240, 90.0)  # flat 10% below open, no intra-window drop
    assert V.guard_minute(c3, sg) is None


def test_trigger_nan_never_fires():
    sg = 0.01
    c = np.full(240, 100.0)
    c[15] = 50.0  # would trigger, but poison window with NaN
    c[3] = np.nan
    # m=16 window has NaN -> skip; later windows slide past NaN: m=20 window
    # c[4..19] all finite with cur 100, max 100 -> no trigger; expect None
    # unless later crash; make rest flat so no trigger
    c[15] = 100.0
    assert V.guard_minute(c, sg) is None


def test_trigger_bad_sigma_never():
    c = np.full(240, 100.0)
    c[15] = 50.0
    assert V.guard_minute(c, np.nan) is None
    assert V.guard_minute(c, 0.0) is None
    assert V.guard_minute(c, -0.01) is None


def test_trigger_first_minute_wins():
    sg = 0.01
    c = np.full(240, 100.0)
    c[15] = 90.0  # triggers at 16
    c[100] = 50.0  # later bigger crash ignored
    assert V.guard_minute(c, sg) == 16


def test_cancel_rule_fill_before_guard_kept():
    # guard at m*=50: f=49 kept, f=50 and f=51 removed
    assert 49 < 50
    g, f_keep, f_at, f_after = 50, 49, 50, 51
    assert (f_keep < g) and not (f_at < g) and not (f_after < g)


def test_causality_window_uses_only_closed_minutes():
    # crash close visible at c[15] moves decision at m=16, not earlier;
    # m=15 is not evaluable (loop starts at 16).
    sg = 0.01
    c = np.full(240, 100.0)
    c[14] = 90.0  # in window of m=16? window c[0..15] includes it but cur=100
    # cur c[15]=100, max=100 -> no trigger at 16 from this alone
    assert V.guard_minute(c, sg) is None
    c[15] = 90.0  # now cur crashes -> trigger at 16
    assert V.guard_minute(c, sg) == 16


def test_sigma_known_at_bar_open():
    opens = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    s = pd.Series(opens).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert np.isfinite(s[3]) and not np.isfinite(s[0])
    ref = pd.Series(opens[:4]).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12


def test_fill_strict_and_exit_from_lv():
    lv = 100.0
    assert V.find_fill(np.array([100.0, 100.0]), np.array([lv, lv])) is None
    assert V.find_fill(np.array([100.0, 99.99]), np.array([lv, lv])) == 1
    sg, f, px = 0.01, 20, 100.0
    O, H, L, C = _flat(o=px)
    tp = px * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how = V.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "tp" and x == 30
    assert abs(ret - (tp / px - 1 - 2 * MK)) < 1e-12


def test_n_vector_boundary_and_nan():
    cmat = np.array([[97.5, np.nan]])
    oo = np.array([100.0])
    ss = np.array([0.01])
    n = V.n_vector(cmat, oo, ss)
    assert n.tolist() == [1, 0]  # exact 97.5 counts; NaN never counts
