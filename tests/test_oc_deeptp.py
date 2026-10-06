"""oc_deeptp tests: B1 static fill + mu-parameterised D0 exit on synthetic paths."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_deeptp"
sys.path.insert(0, str(OC))
import quick as Q

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def test_n_counts_flushers_exact_boundary():
    cmat = np.array([[97.5, 97.51, np.nan],
                      [90.0, 99.0, 97.5],
                      [100.0, 100.0, 100.0],
                      [97.49, 97.5, 97.5]])
    oo = np.array([100.0, 100.0, 100.0, 100.0])
    ss = np.array([0.01, 0.01, 0.01, 0.01])
    n = Q.n_vector(cmat, oo, ss)
    assert n.tolist() == [3, 1, 2]


def test_n_ignores_bad_sigma_and_open():
    cmat = np.array([[50.0], [50.0], [50.0], [50.0]])
    oo = np.array([100.0, np.nan, 100.0, 100.0])
    ss = np.array([0.01, 0.01, np.nan, 0.0])
    n = Q.n_vector(cmat, oo, ss)
    assert n.tolist() == [1]


def test_size_mult():
    assert Q.size_mult(0) == 1.0
    assert abs(Q.size_mult(4) - 0.2) < 1e-12


def test_fill_strict_trade_through():
    lv = 100.0
    assert Q.find_fill(np.array([100.0, 100.0]), lv) is None
    assert Q.find_fill(np.array([100.0, 99.99]), lv) == 1
    assert Q.find_fill(np.array([np.nan, np.nan]), lv) is None


def test_mu10_matches_d0_math():
    sg, f, px = 0.01, 20, 97.0
    O, H, L, C = _flat(o=px)
    tp = px * (1 + 1.0 * sg)
    H[30] = tp + 0.01
    ret, x, how = Q.outcome_mu(H, L, C, O, f, px, sg, 1.0, 99.0, False)
    assert how == "tp" and x == 30
    assert abs(ret - (tp / px - 1 - 2 * MK)) < 1e-12


def test_quick_tp_hits_earlier_and_cheaper():
    # slow drift: crosses +0.5% at 30, +1.0% only at 60 -> QUICK exits first
    sg, f, px = 0.01, 20, 100.0
    O, H, L, C = _flat(o=px)
    H[30] = px * (1 + 0.5 * sg) + 0.01
    H[60] = px * (1 + 1.0 * sg) + 0.01
    rq, xq, hq = Q.outcome_mu(H, L, C, O, f, px, sg, 0.5, 99.0, False)
    rb, xb, hb = Q.outcome_mu(H, L, C, O, f, px, sg, 1.0, 99.0, False)
    assert (hq, hb) == ("tp", "tp")
    assert xq == 30 and xb == 60
    assert rq < rb  # quicker TP banks a smaller gain
    assert abs(rq - (0.5 * sg - 2 * MK)) < 1e-9


def test_quick_tp_rescues_rung_that_base_times_out():
    # peaks between 0.5 and 1.0 sigma, then fades to a timeout below fill
    sg, f, px = 0.01, 20, 100.0
    O, H, L, C = _flat(o=px)
    H[30] = px * (1 + 0.5 * sg) + 0.01
    o2 = px * (1 - 0.01)
    rq, _, hq = Q.outcome_mu(H, L, C, O, f, px, sg, 0.5, o2, False)
    rb, _, hb = Q.outcome_mu(H, L, C, O, f, px, sg, 1.0, o2, False)
    assert hq == "tp" and hb == "time"
    assert rq > 0 > rb


def test_exit_stop_first_same_minute():
    sg, f, px = 0.01, 20, 98.0
    O, H, L, C = _flat(o=px)
    H[29] = px * (1 + 0.5 * sg) + 0.01  # would trigger the quick TP ...
    C[29] = px * (1 - 4 * sg) - 0.01    # ... but the close5 stop fires too
    assert (29 + 1) % 5 == 0
    ret, x, how = Q.outcome_mu(H, L, C, O, f, px, sg, 0.5, 99.0, False)
    assert how == "stop"


def test_exit_backstop_beats_quick_tp():
    sg, f, px = 0.01, 20, 98.0
    O, H, L, C = _flat(o=px)
    H[25] = px * (1 + 0.5 * sg) + 0.01
    L[25] = px * (1 - 8 * sg) - 0.01
    ret, x, how = Q.outcome_mu(H, L, C, O, f, px, sg, 0.5, 99.0, False)
    assert how == "backstop" and x == 25


def test_exit_timeout_funding():
    sg, f, px, o2 = 0.01, 20, 98.0, 98.1
    O, H, L, C = _flat(o=px)
    r0, _, h0 = Q.outcome_mu(H, L, C, O, f, px, sg, 0.5, o2, False)
    r1, _, h1 = Q.outcome_mu(H, L, C, O, f, px, sg, 0.5, o2, True)
    assert (h0, h1) == ("time", "time")
    assert abs((r0 - r1) - 0.0001) < 1e-12


def test_causality_fill_uses_only_closed_minutes():
    o, sg = 100.0, 0.01
    thr = o * (1 - 2.5 * sg)
    closes = np.full((4, 3), 100.0)
    closes[0, 1] = thr - 0.01
    n = Q.n_vector(closes, np.full(4, o), np.full(4, sg))
    assert n.tolist() == [0, 1, 0]


def test_sigma_known_at_bar_open():
    opens = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    s = pd.Series(opens).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert np.isfinite(s[3]) and not np.isfinite(s[0])
    ref = pd.Series(opens[:4]).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12
