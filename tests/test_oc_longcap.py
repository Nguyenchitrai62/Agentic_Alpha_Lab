"""Tests for research/tournament/oc_longcap (pre-registered in PLAN.md)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
OC = ROOT / "research" / "tournament" / "oc_longcap"
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
    assert set(r) == {"meta", "longsum_overall", "years", "window", "full_path", "loyo", "decision"}
    assert len(r["years"]) == 5
    for y in r["years"]:
        for k in ("n_bars", "binding_share", "book_pnl_base", "book_pnl_capped",
                  "long_pnl_base", "long_pnl_capped", "worst_week_base",
                  "worst_week_capped", "maxDD_base", "maxDD_capped",
                  "dd_not_worse", "retention_ok"):
            assert k in y, k
    assert set(r["window"]) == {"start", "end", "n_bars", "binding_share",
                                "book_pnl_base", "book_pnl_capped",
                                "long_pnl_base", "long_pnl_capped"}


def test_cap_math():
    p = _panel()
    g = p.groupby("T", sort=True)
    wb = g["w_base"].apply(lambda s: s.to_numpy())
    wc = g["w_capped"].apply(lambda s: s.to_numpy())
    idx = pd.to_datetime(pd.Series(list(wb.index)), utc=True)
    Wb = np.stack(wb.to_numpy())
    Wc = np.stack(wc.to_numpy())
    L = np.where(Wb > 0, Wb, 0.0).sum(axis=1)
    Lc = np.where(Wc > 0, Wc, 0.0).sum(axis=1)
    assert bool((Lc <= 0.6 + 1e-12).all())
    # Non-binding bars bit-identical across all coins.
    nb = ~(L > 0.6)
    assert bool((Wb[nb] == Wc[nb]).all())
    # Shorts/flats bit-identical everywhere.
    mask_short_flat = ~(Wb > 0)
    assert bool((Wb[mask_short_flat] == Wc[mask_short_flat]).all())
    # Binding bars: scale == 0.6 / L on longs.
    b = L > 0.6
    assert bool(b.any())
    expect = 0.6 / L[b]
    got = Wc[b][Wb[b] > 0] / Wb[b][Wb[b] > 0]
    assert np.allclose(got, np.repeat(expect, (Wb[b] > 0).sum(axis=1)), rtol=1e-12, atol=1e-15)
    # Panel scale column matches.
    sc = g["scale"].first().to_numpy(float)
    assert np.allclose(sc[b], expect, rtol=1e-12, atol=1e-15)
    assert bool((sc[nb] == 1.0).all())


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


def test_turnover_cost():
    p = _panel()
    for wcol, ccol in (("w_base", "cost_base"), ("w_capped", "cost_capped")):
        tot_cost, tot_to = 0.0, 0.0
        for _s, g in p.groupby("sym"):
            g = g.sort_values("T")
            w = g[wcol].to_numpy(float)
            to = np.abs(w - np.concatenate([[0.0], w[:-1]]))
            assert np.allclose(g[ccol].to_numpy(float), 0.0002 * to, rtol=1e-12, atol=1e-18)
            tot_cost += float(g[ccol].sum())
            tot_to += float(to.sum())
        assert abs(tot_cost - 0.0002 * tot_to) < 1e-9
        assert tot_cost >= 0.0


def test_year_partition_covers_grid():
    r = _results()
    p = _panel()
    assert sum(y["n_bars"] for y in r["years"]) == r["meta"]["n_bars"]
    assert bool((p["T"] < CUTOFF).all())
    assert r["meta"]["n_bars"] == 10955
    w0, w1 = pd.Timestamp(r["window"]["start"]), pd.Timestamp(r["window"]["end"])
    assert p["T"].min() <= w0 < w1 <= p["T"].max() + pd.Timedelta(hours=4)


def test_decision_matches_counts():
    r = _results()
    dd = sum(1 for y in r["years"] if y["dd_not_worse"])
    rt = sum(1 for y in r["years"] if y["retention_ok"])
    assert r["decision"]["dd_not_worse_count"] == f"{dd}/5"
    assert r["decision"]["retention_ge95_count"] == f"{rt}/5"
    assert r["decision"]["promising"] == bool(dd >= 4 and rt >= 4)
