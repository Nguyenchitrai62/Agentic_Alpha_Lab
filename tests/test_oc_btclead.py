"""oc_btclead tests: BTC-lead level + D0-from-fill exit on synthetic paths."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_btclead"
sys.path.insert(0, str(OC))
import btclead as B

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
    n = B.n_vector(cmat, oo, ss)
    assert n.tolist() == [3, 1, 2]


def test_btc_drop_boundary_and_nan():
    o, sg = 100.0, 0.01
    thr15 = o * (1 - 1.5 * sg)  # 98.5
    s = B.btc_drop_vector(np.array([thr15, thr15 + 0.01, np.nan]), o, sg)
    assert abs(s[0] - 1.5) < 1e-12
    assert s[1] < 1.5 and np.isnan(s[2])
    # bad sigma -> all NaN (no shift)
    assert np.isnan(B.btc_drop_vector(np.array([90.0]), o, 0.0)).all()


def test_beta_clip_and_fallback():
    assert B.beta_clip(np.nan) == 1.0
    assert B.beta_clip(np.inf) == 1.0
    assert B.beta_clip(-2.0) == 0.0
    assert B.beta_clip(5.0) == 3.0
    assert abs(B.beta_clip(1.234) - 1.234) < 1e-12


def test_beta_uses_only_history():
    # alt returns = 2x BTC returns -> beta 2
    btc = np.array([100.0, 101.0, 100.0, 102.0, 101.0, 103.0, 102.0, 104.0])
    alt = np.array([100.0, 102.0, 100.0, 104.0, 102.0, 106.0, 104.0, 108.0])
    b1 = B.compute_beta_series(alt, btc, window=4, min_periods=3)
    b2 = B.compute_beta_series(np.append(alt, 200.0), np.append(btc, 50.0),
                               window=4, min_periods=3)
    # appending a future bar must not change betas at earlier bars
    assert np.allclose(b1, b2[:len(b1)], equal_nan=True)
    # beta at bar 5 with window 4 over returns 1..4: alt~=2x btc (simple returns
    # from different bases are only approximately proportional)
    assert 1.9 < b1[5] < 2.1


def test_lead_level_formula_gate_and_cap():
    lv, sg, beta = 100.0, 0.01, 2.0
    s = np.array([1.5, 2.0, 1.49, np.nan, 3.0])
    ca = np.array([100.5, 100.5, 100.5, 100.5, 99.0])  # last: alt already at rung
    lvl = B.lead_level_vector(lv, sg, beta, s, ca)
    assert abs(lvl[0] - 100 * (1 - 0.5 * 2.0 * 1.5 * 0.01)) < 1e-12
    assert abs(lvl[1] - 100 * (1 - 0.5 * 2.0 * 2.0 * 0.01)) < 1e-12
    assert lvl[2] == lv and lvl[3] == lv and lvl[4] == lv  # s<1.5, NaN, alt at rung
    assert (lvl <= lv).all()  # never above lv


def test_lead_level_nan_beta_fallback_one():
    lv, sg = 100.0, 0.01
    s = np.array([2.0])
    ca = np.array([101.0])
    lvl = B.lead_level_vector(lv, sg, np.nan, s, ca)
    assert abs(lvl[0] - 100 * (1 - 0.5 * 1.0 * 2.0 * 0.01)) < 1e-12


def test_fill_strict_trade_through():
    lv = 100.0
    assert B.find_fill(np.array([100.0, 100.0]), np.array([lv, lv])) is None
    assert B.find_fill(np.array([100.0, 99.99]), np.array([lv, lv])) == 1


def test_exit_measured_from_actual_fill():
    sg, f = 0.01, 20
    px = 98.0
    O, H, L, C = _flat(o=px)
    tp = px * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how = B.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "tp" and x == 30
    assert abs(ret - (tp / px - 1 - 2 * MK)) < 1e-12


def test_exit_stop_first_same_minute():
    sg, f, px = 0.01, 20, 98.0
    O, H, L, C = _flat(o=px)
    H[29] = px * (1 + sg) + 0.01
    C[29] = px * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    ret, x, how = B.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "stop"


def test_causality_signal_uses_only_closed_minutes():
    # BTC flush closing at slot 1 moves s (and the level) at slot 1's minute,
    # which is decided from C at T+m-1 only; shifting the NEXT close must not
    # change the earlier level.
    o, sg, lv, beta = 100.0, 0.01, 99.0, 1.0
    thr = o * (1 - 1.5 * sg)
    c1 = np.array([100.0, thr - 0.01, 100.0])
    c2 = np.array([100.0, thr - 0.01, thr - 5.0])
    ca = np.array([100.0, 100.0, 100.0])
    l1 = B.lead_level_vector(lv, sg, beta, B.btc_drop_vector(c1, o, sg), ca)
    l2 = B.lead_level_vector(lv, sg, beta, B.btc_drop_vector(c2, o, sg), ca)
    assert l1[0] == lv and l1[1] < lv  # flush visible at slot 1 deepens slot 1
    assert l1[0] == l2[0] and l1[1] == l2[1]  # later close does not rewrite history


def test_sigma_known_at_bar_open():
    opens = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    s = pd.Series(opens).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert np.isfinite(s[3]) and not np.isfinite(s[0])
    ref = pd.Series(opens[:4]).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12
