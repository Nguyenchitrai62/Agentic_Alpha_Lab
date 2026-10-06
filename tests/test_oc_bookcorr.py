"""Tests for oc_bookcorr (idea #43, pre-registered in PLAN.md).

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
HERE = TOURN / "oc_bookcorr"
CACHE = ROOT / "artifacts/research/engine_real"
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
MAKER = 0.0002
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]

sys.path.insert(0, str(HERE))
import compute_bookcorr as CC


def _load():
    res = json.loads((HERE / "results.json").read_text())
    panel = pd.read_parquet(HERE / "panel.parquet")
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    return res, panel


def test_results_exists_and_schema():
    res, panel = _load()
    assert set(res) == {"meta", "years", "full_path", "loyo", "decision"}
    assert len(res["years"]) == 5
    need = {"year", "n_bars", "rho_coverage", "mean_rho", "avg_scale",
            "book_pnl_base", "book_pnl_scaled", "retention",
            "worst_week_base", "worst_week_scaled",
            "maxDD_base", "maxDD_scaled", "dd_improves", "retention_ok",
            "dip_sum", "combDD_base", "combDD_scaled"}
    for y in res["years"]:
        assert need <= set(y), f"missing keys in {y.get('year')}"
    assert set(res["decision"]) == {"dd_improve_count", "retention_ge90_count", "promising"}
    assert len(panel) == 5 * res["meta"]["n_bars"]


def test_scale_bounds():
    _, panel = _load()
    g = panel.groupby("T")["scale"].first()
    assert bool(((g >= 0.5) & (g <= 1.0)).all()), "scale must lie in [0.5, 1.0]"
    rho = panel.groupby("T")["rho"].first()
    lo = rho <= 0.5
    assert bool((g[lo] == 1.0).all()) if int(lo.sum()) else True
    nan = rho.isna()
    assert bool((g[nan] == 1.0).all()) if int(nan.sum()) else True
    hi = rho >= 1.0
    assert bool((g[hi] == 0.5).all()) if int(hi.sum()) else True
    # Synthetic unit check of the fixed clip mapping itself.
    r = np.array([-0.2, 0.0, 0.5, 0.7, 1.0, 1.4, np.nan])
    s = np.clip(1.5 - r, 0.5, 1.0)
    s[~np.isfinite(r)] = 1.0
    assert np.allclose(s[:6], [1.0, 1.0, 1.0, 0.8, 0.5, 0.5])
    assert s[6] == 1.0


def test_corr_causal_on_truncation():
    """rho(T) uses only rows strictly before T.

    (a) truncating opens to times <= T leaves rho(T) unchanged (nothing
    after T is used); (b) perturbing the contemporaneous open[T] itself
    leaves rho(T) unchanged (row T is not in its own window).
    """
    _, panel = _load()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    rho_saved = panel.groupby("T")["rho"].first()
    sample = [pd.Timestamp(t, tz="UTC") for t in (
        "2022-03-15 00:00", "2023-06-01 12:00", "2024-11-20 04:00",
        "2025-05-10 08:00", "2026-01-30 16:00")]
    for T in sample:
        trunc = opens_full[opens_full.index <= T]
        r_trunc = CC.rho_for_grid(trunc, pd.DatetimeIndex([T])).iloc[0]
        assert np.isclose(r_trunc, rho_saved[T], equal_nan=True), f"post-T leak at {T}"
        pert = opens_full.copy()
        pert.loc[T, SYMS] = pert.loc[T, SYMS] * 1.5
        r_pert = CC.rho_for_grid(pert, pd.DatetimeIndex([T])).iloc[0]
        assert np.isclose(r_pert, rho_saved[T], equal_nan=True), f"row-T leak at {T}"


def test_bear_matches_v410():
    """BASE = raw book with v410 bear-long filter (longs x0.5 in bear)."""
    _, panel = _load()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    grid = pd.DatetimeIndex(sorted(panel["T"].unique()))
    btc = opens_full["BTCUSDT"].sort_index()
    ma = btc.rolling(1200, min_periods=600).mean()
    expect_bear = (btc < ma).reindex(grid).fillna(False)
    got_bear = panel.groupby("T")["bear"].first()
    assert bool((got_bear == expect_bear).all())
    w0 = panel["w0"].to_numpy(float)
    wb = panel["w_base"].to_numpy(float)
    bear = panel["bear"].to_numpy(bool)
    is_long_bear = bear & (w0 > 0)
    assert bool((wb[is_long_bear] == 0.5 * w0[is_long_bear]).all())
    assert bool((wb[~is_long_bear] == w0[~is_long_bear]).all())
    # SCALED = BASE * per-bar scale on every coin (flats stay flat).
    sc = panel["scale"].to_numpy(float)
    ws = panel["w_scaled"].to_numpy(float)
    assert bool(np.allclose(ws, wb * sc))
    assert int((ws[w0 == 0.0] != 0.0).sum()) == 0


def test_turnover_cost():
    _, panel = _load()
    for wcol, ccol in (("w_base", "cost_base"), ("w_scaled", "cost_scaled")):
        tot_cost = 0.0
        tot_to = 0.0
        for s in SYMS:
            g = panel[panel["sym"] == s].sort_values("T")
            w = g[wcol].to_numpy(float)
            to = np.abs(w - np.concatenate([[0.0], w[:-1]]))
            tot_to += float(to.sum())
            assert np.allclose(g[ccol].to_numpy(float), MAKER * to)
        assert np.isclose(tot_cost + float(panel[ccol].sum()), MAKER * tot_to)
        assert bool((panel[ccol] >= 0).all())


def test_year_partition_covers_grid():
    res, panel = _load()
    assert sum(y["n_bars"] for y in res["years"]) == res["meta"]["n_bars"] == 10955
    assert bool((panel["T"] < CUTOFF).all())
    assert panel["T"].min() >= pd.Timestamp("2021-09-24", tz="UTC")


def test_decision_matches_counts():
    res, _ = _load()
    dd = sum(1 for y in res["years"] if y["maxDD_scaled"] < y["maxDD_base"])
    assert f"{dd}/5" == res["decision"]["dd_improve_count"]
    rt = sum(1 for y in res["years"]
             if y["book_pnl_base"] > 0 and y["book_pnl_scaled"] >= 0.9 * y["book_pnl_base"])
    assert f"{rt}/5" == res["decision"]["retention_ge90_count"]
    assert res["decision"]["promising"] == (dd >= 4 and rt >= 4)
    assert res["decision"]["promising"] is False
