"""oc_bookthresh tests: book rebuild, bear filter, threshold causality, grid bounds."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_bookthresh"
OC_REF = ROOT / "research/tournament/oc_dvolshort"
sys.path.insert(0, str(OC))
sys.path.insert(0, str(OC_REF))
import compute_bookthresh as T
import compute_dvolshort as S

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]


@pytest.fixture(scope="module")
def res():
    return json.loads((OC / "results.json").read_text())


@pytest.fixture(scope="module")
def panel():
    p = pd.read_parquet(OC / "panel.parquet")
    p["T"] = pd.to_datetime(p["T"], utc=True)
    return p


def test_books_match_dvolshort():
    """Rebuilt books must equal oc_dvolshort's formula cell by cell."""
    a = T.research_books_d2()
    b = S.research_books_d2()
    common = a.index.intersection(b.index)
    assert len(common) > 10000
    pd.testing.assert_frame_equal(a.reindex(common), b.reindex(common), check_dtype=False)


def test_bear_filter_exact(panel):
    """BASE = raw with bear longs x0.5; shorts/flats bit-identical; flags causal."""
    opens_full = pd.read_parquet(T.CACHE / "opens_v154.parquet")
    grid = pd.DatetimeIndex(sorted(panel["T"].unique()))
    grid = grid.tz_convert("UTC") if grid.tz is None else grid.tz_convert("UTC")
    btc = opens_full["BTCUSDT"].sort_index()
    ma = btc.rolling(1200, min_periods=600).mean()
    bear = (btc < ma).fillna(False).reindex(grid).fillna(False)
    pm = panel.sort_values(["T", "sym"]).reset_index(drop=True)
    assert (bear.reindex(pd.to_datetime(pm["T"], utc=True)).to_numpy(bool)
            == pm["bear"].to_numpy(bool)).all()
    w_raw = pm["w_raw"].to_numpy(float)
    w_base = pm["w_base"].to_numpy(float)
    bear_arr = pm["bear"].to_numpy(bool)
    expect = np.where(bear_arr & (w_raw > 0), w_raw * 0.5, w_raw)
    np.testing.assert_allclose(w_base, expect, rtol=1e-12)
    # shorts (w_raw < 0) and flats never halved by the bear filter
    short = w_raw < 0
    np.testing.assert_allclose(w_base[short], w_raw[short], rtol=1e-12)


def test_thresholds_causal(panel, res):
    """Saved q25 must equal previous-data-only 25th pct of |w_base| per coin."""
    for k, a0 in enumerate(T.ANCHORS):
        a0 = pd.to_datetime(a0, utc=True)
        for j, s in enumerate(SYMS):
            sub = panel[(panel["sym"] == s) & (panel["T"] < a0)]
            got = res["years"][k]["q25"][s]
            if k == 0:
                assert got is None
                assert int(sub.shape[0]) == 0
            else:
                assert int(sub.shape[0]) >= 100
                assert (sub["T"].max() < a0)
                q = float(np.quantile(sub["w_base"].abs().to_numpy(float), 0.25))
                assert got == pytest.approx(q, abs=1e-6)
    # Zeroing is exactly |w_base| < q25 on years 1..4, nowhere in year 0.
    bounds = T.ANCHORS + [T.LAST_BOUND]
    for k in range(5):
        m = (panel["T"] >= bounds[k]) & (panel["T"] < bounds[k + 1])
        sub = panel[m]
        if k == 0:
            assert not sub["zeroed"].any()
        else:
            for s in SYMS:
                q = res["years"][k]["q25"][s]
                g = sub[sub["sym"] == s]
                expect = g["w_base"].abs().to_numpy(float) < q
                assert (expect == g["zeroed"].to_numpy(bool)).all()
    # Non-zeroed rows bit-identical; zeroed rows are exactly 0 with nonzero base.
    ung = ~panel["zeroed"].to_numpy(bool)
    np.testing.assert_allclose(panel["w_rule"][ung].to_numpy(float),
                               panel["w_base"][ung].to_numpy(float), rtol=1e-12)
    zed = panel["zeroed"].to_numpy(bool)
    assert (panel["w_rule"][zed].to_numpy(float) == 0.0).all()
    # Zeroed includes already-zero rows (|0| < q when q > 0); they stay unchanged.
    # Newly-zeroed share must match results.json per year.
    bounds = T.ANCHORS + [T.LAST_BOUND]
    for k in range(5):
        m = ((panel["T"] >= bounds[k]) & (panel["T"] < bounds[k + 1])).to_numpy(bool)
        new = (panel["zeroed"].to_numpy(bool)[m]
               & (panel["w_base"].to_numpy(float)[m] != 0.0)).mean()
        assert new == pytest.approx(res["years"][k]["share_rows_zeroed_new"], abs=1e-6)


def test_grid_bounds(panel, res):
    """No decision bar at/after cutoff; years partition; costs use own-path prev."""
    assert (panel["T"] < T.CUTOFF).all()
    assert panel["pnl_base"].notna().all() and panel["pnl_rule"].notna().all()
    bounds = T.ANCHORS + [T.LAST_BOUND]
    total = 0
    for k in range(5):
        m = (panel["T"] >= bounds[k]) & (panel["T"] < bounds[k + 1])
        total += int(m.sum())
    assert total == len(panel), "years must partition the panel"
    assert set(panel["sym"].unique()) == set(SYMS)
    # Costs: maker * |w - own prev| per sym in T order, first prev = 0.
    for col_w, col_c in (("w_base", "cost_base"), ("w_rule", "cost_rule")):
        for s in SYMS:
            g = panel[panel["sym"] == s].sort_values("T")
            w = g[col_w].to_numpy(float)
            prev = np.concatenate([[0.0], w[:-1]])
            np.testing.assert_allclose(g[col_c].to_numpy(float),
                                       T.MAKER * np.abs(w - prev), rtol=1e-12)
    # Year-0 tie by construction (rule inactive).
    y0 = res["years"][0]
    assert y0["book_pnl_base"] == pytest.approx(y0["book_pnl_rule"], abs=1e-12)
    assert y0["maxDD_base"] == pytest.approx(y0["maxDD_rule"], abs=1e-12)
