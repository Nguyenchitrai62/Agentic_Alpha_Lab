"""Tests for oc_cboostctrl: hand-checked synthetics + causality.

Cascade arithmetic verbatim from oc_cascadeboost; controls add frozen seeds and
mechanical per-year constants.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "research/tournament/oc_cboostctrl"))

from ctrl_rule import (  # noqa: E402
    BOOST,
    MIN_PERIODS,
    N_DAYS,
    N_SEEDS,
    NS_DAY,
    SEED_BASE,
    THRESH,
    WINDOW,
    anchor_of,
    boosted_mask,
    close_returns,
    random_starts_for,
    seed_of,
    trailing_sigma,
    triggers_of,
)

DAY = NS_DAY


def test_close_returns_hand_checked():
    c = np.array([100.0, 110.0, 99.0])
    r = close_returns(c)
    assert np.isnan(r[0])
    assert r[1] == np.log(1.1)
    assert r[2] == np.log(0.9)
    r2 = close_returns(np.array([100.0, 100.0, 0.0, -5.0]))
    assert r2[1] == 0.0
    assert np.isnan(r2[2]) and np.isnan(r2[3])


def test_trailing_sigma_excludes_tested_bar():
    base = 100 * 1.01 ** np.arange(600)
    r_base = close_returns(base)
    s_base = trailing_sigma(r_base)
    spiked = np.append(base, base[-1] * 1.50)
    s_spiked = trailing_sigma(close_returns(spiked))
    assert np.isnan(s_base[0])
    np.testing.assert_array_equal(np.isfinite(s_base), np.isfinite(s_spiked[:600]))
    fin = np.isfinite(s_base)
    np.testing.assert_allclose(s_base[fin], s_spiked[:600][fin], rtol=1e-9)
    assert int(np.where(np.isfinite(trailing_sigma(
        np.random.default_rng(1).normal(0.0, 0.02, size=700))))[0][0]) == MIN_PERIODS


def test_triggers_hand_checked_spike():
    rng = np.random.default_rng(0)
    r = rng.normal(0.0001, 0.01, size=600)
    r = np.append(r, [np.log(1.25)])
    c = 100 * np.exp(np.cumsum(r))
    fire = triggers_of(c)
    assert fire.sum() == 1 and bool(fire[-1])
    c2 = 100 * np.exp(np.cumsum(rng.normal(0.0001, 0.01, size=700)))
    assert triggers_of(c2).sum() == 0
    assert not fire[: MIN_PERIODS + 1].any()


def test_boosted_mask_boundaries_7d():
    t0 = 1000 * DAY
    trig = np.array([t0], dtype=np.int64)
    h = 3_600_000_000_000
    grid = np.array([t0 - h, t0, t0 + h, t0 + 7 * DAY - 1, t0 + 7 * DAY,
                     t0 + 7 * DAY + h], dtype=np.int64)
    got = boosted_mask(grid, trig, 7)
    assert list(got) == [False, False, True, True, True, False]
    assert boosted_mask(grid, np.array([], dtype=np.int64), 7).sum() == 0
    trig2 = np.array([t0, t0 + 6 * DAY], dtype=np.int64)
    g2 = np.array([t0 + 7 * DAY + h], dtype=np.int64)
    assert bool(boosted_mask(g2, trig2, 7)[0])
    assert BOOST == 1.5 and N_DAYS == 7 and THRESH == 4.0 and WINDOW == 540


def test_seeds_frozen_distinct():
    assert N_SEEDS == 20
    assert SEED_BASE == 6100000
    seen = set()
    for y in range(5):
        for s in range(4):
            for j in range(N_SEEDS):
                v = seed_of(y, s, j)
                assert v == SEED_BASE + j * 100 + y * 10 + s
                seen.add(v)
    assert len(seen) == 5 * 4 * N_SEEDS  # all distinct


def test_random_starts_hand_checked():
    rng = np.random.default_rng(seed_of(0, 0, 0))
    assert len(random_starts_for(100, 0, rng)) == 0
    assert len(random_starts_for(0, 5, rng)) == 0
    full = random_starts_for(10, 10, rng)
    np.testing.assert_array_equal(full, np.arange(10))
    over = random_starts_for(10, 99, rng)
    np.testing.assert_array_equal(over, np.arange(10))
    sel = random_starts_for(2190, 37, rng)
    assert len(sel) == 37 and len(set(sel.tolist())) == 37
    assert (sel[:-1] < sel[1:]).all()  # sorted
    assert sel.min() >= 0 and sel.max() < 2190
    # same seed -> same starts (deterministic)
    rng2 = np.random.default_rng(seed_of(0, 0, 0))
    np.testing.assert_array_equal(sel, random_starts_for(2190, 37, rng2))


def test_random_window_mask_matches_engine_rule():
    """boosted_mask on frozen starts == per-query searchsorted rule in run_engine."""
    t0 = 2000 * DAY
    h = 14_400_000_000_000  # 4h grid step
    grid = t0 + np.arange(0, 60) * h
    rng = np.random.default_rng(seed_of(2, 1, 7))
    pos = random_starts_for(len(grid), 3, rng)
    ts = np.sort(grid[pos])
    span = 7 * DAY
    expect = np.zeros(len(grid), dtype=bool)
    for i, t in enumerate(grid):
        before = ts[ts < t]
        expect[i] = bool(len(before) and (t - before[-1] <= span))
    np.testing.assert_array_equal(boosted_mask(grid, ts, 7), expect)


def test_anchor_of_boundaries():
    assert anchor_of("2021-09-24 00:00", 0) == 0
    assert anchor_of("2022-09-24 00:00", 0) == 1
    assert anchor_of("2026-09-23 19:00", 0) == 4
    assert anchor_of("2020-01-01 00:00", 0) == 0


def test_truncation_causality_real_bars():
    """Dropping later bars cannot change triggers at kept times (real data)."""
    bars = pd.read_parquet(
        ROOT / "research/tournament/oc_kronoshidden/bars_4h_4shift.parquet",
        columns=["T", "close", "sym", "shift"])
    sub = bars[(bars["sym"] == "BTCUSDT") & (bars["shift"] == 0)].sort_values("T")
    closes = sub["close"].to_numpy(dtype=float)
    fire_full = triggers_of(closes)
    cut = len(closes) - 500
    fire_tr = triggers_of(closes[:cut])
    assert (fire_tr == fire_full[:cut]).all()


def test_ctrl_inputs_invariants():
    p = ROOT / "research/tournament/oc_cboostctrl/tmp/ctrl_counts.json"
    q = ROOT / "research/tournament/oc_cboostctrl/tmp/ctrlR_starts.pkl"
    if not (p.exists() and q.exists()):
        pytest.skip("control inputs not built yet (build_ctrl.py)")
    import json
    import pickle
    counts = json.loads(p.read_text())
    assert counts["n_seeds"] == 20
    blob = pickle.load(open(q, "rb"))
    starts = blob["starts"]
    for y in range(5):
        for s in range(4):
            k = counts["k_per_shift_year"][str(s)][str(y)]
            assert k >= 0
            for j in range(20):
                v = starts[(y, s, j)]
                assert len(v) == k, (y, s, j, len(v), k)
                assert v == sorted(v) and len(set(v)) == len(v)
