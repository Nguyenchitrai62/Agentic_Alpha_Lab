"""Tests for research/tournament/oc_bookholdcap (pre-registered in PLAN.md)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
OC = ROOT / "research" / "tournament" / "oc_bookholdcap"
CACHE = ROOT / "artifacts" / "research" / "engine_real"
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
HOLD = 42


def _results():
    return json.loads((OC / "results.json").read_text())


def _panel():
    p = pd.read_parquet(OC / "panel.parquet")
    p["T"] = pd.to_datetime(p["T"], utc=True)
    return p


def test_results_exists_and_schema():
    r = _results()
    assert set(r) == {"meta", "years", "full_path", "loyo", "decision"}
    assert r["meta"]["hold_bars"] == HOLD
    assert len(r["years"]) == 5
    for y in r["years"]:
        for k in ("n_bars", "n_cells", "n_forced", "forced_share",
                  "cost_base", "cost_rule", "book_pnl_base",
                  "book_pnl_rule", "pnl_ratio", "worst_week_base",
                  "worst_week_rule", "maxDD_base", "maxDD_rule",
                  "pnl_ge97", "dd_not_worse"):
            assert k in y, k
    assert set(r["full_path"]) == {"maxDD_base", "maxDD_rule",
                                   "total_pnl_base", "total_pnl_rule"}
    assert set(r["loyo"]) == {"pnl_stability", "dd_stability"}


def test_holdcap_math():
    p = _panel()
    # Rebuild (n_bars, 5) matrices in grid order.
    grid = pd.DatetimeIndex(sorted(p["T"].unique()))
    syms = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    Wb = np.stack([p.loc[p["sym"] == s].sort_values("T")["w_base"].to_numpy(float)
                   for s in syms], axis=1)
    Wr = np.stack([p.loc[p["sym"] == s].sort_values("T")["w_rule"].to_numpy(float)
                   for s in syms], axis=1)
    F = np.stack([p.loc[p["sym"] == s].sort_values("T")["forced"].to_numpy(bool)
                  for s in syms], axis=1)
    assert Wb.shape == Wr.shape == F.shape
    # Forced rows are exactly 0 and unforced rows bit-identical to BASE.
    assert bool((Wr[F] == 0.0).all())
    assert bool((Wr[~F] == Wb[~F]).all())
    # Every forced row has 42 prior capped all same non-zero sign.
    for j in range(Wr.shape[1]):
        col = Wr[:, j]
        for i in np.where(F[:, j])[0]:
            assert i >= HOLD, "first 42 bars per sym never forced"
            prev = col[i - HOLD:i]
            assert bool((prev > 0).all()) or bool((prev < 0).all()), i
    # No unforced row (with enough history) has 42 prior capped same-sign.
    for j in range(Wr.shape[1]):
        col = Wr[:, j]
        for i in range(HOLD, len(col)):
            if F[i, j]:
                continue
            prev = col[i - HOLD:i]
            assert not (bool((prev > 0).all()) or bool((prev < 0).all())), i
    # Max capped same-sign run (broken by forced flats) is <= 42.
    for j in range(Wr.shape[1]):
        col = Wr[:, j]
        rp = rn = 0
        for v in col:
            rp = rp + 1 if v > 0 else 0
            rn = rn + 1 if v < 0 else 0
            assert rp <= HOLD and rn <= HOLD
    # First 42 grid bars per sym never forced; forced share recomputes.
    assert not F[:HOLD].any()
    r = _results()
    for y, k in zip(r["years"], range(5)):
        assert y["n_forced"] >= 0
        assert y["forced_share"] == round(y["n_forced"] / y["n_cells"], 6)


def test_bear_matches_v410():
    p = _panel()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    btc = opens_full["BTCUSDT"].sort_index()
    ma = btc.rolling(1200, min_periods=600).mean()
    bear_full = (btc < ma).fillna(False)
    for t in p["T"].drop_duplicates().iloc[::997]:
        assert bool(bear_full.reindex([t]).fillna(False).iloc[0]) == bool(
            p.loc[p["T"] == t, "bear"].iloc[0])
    # Synthetic: longs halved in bear, shorts/flat unchanged.
    w = np.array([[0.4, -0.3, 0.0, 0.8, -0.1]])
    bear = np.array([True])
    base = w.copy()
    base[bear[:, None] & (w > 0)] = 0.5 * w[bear[:, None] & (w > 0)]
    assert np.allclose(base, [[0.2, -0.3, 0.0, 0.4, -0.1]])
    # BASE panel weights match raw book + bear filter on all rows.
    assert bool((p.loc[p["bear"] & (p["w_raw"] > 0), "w_base"]
                 == 0.5 * p.loc[p["bear"] & (p["w_raw"] > 0), "w_raw"]).all())
    m = ~(p["bear"].to_numpy(bool) & (p["w_raw"].to_numpy(float) > 0))
    assert bool((p["w_base"].to_numpy(float)[m]
                 == p["w_raw"].to_numpy(float)[m]).all())


def test_turnover_cost():
    p = _panel()
    for wcol, ccol in (("w_base", "cost_base"), ("w_rule", "cost_rule")):
        tot_cost, tot_to = 0.0, 0.0
        for _s, g in p.groupby("sym"):
            g = g.sort_values("T")
            w = g[wcol].to_numpy(float)
            to = np.abs(w - np.concatenate([[0.0], w[:-1]]))
            assert np.allclose(g[ccol].to_numpy(float), 0.0005 * to, rtol=1e-12, atol=1e-18)
            tot_cost += float(g[ccol].sum())
            tot_to += float(to.sum())
        assert abs(tot_cost - 0.0005 * tot_to) < 1e-9
        assert tot_cost >= 0.0


def test_year_partition_covers_grid():
    r = _results()
    p = _panel()
    assert sum(y["n_bars"] for y in r["years"]) == r["meta"]["n_bars"]
    assert sum(y["n_cells"] for y in r["years"]) == len(p) == r["meta"]["n_panel"]
    assert bool((p["T"] < CUTOFF).all())
    assert r["meta"]["n_bars"] == 10955
    assert set(p["sym"].unique()) == {"BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"}


def test_decision_matches_counts():
    r = _results()

    def pnl_ok(y):
        b, q = y["book_pnl_base"], y["book_pnl_rule"]
        if not (np.isfinite(b) and np.isfinite(q)):
            return False
        return (q >= b) if b <= 0 else (q >= 0.97 * b)

    pn = sum(1 for y in r["years"] if pnl_ok(y))
    dd = sum(1 for y in r["years"] if y["maxDD_rule"] <= y["maxDD_base"])
    assert sum(1 for y in r["years"] if y["pnl_ge97"]) == pn
    assert sum(1 for y in r["years"] if y["dd_not_worse"]) == dd
    assert r["decision"]["pnl_ge97_count"] == f"{pn}/5"
    assert r["decision"]["dd_not_worse_count"] == f"{dd}/5"
    assert r["decision"]["promising"] == bool(pn >= 4 and dd >= 4)
