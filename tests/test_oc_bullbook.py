"""Tests for oc_bullbook (research/tournament/oc_bullbook). Lightweight checks on results.json + causality of regimes/filters."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1] / "research" / "tournament" / "oc_bullbook"
RES = HERE / "results.json"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")


def _load():
    return json.loads(RES.read_text())


def _mod():
    spec = importlib.util.spec_from_file_location("oc_bullbook_compute", HERE / "compute_bullbook.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_results_exists_and_schema():
    assert RES.exists(), "run research/tournament/oc_bullbook/compute_bullbook.py first"
    r = _load()
    for k in ("meta", "years", "loyo_pnl", "full_path", "combined_daily", "totals", "decision"):
        assert k in r, k
    assert len(r["years"]) == 5 and len(r["combined_daily"]) == 5
    for row in r["years"]:
        for k in ("n_bars", "share_bear", "share_bullboost", "book_pnl_base",
                  "book_pnl_boost", "long_pnl_base", "long_pnl_boost",
                  "worst_week_base", "worst_week_boost",
                  "maxDD_base", "maxDD_boost", "pnl_higher", "dd_not_worse"):
            assert k in row, (row.get("year"), k)
    assert r["meta"]["n_bars"] == 10955


def test_year_partition_covers_grid():
    r = _load()
    ns = [row["n_bars"] for row in r["years"]]
    assert sum(ns) == r["meta"]["n_bars"] == 10955, ns
    assert ns[2] == 2196  # leap-year partition 2023-09-24..2024-09-24
    assert (ns[0], ns[1], ns[3], ns[4]) == (2190, 2190, 2190, 2189)


def test_turnover_cost_matches():
    r = _load()
    t = r["totals"]
    assert t["total_cost_base"] >= 0 and t["total_cost_boost"] >= 0
    assert abs(t["total_cost_base"] - 0.0005 * t["total_turnover_base"]) < 5e-4
    assert abs(t["total_cost_boost"] - 0.0005 * t["total_turnover_boost"]) < 5e-4
    assert t["total_turnover_boost"] > t["total_turnover_base"]  # 1.25x moves


def test_decision_matches_counts():
    r = _load()
    ys = r["years"]
    n_ret = sum(1 for y in ys if y["book_pnl_boost"] > y["book_pnl_base"])
    n_dd = sum(1 for y in ys if y["maxDD_boost"] < y["maxDD_base"])
    assert r["decision"]["pnl_higher_count"] == f"{n_ret}/5"
    assert r["decision"]["dd_not_worse_count"] == f"{n_dd}/5"
    assert r["decision"]["promising"] == (n_ret >= 4 and n_dd >= 3)
    assert r["decision"]["promising"] is False
    assert [y["pnl_higher"] for y in ys] == [y["book_pnl_boost"] > y["book_pnl_base"] for y in ys]
    assert [y["dd_not_worse"] for y in ys] == [y["maxDD_boost"] < y["maxDD_base"] for y in ys]


def test_filter_math_handchecked():
    mod = _mod()
    idx = pd.date_range("2023-01-01", periods=4, freq="4h", tz="UTC")
    books = pd.DataFrame([[0.10, -0.10, 0.0, 0.04, -0.04]] * 4, index=idx, columns=SYMS)
    bear = pd.Series([True, False, False, False], index=idx)
    bullboost = pd.Series([False, True, True, False], index=idx)
    base, boost = mod.apply_filters(books, bear, bullboost)
    # row0 bear: longs halved, shorts/flat unchanged
    assert base.iloc[0]["BNBUSDT"] == 0.05
    assert base.iloc[0]["BTCUSDT"] == -0.10
    assert base.iloc[0]["ETHUSDT"] == 0.0
    # row1 bullboost: base longs x1.25, shorts/flat unchanged
    assert boost.iloc[1]["BNBUSDT"] == 0.125
    assert boost.iloc[1]["BTCUSDT"] == -0.10
    assert boost.iloc[1]["ETHUSDT"] == 0.0
    # row2 bullboost but bear row keeps x0.5 and is never boosted:
    # (bear and bullboost are exclusive by construction; boosted base row2
    # must equal 1.25x the unfiltered long)
    assert boost.iloc[2]["SOLUSDT"] == 0.05
    # row3 neutral: unchanged on both paths
    pd.testing.assert_frame_equal(base.iloc[3:], books.iloc[3:], check_dtype=False)
    pd.testing.assert_frame_equal(boost.iloc[3:], base.iloc[3:], check_dtype=False)
    # Exclusivity note: apply_filters boosts any row with base > 0, so PLAN
    # exclusivity of bear (open < MA) vs bullboost (open > MA, strict) rests
    # on the regimes never coinciding — check on real data instead:
    both = pd.Series([True, False, False, False], index=idx)
    _, boost2 = mod.apply_filters(books, bear, both)
    assert boost2.iloc[0]["BNBUSDT"] == 0.05 * 1.25  # filter alone would stack
    r = _load()
    assert all(y["share_bear"] + y["share_bullboost"] <= 1.0 + 1e-9 for y in r["years"])


def test_regimes_causal_on_truncation():
    mod = _mod()
    rng = np.random.default_rng(7)
    n = 1500
    idx = pd.date_range("2022-01-01", periods=n + 1, freq="4h", tz="UTC")
    btc = 20000.0 * np.cumprod(1 + 0.004 * rng.standard_normal(n + 1))
    opens = pd.DataFrame({s: (100.0 if s != "BTCUSDT" else 1.0) for s in SYMS},
                         index=idx).astype(float)
    opens["BTCUSDT"] = btc
    grid = idx[:-1]
    bear, bull, ret180, bb = mod.build_regimes(opens, grid)
    cut = grid[1000]
    opens_tr = opens[opens.index <= cut + pd.Timedelta(hours=4)]
    grid_tr = grid[grid <= cut]
    bear_t, bull_t, ret_t, bb_t = mod.build_regimes(opens_tr, grid_tr)
    pd.testing.assert_series_equal(bear.reindex(grid_tr), bear_t, check_dtype=False)
    pd.testing.assert_series_equal(bull.reindex(grid_tr), bull_t, check_dtype=False)
    pd.testing.assert_series_equal(bb.reindex(grid_tr), bb_t, check_dtype=False)
    pd.testing.assert_series_equal(ret180.reindex(grid_tr), ret_t, check_dtype=False)


def test_T_and_bounds():
    r = _load()
    assert pd.Timestamp(r["meta"]["grid_end"], tz="UTC") < CUTOFF
    assert pd.Timestamp(r["meta"]["grid_start"], tz="UTC") >= pd.Timestamp("2021-09-24", tz="UTC")
    for c in r["combined_daily"]:
        assert c["n_days"] in (365, 366)
