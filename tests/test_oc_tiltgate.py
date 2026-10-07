"""oc_tiltgate tests: gate-math hand checks + window causality/truncation.

Run: .venv/Scripts/python.exe -m pytest tests/test_oc_tiltgate.py -q
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "research/tournament/oc_tiltgate"))
sys.path.insert(0, str(ROOT / "research/tournament/oc_voltilt"))

from gate_rule import ANCH5, anchor_of, assign_mult, decide, gate_effect, gate_window  # noqa: E402
import tilt_rule as vt_rule  # noqa: E402  (frozen reference)


def test_assign_mult_handchecked():
    assert assign_mult(3.0, 1, 1.0, 2.0, 1.25, 0.75) == 1.25
    assert assign_mult(2.0, 1, 1.0, 2.0, 1.25, 0.75) == 1.25  # boundary incl.
    assert assign_mult(0.5, 1, 1.0, 2.0, 1.25, 0.75) == 0.75
    assert assign_mult(1.0, 1, 1.0, 2.0, 1.25, 0.75) == 0.75  # boundary incl.
    assert assign_mult(1.5, 1, 1.0, 2.0, 1.25, 0.75) == 1.0
    assert assign_mult(3.0, -1, 1.0, 2.0, 1.25, 0.75) == 0.75
    assert assign_mult(0.5, -1, 1.0, 2.0, 1.25, 0.75) == 1.25
    assert assign_mult(float("nan"), 1, 1.0, 2.0, 1.25, 0.75) == 1.0
    assert assign_mult(float("inf"), -1, 1.0, 2.0, 1.25, 0.75) == 1.0


def test_assign_mult_matches_frozen_voltilt_rule():
    rng = np.random.default_rng(20261008)
    risks = np.r_[np.array([np.nan, np.inf, -np.inf]), rng.normal(1.2, 0.6, 200)]
    for r in risks:
        for d in (1, -1):
            assert assign_mult(r, d, 0.8, 1.9, 1.25, 0.75) == \
                vt_rule.assign_mult(r, d, 0.8, 1.9, 1.25, 0.75)


def test_gate_window_exact_12m_minus_embargo():
    lo, hi = gate_window("2022-09-24")
    assert lo == pd.Timestamp("2021-09-17", tz="UTC")
    assert hi == pd.Timestamp("2022-09-17", tz="UTC")
    assert (hi - lo).days == 365
    for a in ANCH5:
        lo_a, hi_a = gate_window(a)
        assert (hi_a - lo_a).days == 365
        assert hi_a == pd.Timestamp(a, tz="UTC") - pd.Timedelta(days=7)


def test_gate_effect_handchecked():
    # (1.25-1)*1*0.01 + (0.75-1)*1*(-0.02) + 0 = 0.0025+0.005 = 0.0075 /3
    g = gate_effect([1.25, 0.75, 1.0], [1.0, 1.0, 1.0], [0.01, -0.02, 0.005])
    assert g["n"] == 3 and g["n_sized"] == 2
    assert abs(g["effect"] - 0.0075 / 3) < 1e-15
    assert decide(g["effect"]) is True
    # NaN mult -> 1 (contributes 0, counts in n)
    g2 = gate_effect([np.nan, 1.0], [2.0, 2.0], [0.05, -0.01])
    assert g2["n"] == 2 and g2["n_sized"] == 0
    assert g2["effect"] == 0.0
    assert decide(g2["effect"]) is False  # strict > 0
    # negative effect -> OFF
    g3 = gate_effect([1.25], [1.0], [-0.04])
    assert g3["effect"] < 0 and decide(g3["effect"]) is False
    # empty window -> NaN -> OFF
    g4 = gate_effect([], [], [])
    assert g4["n"] == 0 and not np.isfinite(g4["effect"])
    assert decide(g4["effect"]) is False
    assert decide(float("nan")) is False


def test_gate_window_causality_and_fit_window():
    # Window end is exactly A - 7d (embargo); prior-year fit cutoff is at or
    # before the window start, so no outcome from year [A, A+365d) (and not
    # even from the embargo week) can enter the gate for year A.
    for y, a in enumerate(ANCH5):
        A = pd.Timestamp(a, tz="UTC")
        lo, hi = gate_window(a)
        assert hi == A - pd.Timedelta(days=7)
        assert lo < hi
        if y > 0:
            fit_cutoff = pd.Timestamp(ANCH5[y - 1], tz="UTC") - pd.Timedelta(days=7)
            assert fit_cutoff <= lo, (a, fit_cutoff, lo)
    # selection semantics: [lo, hi) half-open on fill bar-open times
    lo, hi = gate_window("2024-09-24")
    ts = pd.DatetimeIndex([lo - pd.Timedelta(minutes=1), lo,
                           hi - pd.Timedelta(minutes=1), hi])
    sel = (ts >= lo) & (ts < hi)
    assert list(sel) == [False, True, True, False]


def test_gate_effect_truncation_stable():
    # Recomputing the effect from fills truncated at a cut matches the
    # full-array effect restricted to the kept prefix (pure pooling, no
    # look-ahead across fills).
    rng = np.random.default_rng(11)
    n = 500
    mult = rng.choice([0.75, 1.0, 1.25], size=n).astype(float)
    w = rng.uniform(0.01, 0.05, size=n)
    y10 = rng.normal(0.0, 0.02, size=n)
    full = gate_effect(mult, w, y10)
    cut = 321
    trunc = gate_effect(mult[:cut], w[:cut], y10[:cut])
    expect = float(np.sum((mult[:cut] - 1.0) * w[:cut] * y10[:cut])) / cut
    assert abs(trunc["effect"] - expect) < 1e-15
    # and the full effect is the n-weighted mean of prefix/suffix effects
    suffix = gate_effect(mult[cut:], w[cut:], y10[cut:])
    mix = (trunc["effect"] * cut + suffix["effect"] * (n - cut)) / n
    assert abs(mix - full["effect"]) < 1e-12


def test_anchor_of_matches_voltilt_convention():
    assert anchor_of("2021-09-24 00:00", 0) == vt_rule.anchor_of("2021-09-24 00:00", 0) == 0
    assert anchor_of("2024-09-25 00:00", 2) == vt_rule.anchor_of("2024-09-25 00:00", 2) == 3
    assert anchor_of("2026-09-23 00:00", 0) == 4
    assert len(ANCH5) == 5
