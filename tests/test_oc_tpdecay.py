"""oc_tpdecay tests: B1 fill + base vs decaying-TP exits on synthetic paths."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_tpdecay"
sys.path.insert(0, str(OC))
import tpdecay as D

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def test_tp_schedule_endpoints():
    px, sg, f = 100.0, 0.01, 20
    assert abs(D.tp_decay_level(px, sg, f, f) - px * (1 + sg)) < 1e-12
    assert abs(D.tp_decay_level(px, sg, f, 240) - px * (1 + 0.5 * sg)) < 1e-12


def test_tp_schedule_decays_linearly():
    px, sg, f = 100.0, 0.02, 40
    v = D.tp_decay_vector(px, sg, f, f + 1, 240)
    assert len(v) == 240 - (f + 1)
    assert (np.diff(v) < 0).all()  # strictly decreasing
    assert abs(v[0] - D.tp_decay_level(px, sg, f, f + 1)) < 1e-12
    assert v[-1] > px * (1 + 0.5 * sg) and v[0] < px * (1 + sg)


def test_tp_uses_only_fill_state():
    # TP(t) is a pure function of px/sg/f: same inputs -> same schedule
    # regardless of any price path (causal by construction).
    a = D.tp_decay_vector(100.0, 0.01, 30, 31, 240)
    b = D.tp_decay_vector(100.0, 0.01, 30, 31, 240)
    assert np.array_equal(a, b)
    c = D.tp_decay_vector(100.0, 0.02, 30, 31, 240)
    assert not np.array_equal(a, c)


def test_find_fill_strict():
    assert D.find_fill(np.array([100.0, 100.0]), 100.0) is None
    assert D.find_fill(np.array([100.0, 99.99]), 100.0) == 1
    assert D.find_fill(np.array([np.nan, np.nan]), 100.0) is None


def test_n_counts_flushers_exact_boundary():
    cmat = np.array([[97.5, 97.51, np.nan],
                      [90.0, 99.0, 97.5],
                      [100.0, 100.0, 100.0],
                      [97.49, 97.5, 97.5]])
    oo = np.array([100.0, 100.0, 100.0, 100.0])
    ss = np.array([0.01, 0.01, 0.01, 0.01])
    assert D.n_vector(cmat, oo, ss).tolist() == [3, 1, 2]


def test_base_exit_fixed_tp():
    sg, f, px = 0.01, 20, 100.0
    O, H, L, C = _flat(o=px)
    tp = px * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how = D.outcome_base(H, L, C, O, f, px, sg, 99.0, False)
    assert (how, x) == ("tp", 30)
    assert abs(ret - (tp / px - 1 - 2 * MK)) < 1e-12


def test_decay_converts_late_timeout_into_tp():
    # High path sits at +0.7sg late in the bar: below the fixed +1.0sg TP
    # (base times out) but above the decayed ~0.5sg TP (decay fills).
    sg, f, px = 0.01, 20, 100.0
    O, H, L, C = _flat(o=px)
    t = 230
    tp_t = D.tp_decay_level(px, sg, f, t)
    assert px * (1 + 0.5 * sg) < tp_t < px * (1 + sg)
    H[t] = tp_t + 0.01
    rb, xb, hb = D.outcome_base(H, L, C, O, f, px, sg, 100.0, False)
    rd, xd, hd, tp = D.outcome_decay(H, L, C, O, f, px, sg, 100.0, False)
    assert hb == "time"  # base misses
    assert hd == "tp" and xd == t
    assert abs(tp - tp_t) < 1e-9
    assert abs(rd - (tp_t / px - 1 - 2 * MK)) < 1e-12


def test_decay_early_tp_matches_base_level():
    # Touch one minute after the fill: decay TP ~= fixed TP.
    sg, f, px = 0.01, 20, 100.0
    O, H, L, C = _flat(o=px)
    H[f + 1] = px * (1 + sg) + 0.01
    rb, _, hb = D.outcome_base(H, L, C, O, f, px, sg, 99.0, False)
    rd, xd, hd, tp = D.outcome_decay(H, L, C, O, f, px, sg, 99.0, False)
    assert hb == "tp" and hd == "tp" and xd == f + 1
    assert abs(tp - D.tp_decay_level(px, sg, f, f + 1)) < 1e-12
    assert abs(rd - (tp / px - 1 - 2 * MK)) < 1e-12


def test_decay_stop_first_same_minute():
    sg, f, px = 0.01, 20, 100.0
    O, H, L, C = _flat(o=px)
    t = 29
    assert (t + 1) % 5 == 0
    H[t] = D.tp_decay_level(px, sg, f, t) + 0.01
    C[t] = px * (1 - 4 * sg) - 0.01
    _, _, hb = D.outcome_base(H, L, C, O, f, px, sg, 99.0, False)
    rd, _, hd, _ = D.outcome_decay(H, L, C, O, f, px, sg, 99.0, False)
    assert hb == "stop" and hd == "stop"


def test_decay_backstop_beats_tp():
    sg, f, px = 0.01, 20, 100.0
    O, H, L, C = _flat(o=px)
    t = 25
    H[t] = D.tp_decay_level(px, sg, f, t) + 0.01
    L[t] = px * (1 - 8 * sg) - 0.01
    _, _, hb = D.outcome_base(H, L, C, O, f, px, sg, 99.0, False)
    _, x, hd, _ = D.outcome_decay(H, L, C, O, f, px, sg, 99.0, False)
    assert hd == "backstop" and x == t


def test_timeout_funding_parity():
    sg, f, px, o2 = 0.01, 20, 100.0, 100.1
    O, H, L, C = _flat(o=px)
    r0, _, h0 = D.outcome_base(H, L, C, O, f, px, sg, o2, False)
    r1, _, h1 = D.outcome_base(H, L, C, O, f, px, sg, o2, True)
    r2, _, h2, _ = D.outcome_decay(H, L, C, O, f, px, sg, o2, False)
    r3, _, h3, _ = D.outcome_decay(H, L, C, O, f, px, sg, o2, True)
    assert (h0, h1, h2, h3) == ("time", "time", "time", "time")
    assert abs((r0 - r1) - 0.0001) < 1e-12
    assert abs((r2 - r3) - 0.0001) < 1e-12
    assert abs(r0 - r2) < 1e-12  # same timeout price both arms


def test_causality_fill_uses_only_closed_minutes():
    o, sg = 100.0, 0.01
    thr = o * (1 - 2.5 * sg)
    closes = np.full((4, 3), 100.0)
    closes[0, 1] = thr - 0.01
    assert D.n_vector(closes, np.full(4, o), np.full(4, sg)).tolist() == [0, 1, 0]


def test_sigma_known_at_bar_open():
    opens = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    s = pd.Series(opens).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert np.isfinite(s[3]) and not np.isfinite(s[0])
    ref = pd.Series(opens[:4]).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12
