"""oc_b1soft tests: soft count ramp, hard boundaries, strict fill, D0 exit parity."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_b1soft"
sys.path.insert(0, str(OC))
import soft as S

OC_DEEP = ROOT / "research/tournament/oc_b1deeper"
sys.path.insert(0, str(OC_DEEP))
import deeper as D

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def test_d_vector_hand_values():
    o = np.array([100.0, 100.0, 100.0, 100.0])
    sg = np.array([0.01, 0.01, 0.01, 0.01])
    c = np.array([97.5, 99.0, 100.0, 101.0])
    d = S.d_vector(c, o, sg)
    assert abs(d[0] - 2.5) < 1e-12  # exactly 2.5 sigma below
    assert abs(d[1] - 1.0) < 1e-12
    assert abs(d[2] - 0.0) < 1e-12
    assert abs(d[3] - (-1.0)) < 1e-12  # above the open


def test_d_vector_invalid_to_nan():
    o = np.array([100.0, np.nan, 100.0, 100.0, 0.0])
    sg = np.array([0.01, 0.01, np.nan, 0.0, 0.01])
    c = np.array([50.0, 50.0, 50.0, 50.0, 50.0])
    d = S.d_vector(c, o, sg)
    assert np.isfinite(d[0]) and d[0] > 0
    assert not np.isfinite(d[1])  # NaN open
    assert not np.isfinite(d[2])  # NaN sigma
    assert not np.isfinite(d[3])  # sg <= 0
    assert not np.isfinite(d[4])  # O <= 0
    c2 = np.array([np.nan, 50.0, 50.0, 50.0, 50.0])
    d2 = S.d_vector(c2, np.full(5, 100.0), np.full(5, 0.01))
    assert not np.isfinite(d2[0])  # NaN close


def test_n_hard_exact_boundary():
    d = np.array([2.5, 2.499, 2.0, 1.5, 1.0, 0.99, np.nan, -1.0])
    assert S.n_hard_from_d(d, 2.5) == 1  # exact 2.5 counts
    assert S.n_hard_from_d(d, 2.0) == 3  # 2.5, 2.499? no: 2.499>=2.0 yes -> 2.5,2.499,2.0
    assert S.n_hard_from_d(d, 1.5) == 4
    assert S.n_hard_from_d(d, 1.0) == 5  # NaN never counts


def test_n_soft_ramp_hand_values():
    assert S.n_soft_from_d(np.array([1.0])) == 0.0
    assert abs(S.n_soft_from_d(np.array([1.75])) - 0.5) < 1e-12
    assert S.n_soft_from_d(np.array([2.5])) == 1.0
    assert S.n_soft_from_d(np.array([3.0])) == 1.0  # clipped
    assert S.n_soft_from_d(np.array([0.5])) == 0.0
    assert S.n_soft_from_d(np.array([-2.0])) == 0.0
    assert S.n_soft_from_d(np.array([np.nan])) == 0.0
    d = np.array([2.5, 1.0, 0.5, 3.0])
    assert abs(S.n_soft_from_d(d) - 2.0) < 1e-12


def test_n_soft_bounds_and_ordering():
    rng = np.random.default_rng(7)
    d = rng.normal(1.5, 1.5, size=(4, 50))
    d[:, ::7] = np.nan
    for j in range(d.shape[1]):
        col = d[:, j]
        ns = S.n_soft_from_d(col)
        assert 0.0 <= ns <= 4.0
        assert ns >= S.n_hard_from_d(col, 2.5)  # partial credit only adds
        assert ns <= S.n_hard_from_d(col, 1.0)  # each leg <= its 1.0 indicator
        assert S.n_hard_from_d(col, 1.5) >= S.n_hard_from_d(col, 2.0) >= S.n_hard_from_d(col, 2.5)


def test_size_mult_bounds():
    assert S.size_mult(0) == 1.0
    assert abs(S.size_mult(4) - 0.2) < 1e-12
    assert abs(S.size_mult(0.5) - 2 / 3) < 1e-12
    assert 0.2 <= S.size_mult(3.999) <= 1.0


def test_d_form_matches_price_form_including_nan():
    o = np.array([100.0, 100.0, 100.0, 100.0])
    sg = np.array([0.01, 0.01, 0.01, 0.01])
    cmat = np.array([[97.5, 97.51, np.nan],
                      [90.0, 99.0, 97.5],
                      [100.0, 100.0, 100.0],
                      [97.49, 97.5, 97.5]])
    for F in (2.5, 2.0, 1.5):
        expect = S.n_hard_vector(cmat, o, sg, F)
        got = np.array([S.n_hard_from_d(S.d_vector(cmat[:, j], o, sg), F)
                        for j in range(3)])
        assert (got == expect).all(), F


def test_fill_strict_trade_through():
    lv = 100.0
    assert S.find_fill(np.array([100.0, 100.0]), np.array([lv, lv])) is None
    assert S.find_fill(np.array([100.0, 99.99]), np.array([lv, lv])) == 1
    low = np.array([np.nan, 99.0])
    assert S.find_fill(low, np.array([lv, lv])) == 1  # NaN never fills


def test_exit_parity_with_b1deeper():
    sg, f, px, o2 = 0.01, 20, 98.0, 98.1
    cases = []
    O, H, L, C = _flat(o=px)  # timeout path
    cases.append((O, H, L, C, o2, False))
    O, H, L, C = _flat(o=px)
    H[30] = px * 1.01 + 0.01  # TP path
    cases.append((O, H, L, C, o2, False))
    O, H, L, C = _flat(o=px)
    L[25] = px * 0.92 - 0.01  # backstop path
    cases.append((O, H, L, C, o2, False))
    O, H, L, C = _flat(o=px)
    C[29] = px * 0.96 - 0.01  # close5 stop path ((29+1)%5==0)
    assert (29 + 1) % 5 == 0
    cases.append((O, H, L, C, o2, True))  # settling timeout funds too
    for (Oa, Ha, La, Ca, oo, st) in cases:
        r1, x1, h1 = S.outcome_from_fill(Ha, La, Ca, Oa, f, px, sg, oo, st)
        r2, x2, h2 = D.outcome_from_fill(Ha, La, Ca, Oa, f, px, sg, oo, st)
        assert (h1, x1) == (h2, x2)
        assert abs(r1 - r2) < 1e-12


def test_exit_stop_first_same_minute():
    sg, f, px = 0.01, 20, 98.0
    O, H, L, C = _flat(o=px)
    H[29] = px * (1 + sg) + 0.01
    C[29] = px * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    _, _, how = S.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "stop"


def test_causality_fill_uses_only_closed_minutes():
    # d at live minute m uses C at T+m-1 only: a flush close in column 1
    # moves n at minute index 1, not 0.
    o = np.full(4, 100.0)
    sg = np.full(4, 0.01)
    thr = 100.0 * (1 - 2.5 * 0.01)
    closes = np.full((4, 3), 100.0)
    closes[0, 1] = thr - 0.01
    n = S.n_hard_vector(closes, o, sg, 2.5)
    assert n.tolist() == [0, 1, 0]
    d0 = S.d_vector(closes[:, 0], o, sg)
    d1 = S.d_vector(closes[:, 1], o, sg)
    assert S.n_hard_from_d(d0, 2.5) == 0
    assert S.n_hard_from_d(d1, 2.5) == 1


def test_sigma_known_at_bar_open():
    opens = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    s = pd.Series(opens).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert np.isfinite(s[3]) and not np.isfinite(s[0])
    ref = pd.Series(opens[:4]).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12
