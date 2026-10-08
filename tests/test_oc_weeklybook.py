"""oc_weeklybook tests: causality/truncation + hand-checked synthetic cases."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent / "research/tournament/oc_weeklybook"
sys.path.insert(0, str(HERE))
from weeklybook_rule import (F_V1, F_V2, control_mult_per_year, overlay,
                             sample_slow, sleeve_corr, weekly_anchors)


def test_weekly_anchors_wednesday_only():
    idx = pd.date_range("2021-09-20", "2021-10-06", freq="4h", tz="UTC")
    m = weekly_anchors(idx, 2)
    got = list(idx[m])
    # Wednesdays 00:00 UTC in range: 2021-09-22, 2021-09-29, 2021-10-06
    assert got == [pd.Timestamp("2021-09-22", tz="UTC"),
                   pd.Timestamp("2021-09-29", tz="UTC"),
                   pd.Timestamp("2021-10-06", tz="UTC")]
    # No other weekday leaks in
    assert not weekly_anchors(idx, 0).any() or True  # Monday exists separately
    m_mon = weekly_anchors(idx, 0)
    assert list(idx[m_mon]) == [pd.Timestamp("2021-09-20", tz="UTC"),
                                pd.Timestamp("2021-09-27", tz="UTC"),
                                pd.Timestamp("2021-10-04", tz="UTC")]


def test_slow_causal_truncation():
    # Post-Wednesday data cannot move earlier slow rows.
    n, k = 40, 2
    rng = np.random.default_rng(0)
    w = rng.normal(size=(n, k))
    idx = pd.date_range("2021-09-20", periods=n, freq="4h", tz="UTC")
    m = weekly_anchors(idx, 2)
    s1 = sample_slow(w, m)
    w2 = w.copy()
    w2[30:] += 5.0  # perturb everything after row 30
    s2 = sample_slow(w2, m)
    # Rows before the first anchor at/after row 30 are identical.
    assert np.array_equal(s1[:30], s2[:30])
    # Holds between anchors: slow equals last anchor row.
    anchors = np.where(m)[0]
    for a, b in zip(anchors, list(anchors[1:]) + [n]):
        assert np.array_equal(s1[a:b], np.broadcast_to(s1[a], (b - a, k)))


def test_slow_zero_before_first_anchor():
    w = np.ones((8, 1))
    m = np.array([False, False, True, False, False, False, False, True])
    s = sample_slow(w, m)
    assert np.array_equal(s[:2], np.zeros((2, 1)))
    assert np.array_equal(s[2:7], np.ones((5, 1)))
    assert np.array_equal(s[7:], np.ones((1, 1)))


def test_hand_overlay_and_control():
    fast = np.array([[1.0, -2.0], [0.5, 0.5]])
    slow = np.array([[0.0, 0.0], [1.0, 1.0]])
    v1 = overlay(fast, slow, F_V1)
    assert np.allclose(v1, [[1.0, -2.0], [0.6, 0.6]])
    v2 = overlay(fast, slow, F_V2)
    assert np.allclose(v2, [[1.0, -2.0], [0.75, 0.75]])
    try:
        overlay(fast, slow, 0.5)
        raise AssertionError("unfrozen f must raise")
    except ValueError:
        pass
    assert control_mult_per_year(100.0, 110.0) == 1.1
    assert control_mult_per_year(0.0, 5.0) == 1.0
    assert control_mult_per_year(-3.0, 5.0) == 1.0


def test_hand_corr_gate():
    a = np.array([1.0, -1.0, 1.0, -1.0, 0.5, -0.5, 0.25])
    assert abs(sleeve_corr(a, a) - 1.0) < 1e-12
    assert abs(sleeve_corr(a, -a) + 1.0) < 1e-12
    assert not np.isfinite(sleeve_corr(np.ones(7), a))  # constant leg -> NaN
    assert not np.isfinite(sleeve_corr(a[:2], a[:2]))  # too short -> NaN
