"""oc_adaptsig tests: dual-sigma B1 replica on synthetic paths."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_adaptsig"
sys.path.insert(0, str(OC))
import adapt as A

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def test_sigma_eff_is_max():
    assert A.sigma_eff(0.01, 0.02) == 0.02
    assert A.sigma_eff(0.03, 0.02) == 0.03
    assert A.sigma_eff(0.01, 0.01) == 0.01


def test_sigma_eff_fallback_and_nan():
    assert A.sigma_eff(0.01, float("nan")) == 0.01
    assert not np.isfinite(A.sigma_eff(float("nan"), 0.02))
    assert not np.isfinite(A.sigma_eff(float("nan"), float("nan")))


def test_n_counts_flushers_exact_boundary():
    cmat = np.array([[97.5, 97.51, np.nan],
                      [90.0, 99.0, 97.5],
                      [100.0, 100.0, 100.0],
                      [97.49, 97.5, 97.5]])
    oo = np.array([100.0, 100.0, 100.0, 100.0])
    ss = np.array([0.01, 0.01, 0.01, 0.01])
    n = A.n_vector(cmat, oo, ss)
    assert n.tolist() == [3, 1, 2]


def test_n_uses_arm_sigma():
    # same close 97.6: flush under sg=0.01 (thr 97.5? no: 97.6 > 97.5 -> not flush)
    # but flush under sg=0.02 (thr 95.0? 97.6 > 95 -> not flush either). Use 96.0:
    # sg 0.01 -> thr 97.5, 96 <= 97.5 flush; sg 0.005 -> thr 98.75 flush too.
    # Better: close 98.0: sg 0.01 thr 97.5 -> NOT flush; sg 0.02 thr 95.0 -> NOT flush.
    # Use close 97.0 with sg_small=0.005 (thr 98.75 -> flush) vs sg=0.02 (thr 95 -> NOT? 97>95 not flush).
    cmat = np.array([[97.0]])
    oo = np.array([100.0])
    n_wide = A.n_vector(cmat, oo, np.array([0.005]))   # thr 98.75 -> flush
    n_narrow = A.n_vector(cmat, oo, np.array([0.02]))  # thr 95.0 -> 97 > 95 no flush
    # wider sigma => higher threshold distance => FEWER flushes: adaptive desensitises
    assert n_wide.tolist() == [1]
    assert n_narrow.tolist() == [0]


def test_size_mult():
    assert A.size_mult(0) == 1.0
    assert abs(A.size_mult(4) - 0.2) < 1e-12


def test_fill_strict_trade_through():
    lv = 100.0
    assert A.find_fill(np.array([100.0, 100.0]), np.array([lv, lv])) is None
    assert A.find_fill(np.array([100.0, 99.99]), np.array([lv, lv])) == 1


def test_exit_tp_scales_with_arm_sigma():
    # flat at px, TP hit at px*(1+sg)+eps with sg=0.01; with sg=0.02 the same
    # absolute bump must NOT be a TP (TP twice as far).
    f, px = 20, 100.0
    O, H, L, C = _flat(o=px)
    H[30] = px * (1 + 0.01) + 0.001
    r_base, _, h_base = A.outcome_from_fill(H, L, C, O, f, px, 0.01, 100.0, False)
    r_ad, _, h_ad = A.outcome_from_fill(H, L, C, O, f, px, 0.02, 100.0, False)
    assert h_base == "tp"
    assert h_ad == "time"  # bump too small for the wider TP
    assert abs(r_base - (H[30] and (px * (1 + 0.01) / px - 1 - 2 * MK))) < 1e-12


def test_exit_stop_wider_with_adaptive_sigma():
    # close dip to px*(1-4*0.01)-eps stops the narrow arm but not the wide arm
    f, px = 20, 100.0
    O, H, L, C = _flat(o=px)
    C[29] = px * (1 - 4 * 0.01) - 0.01
    assert (29 + 1) % 5 == 0
    _, _, h_base = A.outcome_from_fill(H, L, C, O, f, px, 0.01, 100.0, False)
    _, _, h_ad = A.outcome_from_fill(H, L, C, O, f, px, 0.02, 100.0, False)
    assert h_base == "stop"
    assert h_ad == "time"


def test_exit_stop_first_same_minute():
    sg, f, px = 0.01, 20, 100.0
    O, H, L, C = _flat(o=px)
    H[29] = px * (1 + sg) + 0.01
    C[29] = px * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    _, _, how = A.outcome_from_fill(H, L, C, O, f, px, sg, 100.0, False)
    assert how == "stop"


def test_exit_timeout_funding():
    sg, f, px, o2 = 0.01, 20, 100.0, 100.1
    O, H, L, C = _flat(o=px)
    r0, _, h0 = A.outcome_from_fill(H, L, C, O, f, px, sg, o2, False)
    r1, _, h1 = A.outcome_from_fill(H, L, C, O, f, px, sg, o2, True)
    assert (h0, h1) == ("time", "time")
    assert abs((r0 - r1) - 0.0001) < 1e-12


def test_causality_fill_uses_only_closed_minutes():
    o, sg = 100.0, 0.01
    thr = o * (1 - 2.5 * sg)
    closes = np.full((4, 3), 100.0)
    closes[0, 1] = thr - 0.01
    n = A.n_vector(closes, np.full(4, o), np.full(4, sg))
    assert n.tolist() == [0, 1, 0]


def test_sigma_known_at_bar_open():
    opens = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    s = pd.Series(opens).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert np.isfinite(s[3]) and not np.isfinite(s[0])
    ref = pd.Series(opens[:4]).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12
