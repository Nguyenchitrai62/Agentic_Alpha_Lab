"""oc_ewmasig tests: B1 static-level fill + D0-from-fill exit, EWMA sigma checks."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_ewmasig"
sys.path.insert(0, str(OC))
import ewma as E

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def _ewma(r, halflife=60, min_periods=120):
    return r.ewm(halflife=halflife, min_periods=min_periods, adjust=True).std(bias=False).shift(1)


def test_n_counts_flushers_exact_boundary():
    cmat = np.array([[97.5, 97.51, np.nan],
                      [90.0, 99.0, 97.5],
                      [100.0, 100.0, 100.0],
                      [97.49, 97.5, 97.5]])
    oo = np.array([100.0, 100.0, 100.0, 100.0])
    ss = np.array([0.01, 0.01, 0.01, 0.01])
    n = E.n_vector(cmat, oo, ss)
    assert n.tolist() == [3, 1, 2]


def test_n_uses_arm_sigma():
    # wider sigma => higher distance threshold => FEWER flushes
    cmat = np.array([[97.0]])
    oo = np.array([100.0])
    n_wide = E.n_vector(cmat, oo, np.array([0.005]))   # thr 98.75 -> flush
    n_narrow = E.n_vector(cmat, oo, np.array([0.02]))  # thr 95.0 -> no flush
    assert n_wide.tolist() == [1]
    assert n_narrow.tolist() == [0]


def test_size_mult():
    assert E.size_mult(0) == 1.0
    assert abs(E.size_mult(4) - 0.2) < 1e-12


def test_fill_strict_trade_through():
    lv = 100.0
    assert E.find_fill(np.array([100.0, 100.0]), np.array([lv, lv])) is None
    assert E.find_fill(np.array([100.0, 99.99]), np.array([lv, lv])) == 1


def test_exit_tp_scales_with_arm_sigma():
    f, px = 20, 100.0
    O, H, L, C = _flat(o=px)
    H[30] = px * (1 + 0.01) + 0.001
    r_base, _, h_base = E.outcome_from_fill(H, L, C, O, f, px, 0.01, 100.0, False)
    r_ad, _, h_ad = E.outcome_from_fill(H, L, C, O, f, px, 0.02, 100.0, False)
    assert h_base == "tp"
    assert h_ad == "time"
    assert abs(r_base - (px * (1 + 0.01) / px - 1 - 2 * MK)) < 1e-12


def test_exit_stop_wider_with_ewma_sigma():
    f, px = 20, 100.0
    O, H, L, C = _flat(o=px)
    C[29] = px * (1 - 4 * 0.01) - 0.01
    assert (29 + 1) % 5 == 0
    _, _, h_base = E.outcome_from_fill(H, L, C, O, f, px, 0.01, 100.0, False)
    _, _, h_ew = E.outcome_from_fill(H, L, C, O, f, px, 0.02, 100.0, False)
    assert h_base == "stop"
    assert h_ew == "time"


def test_exit_stop_first_same_minute():
    sg, f, px = 0.01, 20, 100.0
    O, H, L, C = _flat(o=px)
    H[29] = px * (1 + sg) + 0.01
    C[29] = px * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    _, _, how = E.outcome_from_fill(H, L, C, O, f, px, sg, 100.0, False)
    assert how == "stop"


def test_exit_timeout_funding():
    sg, f, px, o2 = 0.01, 20, 100.0, 100.1
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
    r = pd.Series(opens).pct_change()
    s = _ewma(r, halflife=60, min_periods=2).to_numpy()
    assert not np.isfinite(s[0])
    ref = _ewma(pd.Series(opens[:4]).pct_change(), halflife=60, min_periods=2).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12  # future spike at index 4 leaks nothing


def test_ewma_weights_recent_more_than_boxcar():
    # Same multiset of returns, spike recent vs spike old: EWMA must react more
    # to the recent spike than to the old one (boxcar rolling std is identical).
    r_recent = pd.Series(np.concatenate([[0.0] * 200, [0.05]]))
    r_old = pd.Series(np.concatenate([[0.05], [0.0] * 200]))
    e_recent = float(r_recent.ewm(halflife=60, min_periods=120, adjust=True).std(bias=False).iloc[-1])
    e_old = float(r_old.ewm(halflife=60, min_periods=120, adjust=True).std(bias=False).iloc[-1])
    b_recent = float(r_recent.rolling(360, min_periods=120).std(ddof=1).iloc[-1])
    b_old = float(r_old.rolling(360, min_periods=120).std(ddof=1).iloc[-1])
    assert np.isfinite(e_recent) and np.isfinite(e_old)
    assert abs(b_recent - b_old) < 1e-12  # boxcar is order-blind
    assert e_recent > e_old  # EWMA weights the recent spike more
