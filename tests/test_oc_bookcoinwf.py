"""Tests for oc_bookcoinwf (causality + gate mechanics; no outcome tuning)."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "tournament" / "oc_bookcoinwf"))
from compute_bookcoinwf import (ANCHORS, COST, CUTOFF, EMBARGO, HIST_START, LAST_BOUND, SYMS,  # noqa: E402
                                research_books_d2)

HERE = ROOT / "research" / "tournament" / "oc_bookcoinwf"
RES = json.loads((HERE / "results.json").read_text())
PANEL = pd.read_parquet(HERE / "panel.parquet")
BOUNDS = ANCHORS + [LAST_BOUND]


def test_history_embargo():
    panel = PANEL.copy()
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    for k, a0 in enumerate(ANCHORS):
        hm = (panel["T"] < a0 - EMBARGO) & (panel["T"] >= HIST_START)
        assert (panel.loc[hm, "T"] < a0 - EMBARGO).all()
        # recompute history sums from the saved panel; must match results.json
        for s in SYMS:
            expect = float(panel.loc[hm & (panel["sym"] == s), "pnl"].sum()) if int(hm.sum()) else 0.0
            assert abs(expect - RES["years"][k]["hist_sums"][s]) < 2e-6  # results.json rounds to 6dp
        # no test-year row is in the history pool
        ym = (panel["T"] >= BOUNDS[k]) & (panel["T"] < BOUNDS[k + 1])
        assert int((hm & ym).sum()) == 0
    # year 1 has empty history and falls back to the full book
    assert RES["years"][0]["fallback"] is True
    assert RES["years"][0]["gated_coins"] == SYMS
    for k in range(1, 5):
        assert RES["years"][k]["fallback"] is False


def test_gate_applied():
    panel = PANEL.copy()
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    for k, a0 in enumerate(ANCHORS):
        gset = set(RES["years"][k]["gated_coins"])
        ym = ((panel["T"] >= BOUNDS[k]) & (panel["T"] < BOUNDS[k + 1])).to_numpy()
        sub = panel.loc[ym]
        for s in SYMS:
            m = (sub["sym"] == s).to_numpy()
            if s in gset:
                assert np.allclose(sub.loc[m, "w_g"].to_numpy(float),
                                   sub.loc[m, "w"].to_numpy(float), atol=0)
            else:
                assert (sub.loc[m, "w_g"].to_numpy(float) == 0.0).all()
    # costs are the assigned 0.0005/unit turnover, non-negative
    assert (panel["cost"].to_numpy(float) >= 0).all()
    assert (panel["cost_g"].to_numpy(float) >= 0).all()
    assert COST == 0.0005


def test_books_match_dvolshort():
    sys.path.insert(0, str(ROOT / "research" / "tournament" / "oc_dvolshort"))
    import compute_dvolshort as dv
    ours = research_books_d2().sort_index()
    theirs = dv.research_books_d2().sort_index()
    common = ours.index.intersection(theirs.index)
    assert len(common) > 1000
    assert np.allclose(ours.reindex(common).to_numpy(float),
                       theirs.reindex(common).to_numpy(float), atol=0)


def test_grid_bounds():
    panel = PANEL.copy()
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    assert (panel["T"] < CUTOFF).all()
    assert panel["T"].min() >= ANCHORS[0]
    # years partition the panel without gaps/overlaps
    total = 0
    for k in range(5):
        m = ((panel["T"] >= BOUNDS[k]) & (panel["T"] < BOUNDS[k + 1])).sum()
        assert int(m) == RES["years"][k]["n_rows"]
        total += int(m)
    assert total == len(panel)
    # per-year totals reconcile with per-coin tables and the decision counts
    for k in range(5):
        r = RES["years"][k]
        assert abs(sum(r["per_coin_pnl"].values()) - r["total_pnl"]) < 3e-6  # 6dp rounding x5
        assert abs(sum(r["per_coin_pnl_gated"].values()) - r["total_pnl_gated"]) < 5e-6
        assert r["pnl_not_lower"] == bool(r["total_pnl_gated"] >= r["total_pnl"])
        assert r["dd_not_worse"] == bool(r["maxDD_gated"] <= r["maxDD"])
    assert RES["decision"]["pnl_not_lower_count"] == f"{sum(1 for r in RES['years'] if r['pnl_not_lower'])}/5"
    assert RES["decision"]["dd_not_worse_count"] == f"{sum(1 for r in RES['years'] if r['dd_not_worse'])}/5"
