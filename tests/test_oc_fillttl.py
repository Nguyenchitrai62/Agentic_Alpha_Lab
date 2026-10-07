"""oc_fillttl tests: fill-relative exits on synthetic tape + causality."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_fillttl"
sys.path.insert(0, str(OC))
import fillttl as F

MK, TK = 0.0002, 0.00055


def _tape(n=600, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def test_d0_matches_oc_dipexit_shape():
    O, H, L, C = _tape(240)
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how = F.outcome_d0(H, L, C, O, f, lv, sg, 99.0, False)
    assert how == "tp" and x == 30
    assert abs(ret - (tp / lv - 1 - 2 * MK)) < 1e-12


def test_t240_time_exit_calm():
    O, H, L, C = _tape(600)
    lv, sg, f, base = 100.0, 0.01, 200, 0
    O[base + f + 240] = 100.7
    ret, x, how = F.outcome_fillrel(H, L, C, O, base, f, lv, sg, f + 240, 0)
    assert how == "time" and x == f + 240
    assert abs(ret - (100.7 / lv - 1 - MK - TK)) < 1e-12


def test_t240_funding_per_settlement():
    O, H, L, C = _tape(600)
    lv, sg, f, base = 100.0, 0.01, 200, 0
    O[base + f + 240] = 100.7
    r0, _, _ = F.outcome_fillrel(H, L, C, O, base, f, lv, sg, f + 240, 0)
    r1, _, _ = F.outcome_fillrel(H, L, C, O, base, f, lv, sg, f + 240, 1)
    assert abs((r0 - r1) - 0.0001) < 1e-12


def test_t240_tp_before_deadline():
    O, H, L, C = _tape(600)
    lv, sg, f, base = 100.0, 0.01, 200, 0
    H[base + 210] = lv * (1 + sg) + 0.01
    ret, x, how = F.outcome_fillrel(H, L, C, O, base, f, lv, sg, f + 240, 0)
    assert how == "tp" and x == 210


def test_t240_late_fill_gets_full_window():
    # D0 would give a fill at f=230 only 10 minutes; T240 gives 240 minutes:
    # a TP at f+100 hits under T240 but is unreachable under D0.
    O, H, L, C = _tape(600)
    lv, sg, f, base = 100.0, 0.01, 230, 0
    H[base + f + 100] = lv * (1 + sg) + 0.01
    ret, x, how = F.outcome_fillrel(H, L, C, O, base, f, lv, sg, f + 240, 0)
    assert how == "tp" and x == f + 100
    # D0 bar slice cannot reach that offset (bar ends at 239)
    Hb, Lb, Cb, Ob = H[:240], L[:240], C[:240], O[:240]
    r0, x0, h0 = F.outcome_d0(Hb, Lb, Cb, Ob, f, lv, sg, 99.0, False)
    assert h0 in ("stop", "time", "backstop") and x0 <= 240


def test_t120_equals_d0_when_early():
    O, H, L, C = _tape(600)
    lv, sg, f, base = 100.0, 0.01, 100, 0
    # f+120=220 < 240 so x_time=240: same race as D0 on a calm tape
    r120, x120, h120 = F.outcome_fillrel(H, L, C, O, base, f, lv, sg, 240, 0)
    Hb, Lb, Cb, Ob = H[:240], L[:240], C[:240], O[:240]
    O[base + 240] = Ob[0]  # calm
    r0, x0, h0 = F.outcome_d0(Hb, Lb, Cb, Ob, f, lv, sg, float(O[base + 240]), False)
    assert (x120, h120) == (240, "time")
    assert abs(r120 - r0) < 1e-12


def test_t120_extends_when_late():
    O, H, L, C = _tape(600)
    lv, sg, f, base = 100.0, 0.01, 200, 0
    assert f + 120 > 240
    O[base + f + 120] = 100.5
    ret, x, how = F.outcome_fillrel(H, L, C, O, base, f, lv, sg, f + 120, 0)
    assert how == "time" and x == f + 120
    assert abs(ret - (100.5 / lv - 1 - MK - TK)) < 1e-12


def test_stop_first_same_minute_extended():
    O, H, L, C = _tape(600)
    lv, sg, f, base = 100.0, 0.01, 200, 0
    t = 209
    assert (t + 1) % 5 == 0
    H[base + t] = lv * (1 + sg) + 0.01
    C[base + t] = lv * (1 - 4 * sg) - 0.01
    ret, x, how = F.outcome_fillrel(H, L, C, O, base, f, lv, sg, f + 240, 0)
    assert how == "stop"


def test_backstop_beats_tp_extended():
    O, H, L, C = _tape(600)
    lv, sg, f, base = 100.0, 0.01, 200, 0
    H[base + 205] = lv * (1 + sg) + 0.01
    L[base + 205] = lv * (1 - 8 * sg) - 0.01
    ret, x, how = F.outcome_fillrel(H, L, C, O, base, f, lv, sg, f + 240, 0)
    assert how == "backstop" and x == 205


def test_stop_at_time_minute_pays_no_funding():
    O, H, L, C = _tape(600)
    lv, sg, f, base = 100.0, 0.01, 200, 0
    xt = f + 240
    m = xt - 1
    # force m to be a clock minute with close below sl
    m = m - ((m + 1) % 5)  # step back to a clock minute
    assert (m + 1) % 5 == 0
    C[base + m] = lv * (1 - 4 * sg) - 0.01
    O[base + m + 1] = 99.0
    r, x, h = F.outcome_fillrel(H, L, C, O, base, f, lv, sg, xt, 1)
    assert h == "stop" and x == m + 1
    assert abs(r - (99.0 / lv - 1 - MK - TK)) < 1e-12  # no funding on stop


def test_nan_never_triggers():
    O, H, L, C = _tape(600)
    lv, sg, f, base = 100.0, 0.01, 200, 0
    H[base + 210] = np.nan
    L[base + 210] = np.nan
    C[base + 210] = np.nan
    O[base + f + 240] = 100.3
    ret, x, how = F.outcome_fillrel(H, L, C, O, base, f, lv, sg, f + 240, 0)
    assert how == "time" and x == f + 240


def test_overlap_minutes():
    assert F.overlap_minutes(20, 240) == 0  # D0 never overlaps
    assert F.overlap_minutes(200, 440) == 440 - 256  # full overlap tail
    assert F.overlap_minutes(230, 350) == 350 - 256
    assert F.overlap_minutes(20, 260) == 260 - 256


def test_fill_strict_trade_through():
    assert F.find_fill(np.array([100.0, 100.0]), 100.0) is None
    assert F.find_fill(np.array([100.0, 99.99]), 100.0) == 1


def test_n_causality_uses_closed_minute():
    o, sg = 100.0, 0.01
    thr = o * (1 - 2.5 * sg)
    closes = np.full((4, 3), 100.0)
    closes[0, 1] = thr - 0.01
    n = F.n_vector(closes, np.full(4, o), np.full(4, sg))
    assert n.tolist() == [0, 1, 0]


def test_sigma_known_at_bar_open():
    opens = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    s = pd.Series(opens).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert np.isfinite(s[3]) and not np.isfinite(s[0])
    ref = pd.Series(opens[:4]).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12
