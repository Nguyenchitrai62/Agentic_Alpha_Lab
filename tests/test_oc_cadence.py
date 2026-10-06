"""Tests for oc_cadence (research/tournament/oc_cadence). Lightweight checks on results.json + causality of bear/cadence/costs."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1] / "research" / "tournament" / "oc_cadence"
RES = HERE / "results.json"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")


def _load():
    return json.loads(RES.read_text())


def _mod():
    spec = importlib.util.spec_from_file_location("oc_cadence_compute", HERE / "compute_cadence.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_results_exists_and_schema():
    assert RES.exists(), "run research/tournament/oc_cadence/compute_cadence.py first"
    r = _load()
    for k in ("meta", "years", "loyo_net8h", "full_path", "totals", "decision"):
        assert k in r, k
    assert len(r["years"]) == 5
    for row in r["years"]:
        for k in ("n_bars", "share_bear", "gross_base", "turnover_base",
                  "cost_base", "net_base", "gross_h8", "turnover_h8",
                  "cost_h8", "net_h8", "gross_h12", "turnover_h12",
                  "cost_h12", "net_h12", "worst_week_base", "worst_week_h8",
                  "maxDD_base", "maxDD_h8", "pnl_higher_8h", "dd_not_worse_8h"):
            assert k in row, (row.get("year"), k)
    assert r["meta"]["n_bars"] == 10955


def test_year_partition_covers_grid():
    r = _load()
    ns = [row["n_bars"] for row in r["years"]]
    assert sum(ns) == r["meta"]["n_bars"] == 10955, ns
    assert ns[2] == 2196  # leap-year partition 2023-09-24..2024-09-24
    assert (ns[0], ns[1], ns[3], ns[4]) == (2190, 2190, 2190, 2189)


def test_cost_math():
    r = _load()
    t = r["totals"]
    for suf in ("base", "h8", "h12"):
        assert t[f"total_cost_{suf}"] >= 0 and t[f"total_turnover_{suf}"] >= 0
        assert abs(t[f"total_cost_{suf}"] - 0.0005 * t[f"total_turnover_{suf}"]) < 5e-4
    # slower cadence must turn over less
    assert t["total_turnover_h8"] < t["total_turnover_base"]
    assert t["total_turnover_h12"] < t["total_turnover_h8"]
    for row in r["years"]:
        for suf in ("base", "h8", "h12"):
            assert abs(row[f"cost_{suf}"] - 0.0005 * row[f"turnover_{suf}"]) < 5e-4
            assert abs(row[f"net_{suf}"] - (row[f"gross_{suf}"] - row[f"cost_{suf}"])) < 5e-4


def test_decision_matches_counts():
    r = _load()
    ys = r["years"]
    n_ret = sum(1 for y in ys if y["net_h8"] > y["net_base"])
    n_dd = sum(1 for y in ys if y["maxDD_h8"] <= y["maxDD_base"])
    assert r["decision"]["pnl_higher_count"] == f"{n_ret}/5"
    assert r["decision"]["dd_not_worse_count"] == f"{n_dd}/5"
    assert r["decision"]["promising"] == (n_ret >= 4 and n_dd >= 4)
    assert r["decision"]["promising"] is False
    assert [y["pnl_higher_8h"] for y in ys] == [y["net_h8"] > y["net_base"] for y in ys]
    assert [y["dd_not_worse_8h"] for y in ys] == [y["maxDD_h8"] <= y["maxDD_base"] for y in ys]


def test_cadence_hold_handchecked():
    mod = _mod()
    idx = pd.date_range("2023-01-01", periods=6, freq="4h", tz="UTC")
    base = pd.DataFrame([[0.10 * (i + 1), -0.01 * (i + 1), 0.0, 0.02, -0.02] for i in range(6)],
                        index=idx, columns=SYMS)
    w8 = mod.apply_cadence(base, 2)
    w12 = mod.apply_cadence(base, 3)
    # 8h: even rows update, odd rows hold previous (compare values; index differs by row)
    np.testing.assert_allclose(w8.iloc[0].to_numpy(), base.iloc[0].to_numpy(), rtol=0, atol=0)
    np.testing.assert_allclose(w8.iloc[1].to_numpy(), base.iloc[0].to_numpy(), rtol=0, atol=0)
    np.testing.assert_allclose(w8.iloc[2].to_numpy(), base.iloc[2].to_numpy(), rtol=0, atol=0)
    np.testing.assert_allclose(w8.iloc[3].to_numpy(), base.iloc[2].to_numpy(), rtol=0, atol=0)
    # 12h: rows 0,3 update; rows 1,2 hold row 0; rows 4,5 hold row 3
    np.testing.assert_allclose(w12.iloc[1].to_numpy(), base.iloc[0].to_numpy(), rtol=0, atol=0)
    np.testing.assert_allclose(w12.iloc[2].to_numpy(), base.iloc[0].to_numpy(), rtol=0, atol=0)
    np.testing.assert_allclose(w12.iloc[3].to_numpy(), base.iloc[3].to_numpy(), rtol=0, atol=0)
    np.testing.assert_allclose(w12.iloc[4].to_numpy(), base.iloc[3].to_numpy(), rtol=0, atol=0)
    np.testing.assert_allclose(w12.iloc[5].to_numpy(), base.iloc[3].to_numpy(), rtol=0, atol=0)


def test_bear_causal_on_truncation():
    mod = _mod()
    rng = np.random.default_rng(11)
    n = 1500
    idx = pd.date_range("2022-01-01", periods=n + 1, freq="4h", tz="UTC")
    btc = 20000.0 * np.cumprod(1 + 0.004 * rng.standard_normal(n + 1))
    opens = pd.DataFrame({s: 100.0 for s in SYMS}, index=idx).astype(float)
    opens["BTCUSDT"] = btc
    grid = idx[:-1]
    bear = mod.build_bear(opens, grid)
    cut = grid[1000]
    opens_tr = opens[opens.index <= cut + pd.Timedelta(hours=4)]
    grid_tr = grid[grid <= cut]
    bear_t = mod.build_bear(opens_tr, grid_tr)
    pd.testing.assert_series_equal(bear.reindex(grid_tr), bear_t, check_dtype=False)


def test_T_and_bounds():
    r = _load()
    assert pd.Timestamp(r["meta"]["grid_end"], tz="UTC") < CUTOFF
    assert pd.Timestamp(r["meta"]["grid_start"], tz="UTC") >= pd.Timestamp("2021-09-24", tz="UTC")
