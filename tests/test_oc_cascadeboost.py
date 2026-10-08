"""Tests for oc_cascadeboost: hand-checked synthetics + causality.

Arithmetic verbatim from oc_cascadedelay; multiplier inverted (1.5).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "research/tournament/oc_cascadeboost"))

from boost_rule import (  # noqa: E402
    B3_DAYS,
    B7_DAYS,
    BOOST,
    MIN_PERIODS,
    THRESH,
    WINDOW,
    anchor_of,
    boosted_mask,
    close_returns,
    cooled_mask,
    trailing_sigma,
    triggers_of,
)

DAY = 86_400_000_000_000


def test_close_returns_hand_checked():
    c = np.array([100.0, 110.0, 99.0])
    r = close_returns(c)
    assert np.isnan(r[0])
    assert r[1] == np.log(1.1)
    assert r[2] == np.log(0.9)
    # flat series -> zero returns (finite), zeros/negatives -> NaN
    r2 = close_returns(np.array([100.0, 100.0, 0.0, -5.0]))
    assert r2[1] == 0.0
    assert np.isnan(r2[2]) and np.isnan(r2[3])


def test_trailing_sigma_excludes_tested_bar():
    # constant +1% returns: SIG is ~0 (tiny), and must be identical whether or
    # not a later spike is appended (tested bar never in its own window).
    base = 100 * 1.01 ** np.arange(600)
    r_base = close_returns(base)
    s_base = trailing_sigma(r_base)
    spiked = np.append(base, base[-1] * 1.50)
    s_spiked = trailing_sigma(close_returns(spiked))
    assert np.isnan(s_base[0])
    np.testing.assert_array_equal(np.isfinite(s_base), np.isfinite(s_spiked[:600]))
    fin = np.isfinite(s_base)
    np.testing.assert_allclose(s_base[fin], s_spiked[:600][fin], rtol=1e-9)
    # Non-degenerate (noisy) series: first finite SIG needs MIN_PERIODS priors;
    # r[0] is NaN so SIG[i] sees i-1 finite priors -> first at i = 121.
    rng = np.random.default_rng(1)
    rn = rng.normal(0.0, 0.02, size=700)
    sn = trailing_sigma(rn)
    # (raw draws here, no leading NaN; with close_returns the first is +1 later)
    assert int(np.where(np.isfinite(sn))[0][0]) == MIN_PERIODS
    # spot-check against a direct std on the exact frozen window
    i = 600
    np.testing.assert_allclose(sn[i], np.std(rn[i - WINDOW:i], ddof=1), rtol=1e-12)


def test_triggers_hand_checked_spike():
    # noisy drift (seeded) then a +25% jump: only the jump bar fires (4-sigma).
    rng = np.random.default_rng(0)
    r = rng.normal(0.0001, 0.01, size=600)
    r = np.append(r, [np.log(1.25)])
    c = 100 * np.exp(np.cumsum(r))
    fire = triggers_of(c)
    assert fire.sum() == 1 and bool(fire[-1])
    # quiet-only series never fires
    c2 = 100 * np.exp(np.cumsum(rng.normal(0.0001, 0.01, size=700)))
    assert triggers_of(c2).sum() == 0
    # NaN sigma region (early bars) never fires
    assert not fire[: MIN_PERIODS + 1].any()


def test_boosted_mask_boundaries():
    t0 = 1000 * DAY
    trig = np.array([t0], dtype=np.int64)
    h = 3_600_000_000_000  # 1h in ns
    grid = np.array([t0 - h, t0, t0 + h, t0 + 7 * DAY - 1, t0 + 7 * DAY,
                     t0 + 7 * DAY + h], dtype=np.int64)
    got = boosted_mask(grid, trig, 7)
    # strictly after tc, up to and including +7d
    assert list(got) == [False, False, True, True, True, False]
    got3 = boosted_mask(grid, trig, 3)
    assert list(got3) == [False, False, True, False, False, False]
    assert boosted_mask(grid, np.array([], dtype=np.int64), 7).sum() == 0
    # latest trigger before T binds (overlapping windows union)
    trig2 = np.array([t0, t0 + 6 * DAY], dtype=np.int64)
    g2 = np.array([t0 + 7 * DAY + h], dtype=np.int64)  # >7d after t0, <7d after t0+6d
    assert bool(boosted_mask(g2, trig2, 7)[0])
    # alias identical, frozen constants
    assert cooled_mask is boosted_mask
    assert BOOST == 1.5 and B7_DAYS == 7 and B3_DAYS == 3
    assert THRESH == 4.0 and WINDOW == 540


def test_anchor_of_boundaries():
    assert anchor_of("2021-09-24 00:00", 0) == 0
    assert anchor_of("2022-09-24 00:00", 0) == 1
    assert anchor_of("2026-09-23 19:00", 0) == 4
    assert anchor_of("2020-01-01 00:00", 0) == 0  # before first anchor -> 0


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
    # fire[i] uses closes only up to C[i] -> identical on the kept prefix
    assert (fire_tr == fire_full[:cut]).all()


def test_boost_parquet_invariants():
    """Built grid: mults in {1.0, 1.5}, B3 window subset of B7, shift grids sane."""
    p = ROOT / "research/tournament/oc_cascadeboost/boost_mult_4shift.parquet"
    d = pd.read_parquet(p)
    assert set(d["mult_B7"].unique()) <= {1.0, 1.5}
    assert set(d["mult_B3"].unique()) <= {1.0, 1.5}
    assert BOOST == 1.5 and THRESH == 4.0 and WINDOW == 540
    # B3 (3d) boosted implies B7 (7d) boosted everywhere
    assert ((d["mult_B3"] == 1.5) <= (d["mult_B7"] == 1.5)).all()
    assert set(d["shift"].unique()) == {0, 1, 2, 3}
    tmin = pd.to_datetime(d["T"], utc=True).min()
    assert tmin <= pd.Timestamp("2021-09-24", tz="UTC")
