"""Tests for research/tournament/oc_bookweekend (pre-registered in PLAN.md)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
OC = ROOT / "research" / "tournament" / "oc_bookweekend"
CACHE = ROOT / "artifacts" / "research" / "engine_real"
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")


def _results():
    return json.loads((OC / "results.json").read_text())


def _panel():
    p = pd.read_parquet(OC / "panel.parquet")
    p["T"] = pd.to_datetime(p["T"], utc=True)
    return p


def test_results_exists_and_schema():
    r = _results()
    assert set(r) == {"meta", "years", "full_path", "loyo", "decision"}
    assert len(r["years"]) == 5
    for y in r["years"]:
        for k in ("n_bars", "weekend_share", "base_weekend_pnl",
                  "base_weekday_pnl", "cost_base", "cost_rule",
                  "book_pnl_base", "book_pnl_rule", "worst_week_base",
                  "worst_week_rule", "maxDD_base", "maxDD_rule",
                  "pnl_not_lower", "dd_not_worse"):
            assert k in y, k
    assert set(r["full_path"]) == {"maxDD_base", "maxDD_rule",
                                   "total_pnl_base", "total_pnl_rule"}
    assert set(r["loyo"]) == {"pnl_stability", "dd_stability"}


def test_weekend_math():
    p = _panel()
    g = p.groupby("T", sort=True)
    wb = g["w_base"].apply(lambda s: s.to_numpy())
    wr = g["w_rule"].apply(lambda s: s.to_numpy())
    wk = g["weekend"].first().to_numpy(bool)
    Wb = np.stack(wb.to_numpy())
    Wr = np.stack(wr.to_numpy())
    # Rule weights exactly 0 on weekend bars.
    assert bool((Wr[wk] == 0.0).all())
    # Weekday bars bit-identical to BASE.
    assert bool((Wb[~wk] == Wr[~wk]).all())
    # Weekend mask == weekday >= 5 and matches [Sat 00:00, Mon 00:00).
    idx = pd.to_datetime(pd.Series(list(wb.index)), utc=True)
    expect = (idx.dt.weekday >= 5).to_numpy()
    assert bool((wk == expect).all())
    assert bool((idx[wk].dt.weekday.isin([5, 6])).all())
    assert bool((~idx[~wk].dt.weekday.isin([5, 6])).all())
    # Sampled full weekends have 12 flat bars (Sat 00 .. Sun 20).
    sats = idx[(idx.dt.weekday == 5) & (idx.dt.hour == 0)]
    assert len(sats) > 200
    for t in sats[::25]:
        block = idx[(idx >= t) & (idx < t + pd.Timedelta(days=2))]
        assert len(block) == 12
        assert bool(wk[idx.isin(block)].all())
    # Monday-00:00 bars are not weekend (reopen per normal targets).
    mons = idx[(idx.dt.weekday == 0) & (idx.dt.hour == 0)]
    assert len(mons) > 200
    assert bool((~wk[idx.isin(mons)]).all())


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
    # BASE panel weights match raw book + bear filter on sampled rows.
    g = p.groupby("T", sort=True)
    wr_ = g["w_raw"].apply(lambda s: s.to_numpy())
    wb_ = g["w_base"].apply(lambda s: s.to_numpy())
    be = g["bear"].first().to_numpy(bool)
    W0 = np.stack(wr_.to_numpy())
    Wb = np.stack(wb_.to_numpy())
    pos = W0 > 0
    assert bool((Wb[be[:, None] & pos] == 0.5 * W0[be[:, None] & pos]).all())
    assert bool((Wb[~(be[:, None] & pos)] == W0[~(be[:, None] & pos)]).all())


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
    assert bool((p["T"] < CUTOFF).all())
    assert r["meta"]["n_bars"] == 10955
    # Weekend/weekday BASE legs sum to the BASE total each year.
    for y in r["years"]:
        assert abs(y["base_weekend_pnl"] + y["base_weekday_pnl"]
                   - y["book_pnl_base"]) < 2e-6


def test_decision_matches_counts():
    r = _results()
    pn = sum(1 for y in r["years"] if y["pnl_not_lower"])
    dd = sum(1 for y in r["years"] if y["dd_not_worse"])
    assert r["decision"]["pnl_not_lower_count"] == f"{pn}/5"
    assert r["decision"]["dd_not_worse_count"] == f"{dd}/5"
    assert r["decision"]["promising"] == bool(pn >= 4 and dd >= 4)
