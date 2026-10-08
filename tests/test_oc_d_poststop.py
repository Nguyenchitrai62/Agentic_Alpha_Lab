"""Tests for oc_d_poststop pure helpers (no data access beyond truncation test).

Covers: hand-checked synthetic stop/kind/x/window arithmetic + causality/truncation
(recompute from truncated bars/1m -> identical triggers on the kept prefix).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
TDIR = HERE.parent / "research" / "tournament" / "oc_d_poststop"
sys.path.insert(0, str(TDIR))

from poststop_rule import (BOOST, FLAT, boosted_mult, compute_sigma, find_fill,
                           outcome_kind_x, phase_mean_sums)


def test_find_fill_strict():
    low = np.array([10.0, 9.0, 8.0])
    assert find_fill(low, 8.0) is None  # strict: equal never fills
    assert find_fill(low, 8.5) == 2
    assert find_fill(low, 11.0) == 0


def test_outcome_stop_x_handchecked():
    # Flat market at 100; rung level 97, sg small so sl/bl/tp far apart.
    # Force a close5 stop: craft closes dipping below sl exactly on a %5==0 minute.
    lv, sg = 100.0, 0.01
    sl = lv * (1 - 4 * sg)  # 96.0
    bl = lv * (1 - 8 * sg)  # 92.0
    tp = lv * (1 + 1.0 * sg)  # 101.0
    n = 240
    Oa = np.full(n, 100.0)
    Ha = np.full(n, 100.0)
    La = np.full(n, 100.0)
    Ca = np.full(n, 100.0)
    f = 16
    # stop trigger minute: post = f+1 .. 239; need (post+1) % 5 == 0 -> post = 19, 24, ...
    # pick post = 19 (minute index 19 in bar): Ca[19] <= sl.
    Ca[19] = sl - 0.5
    # keep lows above backstop everywhere, highs below tp everywhere
    kind, x = outcome_kind_x(Ha, La, Ca, Oa, f, lv, sg)
    assert kind == "stop"
    # ks = argmax over trig array (Ca[f+1:240] = Ca[17:240]); trig fires at global minute 19
    # -> position 19-17=2 in the slice; km = f+1+ks = 17+2 = 19; x = 20
    assert x == 20


def test_outcome_backstop_beats_stop_and_tp():
    lv, sg = 100.0, 0.01
    n = 240
    Oa = np.full(n, 100.0)
    Ha = np.full(n, 100.0)
    La = np.full(n, 100.0)
    Ca = np.full(n, 100.0)
    f = 16
    La[17] = 50.0  # backstop touch at minute 17 (earliest touch wins)
    Ha[18] = 500.0  # tp touch later at minute 18
    Ca[19] = 50.0  # stop trigger even later
    kind, x = outcome_kind_x(Ha, La, Ca, Oa, f, lv, sg)
    # verbatim ordering: backstop branch first (kb<=ks and kb<=kt wins ties and
    # earlier touches); here kb=0 beats kt=1, ks=2.
    assert kind == "backstop"
    assert x == 17


def test_outcome_timeout_when_nothing_touched():
    lv, sg = 100.0, 0.01
    n = 240
    Oa = np.full(n, 100.0)
    Ha = np.full(n, 100.0)
    La = np.full(n, 100.0)
    Ca = np.full(n, 100.0)
    kind, x = outcome_kind_x(Ha, La, Ca, Oa, 16, lv, sg)
    assert (kind, x) == ("time", 240)


def test_boosted_mult_window_handchecked():
    day = 86_400_000_000_000
    tc = 1_000 * day
    grid = np.array([tc - 1, tc, tc + 1, tc + 3 * day, tc + 7 * day,
                     tc + 7 * day + 1], dtype=np.int64)
    # V2 N=3: strictly after tc, up to and including +3d
    m = boosted_mult(grid, np.array([tc], dtype=np.int64), 3)
    assert list(m) == [FLAT, FLAT, BOOST, BOOST, FLAT, FLAT]
    # V1 N=7
    m7 = boosted_mult(grid, np.array([tc], dtype=np.int64), 7)
    assert list(m7) == [FLAT, FLAT, BOOST, BOOST, BOOST, FLAT]
    # empty triggers -> all flat
    m0 = boosted_mult(grid, np.array([], dtype=np.int64), 7)
    assert (m0 == FLAT).all()


def test_boosted_mult_uses_latest_stop_only():
    day = 86_400_000_000_000
    t1, t2 = 100 * day, 200 * day
    grid = np.array([t2 + 7 * day, t2 + 7 * day + 1], dtype=np.int64)
    m = boosted_mult(grid, np.array([t1, t2], dtype=np.int64), 7)
    assert list(m) == [BOOST, FLAT]  # latest tc strictly before T decides


def test_phase_mean_sums_handchecked():
    ph = np.array([0, 1, 2, 3, 0])
    yr = np.array([0, 0, 0, 0, 1])
    w = np.array([1.0, 2.0, 1.0, 1.0, 5.0])
    y = np.array([1.0, 1.0, 1.0, 1.0, 2.0])
    out = phase_mean_sums(ph, yr, w, y, 2)
    assert out[0] == (1.0 + 2.0 + 1.0 + 1.0) / 4
    assert out[1] == (10.0 + 0 + 0 + 0) / 4


def test_truncation_causality_compute_sigma():
    # compute_sigma at position j uses opens <= j-1 only (shift-1): truncating the
    # tail cannot change the kept prefix.
    rng = np.random.default_rng(0)
    opens = 100 + np.cumsum(rng.normal(0, 1, 500))
    full = compute_sigma(opens)
    cut = compute_sigma(opens[:400])
    assert np.allclose(full[:400], cut, equal_nan=True)


def test_truncation_causality_boosted_mult():
    # Dropping later stop triggers cannot change mults on the kept prefix grid.
    day = 86_400_000_000_000
    base = 500 * day
    trig_full = np.array([base - 50 * day, base + 10 * day], dtype=np.int64)
    trig_kept = np.array([base - 50 * day], dtype=np.int64)
    grid = np.array([base - 60 * day + i * day for i in range(55)], dtype=np.int64)
    m_full = boosted_mult(grid, trig_full, 7)
    m_kept = boosted_mult(grid, trig_kept, 7)
    # grid points before the dropped trigger's influence zone are identical;
    # specifically all T <= dropped_tc behave identically.
    assert (m_full == m_kept).all()  # dropped tc is after all grid points here
