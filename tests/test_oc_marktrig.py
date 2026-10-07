"""oc_marktrig tests: mark-trigger stops on synthetic tape + causality."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_marktrig"
sys.path.insert(0, str(OC))
import marktrig as T

MK, TK = 0.0002, 0.00055


def _bar(o=100.0):
    O = np.full(240, o)
    H = np.full(240, o)
    L = np.full(240, o)
    C = np.full(240, o)
    return O, H, L, C


def _prem_ext(v=0.0):
    return np.full((244,), v)


def test_build_mark_trailing5_mean():
    C = np.full(240, 100.0)
    pe = np.full((244,), 0.0)
    pe[4 + 10 - 4:4 + 10 + 1] = np.array([0.0, 0.001, 0.002, 0.003, 0.004])
    m = T.build_mark(C, pe)
    assert abs(m[10] - 100.0 * (1 + 0.002)) < 1e-9


def test_build_mark_nan_window_never_triggers():
    C = np.full(240, 100.0)
    pe = np.full((244,), np.nan)
    m = T.build_mark(C, pe)
    assert bool(np.isnan(m).all())


def test_build_mark_causality_future_premium_ignored():
    C = np.full(240, 100.0)
    pe = np.zeros((244,))
    m0 = T.build_mark(C, pe)
    pe2 = pe.copy()
    pe2[4 + 100:] = 0.05  # shock at/after offset 100
    m2 = T.build_mark(C, pe2)
    assert np.allclose(m0[:99], m2[:99], equal_nan=True)
    assert not np.allclose(m0[100:], m2[100:], equal_nan=True)


def test_mark_close5_avoids_wick_stop_but_last_fires():
    # last-price close dips below sl on a clock minute; mark stays above
    # (positive premium offsets the dip) -> BASE stops, MARK survives to time.
    O, H, L, C = _bar(100.0)
    lv, sg, f = 100.0, 0.01, 20
    sl = lv * (1 - 4 * sg)  # 96
    m = 24  # (24+1)%5==0 clock minute
    C[m] = sl - 0.1
    O[m + 1] = sl - 0.1
    o2 = 100.0
    rb, xb, hb = T.outcome_base(H, L, C, O, f, lv, sg, o2, False)
    assert hb == "stop" and xb == m + 1
    pe = _prem_ext(0.05)  # +500bps premium lifts every mark far above sl
    mark = T.build_mark(C, pe)
    assert float(mark[m]) > sl
    rm, xm, hm = T.outcome_mark(H, L, C, O, mark, f, lv, sg, o2, False)
    assert hm == "time" and xm == 240


def test_mark_close5_fires_when_mark_dips():
    O, H, L, C = _bar(100.0)
    lv, sg, f = 100.0, 0.01, 20
    sl = lv * (1 - 4 * sg)
    m = 24
    # last close stays above sl; negative premium drags the mark below sl
    C[m] = sl + 0.5
    O[m + 1] = 97.0
    pe = np.zeros((244,))
    pe[:] = -0.02  # -200bps
    mark = T.build_mark(C, pe)
    assert float(mark[m]) <= sl
    rb, _, hb = T.outcome_base(H, L, C, O, f, lv, sg, 100.0, False)
    assert hb == "time"
    rm, xm, hm = T.outcome_mark(H, L, C, O, mark, f, lv, sg, 100.0, False)
    assert hm == "stop" and xm == m + 1
    assert abs(rm - (97.0 / lv - 1 - MK - TK)) < 1e-12


def test_mark_backstop_ignores_wick_exits_next_open():
    # low wicks below bl but mark-close stays above -> BASE backstop, MARK time
    O, H, L, C = _bar(100.0)
    lv, sg, f = 100.0, 0.01, 20
    bl = lv * (1 - 8 * sg)  # 92
    L[30] = bl - 0.5
    O[30] = 100.0  # base exits at min(bl, open)=bl same minute
    rb, xb, hb = T.outcome_base(H, L, C, O, f, lv, sg, 100.0, False)
    assert hb == "backstop" and xb == 30
    assert abs(rb - (bl / lv - 1 - MK - TK)) < 1e-12
    pe = _prem_ext(0.0)
    mark = T.build_mark(C, pe)  # = close = 100 > bl everywhere
    rm, xm, hm = T.outcome_mark(H, L, C, O, mark, f, lv, sg, 100.0, False)
    assert hm == "time" and xm == 240


def test_mark_backstop_fires_on_mark_close_next_open():
    O, H, L, C = _bar(100.0)
    lv, sg, f = 100.0, 0.01, 20
    bl = lv * (1 - 8 * sg)
    t = 30
    C[t] = bl + 0.2  # last close above bl; low never touches either
    L[t] = bl + 0.2
    O[t + 1] = 93.0
    pe = np.zeros((244,))
    pe[:] = -0.02
    mark = T.build_mark(C, pe)
    assert float(mark[t]) <= bl
    rm, xm, hm = T.outcome_mark(H, L, C, O, mark, f, lv, sg, 100.0, False)
    assert hm == "backstop" and xm == t + 1
    assert abs(rm - (93.0 / lv - 1 - MK - TK)) < 1e-12


def test_mark_backstop_at_239_exits_o2_with_funding():
    O, H, L, C = _bar(100.0)
    lv, sg, f = 100.0, 0.01, 20
    bl = lv * (1 - 8 * sg)
    C[239] = bl + 0.1
    pe = np.zeros((244,))
    pe[:] = -0.02
    mark = T.build_mark(C, pe)
    assert float(mark[239]) <= bl
    rm, xm, hm = T.outcome_mark(H, L, C, O, mark, f, lv, sg, 99.0, True)
    assert hm == "backstop" and xm == 240
    assert abs(rm - (99.0 / lv - 1 - MK - TK - 0.0001)) < 1e-12


def test_tp_unchanged_strict_and_stop_first():
    O, H, L, C = _bar(100.0)
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + sg)
    H[30] = tp  # exact touch is NOT strict
    rm, xm, hm = T.outcome_mark(H, L, C, O, T.build_mark(C, _prem_ext(0.0)), f, lv, sg, 100.0, False)
    assert hm == "time"
    H[30] = tp + 0.01
    rm, xm, hm = T.outcome_mark(H, L, C, O, T.build_mark(C, _prem_ext(0.0)), f, lv, sg, 100.0, False)
    assert hm == "tp" and xm == 30
    # same-minute mark stop + TP -> stop wins
    m = 24
    C[m] = lv * (1 - 4 * sg) - 0.5
    pe = _prem_ext(0.0)
    mark = T.build_mark(C, pe)
    H[m] = tp + 1.0
    O[m + 1] = 95.0
    rm, xm, hm = T.outcome_mark(H, L, C, O, mark, f, lv, sg, 100.0, False)
    assert hm == "stop"


def test_find_fill_strict():
    assert T.find_fill(np.array([100.0, 100.0]), 100.0) is None
    assert T.find_fill(np.array([100.0, 99.99]), 100.0) == 1


def test_n_uses_closed_minute_and_threshold():
    o, sg = 100.0, 0.01
    thr = o * (1 - 2.5 * sg)
    closes = np.full((4, 3), 100.0)
    closes[0, 1] = thr - 0.01
    closes[1, 1] = thr  # exactly at threshold counts
    n = T.n_vector(closes, np.full(4, o), np.full(4, sg))
    assert n.tolist() == [0, 2, 0]


def test_sigma_known_at_bar_open():
    opens = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    s = pd.Series(opens).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert np.isfinite(s[3]) and not np.isfinite(s[0])
    ref = pd.Series(opens[:4]).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12
