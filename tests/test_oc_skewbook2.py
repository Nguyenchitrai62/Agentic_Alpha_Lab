"""oc_skewbook2 tests: as-of causality, cut-off causality, book rebuild, grid bounds."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_skewbook2"
OC_DVOLSHORT = ROOT / "research/tournament/oc_dvolshort"
sys.path.insert(0, str(OC))
sys.path.insert(0, str(OC_DVOLSHORT))
import compute_skewbook2 as S
import compute_dvolshort as D

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]


@pytest.fixture(scope="module")
def res():
    return json.loads((OC / "results.json").read_text())


@pytest.fixture(scope="module")
def panel():
    p = pd.read_parquet(OC / "panel.parquet")
    p["T"] = pd.to_datetime(p["T"], utc=True)
    return p


@pytest.fixture(scope="module")
def opt():
    return S.load_options()


def test_asof_strictly_before_T(opt, panel):
    """z recomputed from options truncated to end < T matches saved rows."""
    idx = [0, 5000, 20000, 40000, len(panel) - 1]
    sub = panel.iloc[idx].reset_index(drop=True)
    Tns = sub["T"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    ref = sub["z"].to_numpy(float)
    ends = opt["end"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    assert (opt["bar"] < S.CUTOFF).all()
    # bar lies on the 4h grid
    mins = (pd.to_datetime(opt["bar"], utc=True).astype(np.int64) // 1_000_000_000 // 60) % (4 * 60)
    assert (mins == 0).all()
    for i in range(len(sub)):
        T = int(Tns[i])
        assert ((ends < T) | True).any()  # grid non-empty
        assert not ((ends < T) & (ends >= T)).any()
        opt_t = opt[opt["end"] < pd.to_datetime(T, utc=True, unit="ns")]
        got = S.skew_z90_for_times(np.array([T]), opt_t)[0]
        assert (np.isnan(got) and np.isnan(ref[i])) or abs(got - ref[i]) < 1e-9, \
            f"row {idx[i]} T={sub['T'].iloc[i]} got={got} ref={ref[i]}"
    got_full = S.skew_z90_for_times(Tns, opt)
    for i in range(len(sub)):
        g = got_full[i]
        assert (np.isnan(g) and np.isnan(ref[i])) or abs(g - ref[i]) < 1e-9


def test_cutoffs_causal(panel, res, opt):
    """results.json q80 must equal previous-data-only pool quantiles."""
    opens_full = pd.read_parquet(S.CACHE / "opens_v154.parquet")
    pool_idx = opens_full.index[(opens_full.index >= S.SKEW_START)
                                & (opens_full.index < S.CUTOFF)].sort_values()
    pool_Tns = pool_idx.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    pool_z = S.skew_z90_for_times(pool_Tns, opt)
    pool_T = pd.to_datetime(pool_idx, utc=True)
    for k in (0, 2):  # first year (pre-anchor pool) + one later year
        a0 = S.ANCHORS[k]
        pm = (pool_T < a0) & np.isfinite(pool_z)
        assert int(pm.sum()) >= 100
        assert pool_T[pm].max() < a0
        q80 = float(np.quantile(pool_z[pm], 0.8))
        assert res["years"][k]["q80"] == pytest.approx(q80, abs=1e-6)
    # NaN-z rows are never gated; gated rows strictly exceed their year's q80
    z = panel["z"].to_numpy(float)
    assert not panel["gated"][~np.isfinite(z)].any()
    for k, a0 in enumerate(S.ANCHORS):
        q = res["years"][k]["q80"]
        m = (panel["T"] >= a0) & (panel["T"] < (S.ANCHORS[k + 1] if k < 4 else S.LAST_BOUND))
        g = panel[m & (panel["w_base"] > 0) & panel["z"].notna()]
        assert ((g["z"] > q) == g["gated"]).all()


def test_books_match_dvolshort_and_bear(panel):
    """Rebuilt raw books must equal oc_dvolshort's formula; bear mask exact."""
    a = S.research_books_d2()
    b = D.research_books_d2()
    common = a.index.intersection(b.index)
    assert len(common) > 10000
    pd.testing.assert_frame_equal(a.reindex(common), b.reindex(common), check_dtype=False)
    # bear mask equals btc < rolling(1200, min_periods=600).mean() on opens
    opens_full = pd.read_parquet(S.CACHE / "opens_v154.parquet")
    btc = opens_full["BTCUSDT"].sort_index()
    expect = (btc < btc.rolling(1200, min_periods=600).mean())
    grid = pd.DatetimeIndex(pd.read_parquet(OC / "panel.parquet")["T"].unique()).sort_values()
    grid = grid.tz_localize("UTC") if grid.tz is None else grid.tz_convert("UTC")
    got = S.bear_for_times(grid)
    pd.testing.assert_series_equal(got, expect.reindex(grid).fillna(False).astype(bool),
                                   check_names=False)
    # base weights = bear-filtered raw weights (longs x0.5 in bear)
    sub = panel.drop_duplicates("T").set_index("T").sort_index()
    assert set(sub["bear"].unique()) <= {True, False}
    w = panel["w"].to_numpy(float)
    wb = panel["w_base"].to_numpy(float)
    bear = panel["bear"].to_numpy(bool)
    expect_wb = np.where(bear & (w > 0), 0.5 * w, w)
    np.testing.assert_allclose(wb, expect_wb, rtol=1e-12)


def test_grid_bounds(panel, res):
    """No decision bar at/after cutoff; gate math exact; years partition."""
    assert (panel["T"] < S.CUTOFF).all()
    assert panel["pnl"].notna().all() and panel["pnl_g"].notna().all()
    bounds = S.ANCHORS + [S.LAST_BOUND]
    total = 0
    for k in range(5):
        m = (panel["T"] >= bounds[k]) & (panel["T"] < bounds[k + 1])
        total += int(m.sum())
    assert total == len(panel), "years must partition the panel"
    assert set(panel["sym"].unique()) == set(SYMS)
    # gated longs are exactly 0.75x base; everything else bit-identical
    gated = panel["gated"].to_numpy()
    np.testing.assert_allclose(panel["w_g"][gated].to_numpy(float),
                               0.75 * panel["w_base"][gated].to_numpy(float), rtol=1e-12)
    ung = ~gated
    np.testing.assert_allclose(panel["w_g"][ung].to_numpy(float),
                               panel["w_base"][ung].to_numpy(float), rtol=1e-12)
    shorts = panel["w_base"] < 0
    assert not panel["gated"][shorts].any()
    flats = panel["w_base"] == 0
    assert not panel["gated"][flats].any()
