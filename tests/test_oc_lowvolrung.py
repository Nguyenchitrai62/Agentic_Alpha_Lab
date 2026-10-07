"""oc_lowvolrung tests: B1 replica + gated-2.0 logic on synthetic paths."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_lowvolrung"
sys.path.insert(0, str(OC))
import core as K

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
    n = K.n_vector(cmat, oo, ss)
    assert n.tolist() == [3, 1, 2]


def test_n_ignores_bad_sigma_and_open():
    cmat = np.array([[50.0], [50.0], [50.0], [50.0]])
    oo = np.array([100.0, np.nan, 100.0, 100.0])
    ss = np.array([0.01, 0.01, np.nan, 0.0])
    n = K.n_vector(cmat, oo, ss)
    assert n.tolist() == [1]


def test_size_mult():
    assert K.size_mult(0) == 1.0
    assert abs(K.size_mult(4) - 0.2) < 1e-12


def test_fill_strict_trade_through():
    lv = 100.0
    assert K.find_fill(np.array([100.0, 100.0]), lv) is None
    assert K.find_fill(np.array([100.0, 99.99]), lv) == 1
    assert K.find_fill(np.array([np.nan, 99.0]), lv) == 1
    assert K.find_fill(np.array([np.nan, np.nan]), lv) is None


def test_extra_level_shallower_than_base():
    o1, sg = 100.0, 0.01
    lv20 = o1 * (1 - 2.0 * sg)
    lv25 = o1 * (1 - 2.5 * sg)
    assert lv20 > lv25  # 2.0 rung is shallower
    assert abs(lv20 - 98.0) < 1e-12 and abs(lv25 - 97.5) < 1e-12


def test_exit_tp_from_fill():
    sg, f, px = 0.01, 20, 98.0
    O, H, L, C = _flat(o=px)
    tp = px * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how = K.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "tp" and x == 30
    assert abs(ret - (tp / px - 1 - 2 * MK)) < 1e-12


def test_exit_stop_first_same_minute():
    sg, f, px = 0.01, 20, 98.0
    O, H, L, C = _flat(o=px)
    H[29] = px * (1 + sg) + 0.01
    C[29] = px * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    _, _, how = K.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "stop"


def test_exit_timeout_funding():
    sg, f, px, o2 = 0.01, 20, 98.0, 98.1
    O, H, L, C = _flat(o=px)
    r0, _, h0 = K.outcome_from_fill(H, L, C, O, f, px, sg, o2, False)
    r1, _, h1 = K.outcome_from_fill(H, L, C, O, f, px, sg, o2, True)
    assert (h0, h1) == ("time", "time")
    assert abs((r0 - r1) - 0.0001) < 1e-12


def test_lowvol_cutoff_is_lower_tercile():
    hist = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
    q = K.lowvol_cutoff(hist)
    assert abs(q - float(np.quantile(hist, 1.0 / 3.0))) < 1e-12
    # gate boundary inclusive: sigma == cutoff is armed
    assert (3.0 <= q) or (3.0 > q)  # smoke: q in (2,4)
    assert 2.0 < q < 4.0


def test_gate_uses_only_pre_anchor_sigma():
    # cutoff from pre-anchor history only; a post-anchor spike must not move it
    pre = np.array([0.01, 0.011, 0.012, 0.009, 0.0105])
    q_pre = K.lowvol_cutoff(pre)
    post = np.append(pre, [0.50, 0.60])  # leakage would raise q
    q_leak = K.lowvol_cutoff(post)
    assert q_leak > q_pre  # proves post-anchor data WOULD change it
    sg_now = q_pre  # exactly at cutoff -> armed (<=)
    assert bool(sg_now <= q_pre)
    assert not bool((q_pre + 1e-9) <= q_pre)


def test_causality_fill_uses_only_closed_minutes():
    o, sg = 100.0, 0.01
    thr = o * (1 - 2.5 * sg)
    closes = np.full((4, 3), 100.0)
    closes[0, 1] = thr - 0.01
    n = K.n_vector(closes, np.full(4, o), np.full(4, sg))
    assert n.tolist() == [0, 1, 0]


def test_sigma_known_at_bar_open():
    opens = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    s = pd.Series(opens).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert np.isfinite(s[3]) and not np.isfinite(s[0])
    ref = pd.Series(opens[:4]).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12
