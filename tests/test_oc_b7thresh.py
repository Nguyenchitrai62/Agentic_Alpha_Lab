"""Tests for oc_b7thresh: hand-checked synthetics + causality + grid invariants."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "research/tournament/oc_b7thresh"))

from thresh_rule import (  # noqa: E402
    BOOST,
    CELLS,
    MIN_PERIODS,
    THRESH_GRID,
    WINDOW,
    WINDOW_GRID,
    anchor_of,
    boosted_mask,
    cell_of,
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


def test_trailing_sigma_excludes_tested_bar():
    base = 100 * 1.01 ** np.arange(600)
    r_base = close_returns(base)
    s_base = trailing_sigma(r_base)
    spiked = np.append(base, base[-1] * 1.50)
    s_spiked = trailing_sigma(close_returns(spiked))
    np.testing.assert_array_equal(np.isfinite(s_base), np.isfinite(s_spiked[:600]))
    fin = np.isfinite(s_base)
    np.testing.assert_allclose(s_base[fin], s_spiked[:600][fin], rtol=1e-9)
    i = 600
    rng = np.random.default_rng(1)
    rn = rng.normal(0.0, 0.02, size=700)
    sn = trailing_sigma(rn)
    np.testing.assert_allclose(sn[i], np.std(rn[i - WINDOW:i], ddof=1), rtol=1e-12)


def test_triggers_k_monotonic_hand_checked():
    # noisy drift then a +18% jump: fires at k=3.5, borderline at 4.0/4.5 depending on sigma.
    # Core assertion: fire sets nest k35 superset k40 superset k45 on ANY series.
    rng = np.random.default_rng(0)
    r = rng.normal(0.0001, 0.01, size=600)
    r = np.append(r, [np.log(1.18)])
    c = 100 * np.exp(np.cumsum(r))
    f35 = triggers_of(c, thresh=3.5)
    f40 = triggers_of(c, thresh=4.0)
    f45 = triggers_of(c, thresh=4.5)
    assert ((f40 <= f35).all() and (f45 <= f40).all())
    assert bool(f35[-1])  # the spike fires at the loosest threshold
    assert BOOST == 1.5
    assert tuple(THRESH_GRID) == (3.5, 4.0, 4.5) and tuple(WINDOW_GRID) == (3, 5, 7, 10)
    assert cell_of(3.5, 3) == "k35_W03" and cell_of(4.0, 7) == "k40_W07"
    assert len(CELLS) == 12 and "k40_W07" in CELLS


def test_boosted_mask_W_boundaries():
    t0 = 1000 * DAY
    trig = np.array([t0], dtype=np.int64)
    h = 3_600_000_000_000
    grid = np.array([t0 - h, t0, t0 + h, t0 + 3 * DAY, t0 + 3 * DAY + h,
                     t0 + 10 * DAY, t0 + 10 * DAY + h], dtype=np.int64)
    got3 = boosted_mask(grid, trig, 3)
    assert list(got3) == [False, False, True, True, False, False, False]
    got10 = boosted_mask(grid, trig, 10)
    assert list(got10) == [False, False, True, True, True, True, False]
    # W-longer superset of W-shorter; strictly-after-tc convention
    assert ((got3 <= got10).all())
    assert boosted_mask(grid, np.array([], dtype=np.int64), 7).sum() == 0
    assert cooled_mask is boosted_mask


def test_anchor_of_boundaries():
    assert anchor_of("2021-09-24 00:00", 0) == 0
    assert anchor_of("2026-09-23 19:00", 0) == 4


def test_truncation_causality_real_bars():
    """Dropping later bars cannot change triggers at kept times (real data)."""
    bars = pd.read_parquet(
        ROOT / "research/tournament/oc_kronoshidden/bars_4h_4shift.parquet",
        columns=["T", "close", "sym", "shift"])
    sub = bars[(bars["sym"] == "BTCUSDT") & (bars["shift"] == 0)].sort_values("T")
    closes = sub["close"].to_numpy(dtype=float)
    for k in (3.5, 4.0, 4.5):
        fire_full = triggers_of(closes, thresh=k)
        cut = len(closes) - 500
        fire_tr = triggers_of(closes[:cut], thresh=k)
        assert (fire_tr == fire_full[:cut]).all()


def test_grid_parquet_invariants():
    """Built grids: mults in {1.0,1.5}, nesting k35>k40>k45 and W10>W07>W05>W03."""
    for name in ("boost_grid_main.parquet", "boost_grid_pre.parquet"):
        p = ROOT / f"research/tournament/oc_b7thresh/{name}"
        d = pd.read_parquet(p)
        for c in CELLS:
            assert set(d[f"mult_{c}"].unique()) <= {1.0, 1.5}, (name, c)
        for w in (3, 5, 7, 10):
            b35 = d[f"mult_{cell_of(3.5, w)}"] == 1.5
            b40 = d[f"mult_{cell_of(4.0, w)}"] == 1.5
            b45 = d[f"mult_{cell_of(4.5, w)}"] == 1.5
            assert ((b40 <= b35).all() and (b45 <= b40).all()), (name, w)
        for k in (3.5, 4.0, 4.5):
            m3 = d[f"mult_{cell_of(k, 3)}"] == 1.5
            m5 = d[f"mult_{cell_of(k, 5)}"] == 1.5
            m7 = d[f"mult_{cell_of(k, 7)}"] == 1.5
            m10 = d[f"mult_{cell_of(k, 10)}"] == 1.5
            assert ((m3 <= m5).all() and (m5 <= m7).all() and (m7 <= m10).all()), (name, k)
        assert set(d["shift"].unique()) == {0, 1, 2, 3}
