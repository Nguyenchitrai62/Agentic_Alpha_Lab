"""Tests for oc_fomcbook (idea #66, pre-registered in PLAN.md).

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
HERE = TOURN / "oc_fomcbook"
CACHE = ROOT / "artifacts/research/engine_real"
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
MAKER = 0.0005
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]

sys.path.insert(0, str(HERE))
import compute_fomcbook as CF


def _load():
    res = json.loads((HERE / "results.json").read_text())
    panel = pd.read_parquet(HERE / "panel.parquet")
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    return res, panel


def test_results_exists_and_schema():
    res, panel = _load()
    assert set(res) == {"meta", "years", "loyo", "full_path", "decision"}
    assert len(res["years"]) == 5
    need = {"year", "n_bars", "share_rulebar", "share_bear",
            "eventbar_pnl_base", "eventbar_pnl_rule",
            "book_pnl_base", "book_pnl_rule", "retention",
            "worst_week_base", "worst_week_rule",
            "maxDD_base", "maxDD_rule", "dd_not_worse", "pnl_ge98"}
    for y in res["years"]:
        assert need <= set(y), f"missing keys in {y.get('year')}"
    assert set(res["decision"]) == {"dd_not_worse_count", "pnl_ge98_count",
                                    "promising", "rule"}
    assert len(panel) == 5 * res["meta"]["n_bars"]
    assert set(panel["sym"].unique()) == set(SYMS)


def test_rulebar_from_hardcoded_calendar_only():
    """RULEBAR from grid times + hard-coded FOMC list only (no market/book read)."""
    _, panel = _load()
    grid = pd.DatetimeIndex(sorted(panel["T"].unique()))
    R = CF.fomc_instants()
    assert len(R) == 56  # 8 scheduled statements x 7 years 2020-2026
    rb = CF.rulebar_flags(grid, R)
    got_rb = panel.groupby("T")["rulebar"].first().reindex(grid).to_numpy(bool)
    assert bool((got_rb == rb).all())
    # Boundary hand checks on a synthetic 4h grid around a known instant
    # (R = 2024-09-18 18:00 UTC, an EDT statement).
    R0 = pd.Timestamp("2024-09-18 18:00", tz="UTC")
    assert R0 in R
    synth = pd.DatetimeIndex(
        [R0 + pd.Timedelta(hours=h) for h in (-28, -24, -20, -4, 0, 4, 8)],
        tz="UTC",
    )
    got = CF.rulebar_flags(synth, R)
    # R-24h <= T <= R+4h inclusive; neighbours outside the window are clean
    # (other 2024 statements are weeks away, so no cross-contamination).
    expect = np.array([False, True, True, True, True, True, False])
    assert bool((got == expect).all()), dict(zip(synth.astype(str), got))
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
             if y["book_pnl_base"] > 0 and y["book_pnl_rule"] >= 0.98 * y["book_pnl_base"])
    assert f"{rt}/5" == res["decision"]["pnl_ge98_count"]
    assert res["decision"]["promising"] == (dd >= 4 and rt >= 4)
