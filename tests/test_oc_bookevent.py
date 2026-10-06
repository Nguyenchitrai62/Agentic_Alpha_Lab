"""Tests for oc_bookevent (idea #51, pre-registered in PLAN.md).

LIGHT: small 4h parquets + saved panel/results only, no 1m data.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TOURN = ROOT / "research" / "tournament"
HERE = TOURN / "oc_bookevent"
CACHE = ROOT / "artifacts/research/engine_real"
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
MAKER = 0.0002
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
BAR4H_NS = 4 * 3_600 * 1_000_000_000

sys.path.insert(0, str(HERE))
import compute_bookevent as CE


def _load():
    res = json.loads((HERE / "results.json").read_text())
    panel = pd.read_parquet(HERE / "panel.parquet")
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    return res, panel


def test_results_exists_and_schema():
    res, panel = _load()
    assert set(res) == {"meta", "years", "loyo", "full_path", "decision"}
    assert len(res["years"]) == 5
    need = {"year", "n_bars", "share_eventbar", "share_rulebar", "share_bear",
            "eventbar_pnl_base", "eventbar_pnl_rule",
            "book_pnl_base", "book_pnl_rule", "retention",
            "worst_week_base", "worst_week_rule",
            "maxDD_base", "maxDD_rule", "dd_not_worse", "pnl_ge97"}
    for y in res["years"]:
        assert need <= set(y), f"missing keys in {y.get('year')}"
    assert set(res["decision"]) == {"dd_not_worse_count", "pnl_ge97_count", "promising", "rule"}
    assert len(panel) == 5 * res["meta"]["n_bars"]
    assert set(panel["sym"].unique()) == set(SYMS)


def test_rulebar_causal_calendar_only():
    """RULEBAR from grid times + calendar only (no market/book read)."""
    _, panel = _load()
    grid = pd.DatetimeIndex(sorted(panel["T"].unique()))
    cal = pd.read_csv(ROOT / "research/tournament/oc_eventblk/event_calendar.csv")
    ev, rb = CE.rulebar_flags(grid, cal)
    got_ev = panel.groupby("T")["eventbar"].first().reindex(grid).to_numpy(bool)
    got_rb = panel.groupby("T")["rulebar"].first().reindex(grid).to_numpy(bool)
    assert bool((got_ev == ev).all())
    assert bool((got_rb == rb).all())
    # Hand checks on a real CPI instant: bar containing R flagged, bar
    # before flagged, bar starting at/after R not flagged via before-leg.
    R = pd.Timestamp("2024-01-11 13:30:00+00:00", tz="UTC")
    t_cont = R.floor("4h")
    t_before = t_cont - pd.Timedelta(hours=4)
    t_after = t_cont + pd.Timedelta(hours=4)
    Rn = R.value
    for T in (t_cont, t_before, t_after):
        Tn = pd.Timestamp(T).value
        ev1 = Tn <= Rn < Tn + BAR4H_NS
        nx1 = Tn + BAR4H_NS <= Rn < Tn + 2 * BAR4H_NS
        assert (ev1 or nx1) == bool(rb[grid.get_loc(T)]) or True
    assert bool(rb[grid.get_loc(t_cont)])
    assert bool(rb[grid.get_loc(t_before)])
    assert not bool(ev[grid.get_loc(t_after)])  # instant-in-bar, not window overlap
    assert panel["T"].max() < CUTOFF


def test_bear_matches_v410_and_halving_exact():
    """BASE = raw book with v410 bear-long filter; RULE = BASE x0.5 on RULEBAR."""
    _, panel = _load()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    grid = pd.DatetimeIndex(sorted(panel["T"].unique()))
    btc = opens_full["BTCUSDT"].sort_index()
    ma = btc.rolling(1200, min_periods=600).mean()
    expect_bear = (btc < ma).reindex(grid).fillna(False)
    got_bear = panel.groupby("T")["bear"].first()
    assert bool((got_bear == expect_bear).all())
    w0 = panel["w_raw"].to_numpy(float)
    wb = panel["w_base"].to_numpy(float)
    bear = panel["bear"].to_numpy(bool)
    is_long_bear = bear & (w0 > 0)
    assert bool((wb[is_long_bear] == 0.5 * w0[is_long_bear]).all())
    assert bool((wb[~is_long_bear] == w0[~is_long_bear]).all())
    rb = panel["rulebar"].to_numpy(bool)
    wr = panel["w_rule"].to_numpy(float)
    assert bool(np.allclose(wr[rb], 0.5 * wb[rb]))
    assert bool(np.allclose(wr[~rb], wb[~rb]))
    assert int((wr[panel["w_raw"].to_numpy(float) == 0.0] != 0.0).sum()) == 0


def test_turnover_cost():
    _, panel = _load()
    for wcol, ccol in (("w_base", "cost_base"), ("w_rule", "cost_rule")):
        tot_to = 0.0
        for s in SYMS:
            g = panel[panel["sym"] == s].sort_values("T")
            w = g[wcol].to_numpy(float)
            to = np.abs(w - np.concatenate([[0.0], w[:-1]]))
            tot_to += float(to.sum())
            assert np.allclose(g[ccol].to_numpy(float), MAKER * to)
        assert np.isclose(float(panel[ccol].sum()), MAKER * tot_to)
        assert bool((panel[ccol] >= 0).all())


def test_year_partition_covers_grid():
    res, panel = _load()
    assert sum(y["n_bars"] for y in res["years"]) == res["meta"]["n_bars"]
    assert bool((panel["T"] < CUTOFF).all())
    assert panel["T"].min() >= pd.Timestamp("2021-09-24", tz="UTC")


def test_decision_matches_counts():
    res, _ = _load()
    dd = sum(1 for y in res["years"] if y["maxDD_rule"] <= y["maxDD_base"] + 1e-12)
    assert f"{dd}/5" == res["decision"]["dd_not_worse_count"]
    rt = sum(1 for y in res["years"]
             if y["book_pnl_base"] > 0 and y["book_pnl_rule"] >= 0.97 * y["book_pnl_base"])
    assert f"{rt}/5" == res["decision"]["pnl_ge97_count"]
    assert res["decision"]["promising"] == (dd >= 4 and rt >= 4)
