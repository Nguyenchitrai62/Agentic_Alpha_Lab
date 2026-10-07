"""oc_tpfill tests: BASE/FIX logic on synthetic 1m paths + causality."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_tpfill"
sys.path.insert(0, str(OC))
import tpfill as T

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    Lw = np.full(n, o)
    C = np.full(n, o)
    return O, H, Lw, C


def test_same_minute_tp_needs_close_not_just_high():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + sg)
    H[f] = tp + 0.50  # wick through TP ...
    C[f] = tp - 0.01  # ... but closes below -> NO same-minute TP
    rb, xb, hb = T.outcome_base(H, Lw, C, O, f, lv, sg, 99.0, False)
    rf, xf, hf = T.outcome_fix(H, Lw, C, O, f, lv, sg, 99.0, False)
    assert hf != "tp_same"
    assert (rf, xf, hf) == (rb, xb, hb)


def test_same_minute_tp_on_close_at_or_above():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + sg)
    C[f] = tp  # exactly at the level counts (>=)
    H[f] = tp + 0.10
    rf, xf, hf = T.outcome_fix(H, Lw, C, O, f, lv, sg, 99.0, False)
    assert hf == "tp_same" and xf == f
    assert abs(rf - (tp / lv - 1 - 2 * MK)) < 1e-12


def test_same_minute_tp_price_and_fee():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.02, 33
    tp = lv * (1 + sg)
    C[f] = tp + 0.25
    rf, xf, hf = T.outcome_fix(H, Lw, C, O, f, lv, sg, 101.0, True)
    # intrabar: no funding even on a settling bar
    assert hf == "tp_same"
    assert abs(rf - (tp / lv - 1 - 2 * MK)) < 1e-12


def test_no_same_minute_tp_path_equals_base_exactly():
    rng = np.random.default_rng(7)
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    H[25] = lv * (1 + sg) + 0.05
    C[29] = lv * (1 - 4 * sg) - 0.01  # clock minute stop
    assert (29 + 1) % 5 == 0
    O[30] = 99.5
    C[f] = lv  # below TP -> no same-minute trigger
    rb, xb, hb = T.outcome_base(H, Lw, C, O, f, lv, sg, 101.0, False)
    rf, xf, hf = T.outcome_fix(H, Lw, C, O, f, lv, sg, 101.0, False)
    assert (rb, xb, hb) == (rf, xf, hf)
    assert rng is not None  # silence lint about rng naming


def test_stop_first_same_minute_kept_after_fix():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + sg)
    H[29] = tp + 0.01  # TP touch same minute as a clock close below sl
    C[29] = lv * (1 - 4 * sg) - 0.01
    C[f] = lv  # no same-minute TP
    assert (29 + 1) % 5 == 0
    rf, xf, hf = T.outcome_fix(H, Lw, C, O, f, lv, sg, 99.0, False)
    assert hf == "stop"  # stop-first preserved
    assert abs(rf - (O[xf] / lv - 1 - MK - TK)) < 1e-12


def test_backstop_beats_tp_same_minute():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + sg)
    H[25] = tp + 0.01
    Lw[25] = lv * (1 - 8 * sg) - 0.01
    C[f] = lv
    rf, xf, hf = T.outcome_fix(H, Lw, C, O, f, lv, sg, 99.0, False)
    assert hf == "backstop" and xf == 25


def test_timeout_funding():
    O, H, Lw, C = _flat()
    lv, sg, f, o2 = 100.0, 0.01, 20, 101.0
    C[f] = lv
    r0, x0, h0 = T.outcome_fix(H, Lw, C, O, f, lv, sg, o2, False)
    r1, x1, h1 = T.outcome_fix(H, Lw, C, O, f, lv, sg, o2, True)
    assert (h0, h1) == ("time", "time") and (x0, x1) == (240, 240)
    assert abs((r0 - r1) - 0.0001) < 1e-12


def test_fill_strict_trade_through():
    lv = 100.0
    assert not (100.0 < lv)  # touch == level is NOT a fill
    assert 99.99 < lv
    assert T.find_fill(np.array([100.0, 100.0, 99.9]), 100.0) == 2
    assert T.find_fill(np.array([100.0, 100.0]), 100.0) is None


def test_sigma_known_at_bar_open():
    opens = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    s = pd.Series(opens).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert np.isfinite(s[3]) and not np.isfinite(s[0])
    # sigma at bar 3 excludes the bar-4 spike to 500
    ref = pd.Series(opens[:4]).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12


def test_n_vector_causal_and_b1_size():
    # two other coins: one flushing (close <= O*(1-2.5sg)), one not
    cmat = np.array([[95.0, 99.9, 95.0],
                     [99.9, 99.9, 99.9]])
    oo = np.array([100.0, 100.0])
    ss = np.array([0.01, 0.01])  # thr = 97.5
    n = T.n_vector(cmat, oo, ss)
    assert list(n) == [1, 0, 1]
    assert abs(T.size_mult(0) - 1.0) < 1e-12
    assert abs(T.size_mult(3) - 0.25) < 1e-12
