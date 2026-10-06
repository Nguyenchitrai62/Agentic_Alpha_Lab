"""Tests for research/tournament/oc_cmegap (pre-registered in PLAN.md)."""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
OC = ROOT / "research" / "tournament" / "oc_cmegap"
CACHE = ROOT / "artifacts" / "research" / "engine_real"
BTC1M = ROOT / "data" / "raw" / "btc_intraday_20260924"
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")


def _results():
    return json.loads((OC / "results.json").read_text())


def _panel():
    p = pd.read_parquet(OC / "panel.parquet")
    p["T"] = pd.to_datetime(p["T"], utc=True)
    return p


def _gaps():
    g = pd.read_parquet(OC / "gaps.parquet")
    for c in ("close_min", "reopen_min", "fill_minute"):
        g[c] = pd.to_datetime(g[c], utc=True)
    return g


def test_results_exists_and_schema():
    r = _results()
    assert set(r) == {"meta", "years", "full_path", "loyo", "decision"}
    assert len(r["years"]) == 5
    for y in r["years"]:
        for k in ("n_bars", "n_weekends", "n_gap", "n_large",
                  "fill_rate_large", "n_affected_bars", "affected_share",
                  "affected_pnl_base", "affected_pnl_rule",
                  "book_pnl_base", "book_pnl_rule", "worst_week_base",
                  "worst_week_rule", "maxDD_base", "maxDD_rule",
                  "pnl_not_lower", "dd_not_worse"):
            assert k in y, k
    assert set(r["full_path"]) == {"maxDD_base", "maxDD_rule",
                                   "total_pnl_base", "total_pnl_rule"}
    assert set(r["loyo"]) == {"pnl_stability", "dd_stability"}
    assert set(r["decision"]) == {"pnl_not_lower_count",
                                  "dd_not_worse_count", "promising"}


def _nth_weekday(year, month, weekday, n):
    d = _dt.date(year, month, 1)
    off = (weekday - d.weekday()) % 7
    return d + _dt.timedelta(days=off + 7 * (n - 1))


def test_gap_causality_and_dst():
    g = _gaps()
    # DST rule spot checks (season by Friday date; hours winter 21/22, summer 20/21).
    spot = {"2021-09-24": ("summer", 20, 21), "2021-11-19": ("winter", 21, 22),
            "2022-03-11": ("winter", 21, 22), "2022-03-18": ("summer", 20, 21),
            "2023-01-06": ("winter", 21, 22), "2023-07-14": ("summer", 20, 21)}
    for fri, (season, ch, rh) in spot.items():
        row = g[g["friday"] == fri]
        assert len(row) == 1, fri
        assert row["season"].iloc[0] == season, fri
        assert row["close_min"].iloc[0].hour == ch, fri
        assert row["reopen_min"].iloc[0].hour == rh, fri
        assert (row["reopen_min"].iloc[0] - row["close_min"].iloc[0]) == pd.Timedelta(days=2, hours=1)
    # DST boundary dates: 2nd Sun Mar / 1st Sun Nov.
    for y in (2021, 2022, 2023, 2024, 2025):
        s = _nth_weekday(y, 3, 6, 2)
        e = _nth_weekday(y, 11, 6, 1)
        assert s.weekday() == 6 and e.weekday() == 6
    # Causality: gaps recomputed from 1m truncated to open_time <= reopen are unchanged.
    frames = []
    for y in (2021, 2022, 2023, 2024, 2025, 2026):
        f = BTC1M / f"klines_1m_{y}.parquet"
        if f.exists():
            frames.append(pd.read_parquet(f, columns=["open_time", "close"]))
    m1 = pd.concat(frames, ignore_index=True)
    m1["open_time"] = pd.to_datetime(m1["open_time"], utc=True)
    m1 = m1[m1["open_time"] < CUTOFF].drop_duplicates("open_time").sort_values("open_time")
    close_s = pd.Series(m1["close"].to_numpy(float), index=m1["open_time"])
    for _, r in g.iloc[::25].iterrows():
        ro = r["reopen_min"]
        trunc = m1[m1["open_time"] <= ro]
        cs = pd.Series(trunc["close"].to_numpy(float), index=trunc["open_time"])
        c = cs.get(r["close_min"], np.nan)
        s = cs.get(ro, np.nan)
        expect = float(s) / float(c) - 1.0 if np.isfinite(c) and np.isfinite(s) else np.nan
        got = float(r["gap"])
        if np.isnan(expect):
            assert np.isnan(got)
        else:
            assert abs(got - expect) < 1e-12


def test_fill_strictly_before_T_and_first_row():
    p = _panel()
    g = _gaps()
    grid = pd.to_datetime(pd.Series(p["T"].drop_duplicates().sort_values().to_numpy()), utc=True)
    grid_ns = grid.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    aff = p.groupby("T")["affected"].first().reindex(grid).to_numpy(bool)
    gapv = p.groupby("T")["gap"].first().reindex(grid).to_numpy(float)
    # Recompute expected affected/gap from gaps.parquet per PLAN formulas.
    exp_aff = np.zeros(len(grid), dtype=bool)
    exp_gap = np.full(len(grid), np.nan)
    for _, r in g.iterrows():
        if not bool(r["large"]) or not np.isfinite(float(r["gap"])):
            continue
        ro = r["reopen_min"].value
        end = ro + 72 * 3_600_000_000_000
        m = (grid_ns > ro) & (grid_ns <= end)
        fm = r["fill_minute"]
        if pd.notna(fm):
            m = m & (grid_ns <= int(fm.value))
        assert not np.any(exp_aff[m]), "overlapping large-gap windows"
        exp_aff[m] = True
        exp_gap[m] = float(r["gap"])
    assert bool((aff == exp_aff).all())
    same = np.isfinite(gapv) & np.isfinite(exp_gap)
    assert bool(np.isnan(gapv[~exp_aff]).all())
    assert np.allclose(gapv[same], exp_gap[same], rtol=0, atol=1e-12)
    # Direct check: every affected bar has some weekend with reopen < T <= reopen+72h.
    ro_all = g[g["large"]]["reopen_min"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    for t, a in zip(grid_ns[exp_aff], np.where(exp_aff)[0]):
        assert bool(np.any((ro_all < t) & (t <= ro_all + 72 * 3_600_000_000_000)))
    # Fill strictly before T: rows after fill or after reopen+72h are not affected
    # (covered by exp_aff equality above, which encodes both cutoffs).


def test_rule_math():
    p = _panel()
    base = p["w_base"].to_numpy(float)
    rule = p["w_rule"].to_numpy(float)
    gap = p["gap"].to_numpy(float)
    aff = p["affected"].to_numpy(bool)
    # Shorts/flats bit-identical everywhere.
    assert bool((rule[base <= 0] == base[base <= 0]).all())
    # Non-affected rows bit-identical (all coins).
    assert bool((rule[~aff] == base[~aff]).all())
    # Affected rows: longs exactly x0.75 (up) / x1.25 (down); shorts identical.
    up = aff & np.isfinite(gap) & (gap > 0.02)
    dn = aff & np.isfinite(gap) & (gap < -0.02)
    assert up.any() and dn.any()
    assert bool((rule[up & (base > 0)] == 0.75 * base[up & (base > 0)]).all())
    assert bool((rule[dn & (base > 0)] == 1.25 * base[dn & (base > 0)]).all())
    assert bool((rule[up & (base <= 0)] == base[up & (base <= 0)]).all())
    assert bool((rule[dn & (base <= 0)] == base[dn & (base <= 0)]).all())
    # No small-gap scaling: every affected row has |gap| > 2%.
    assert bool((np.abs(gap[aff]) > 0.02).all())


def test_bear_matches_v410():
    p = _panel()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    btc = opens_full["BTCUSDT"].sort_index()
    ma = btc.rolling(1200, min_periods=600).mean()
    bear_full = (btc < ma).fillna(False)
    for t in p["T"].drop_duplicates().iloc[::997]:
        assert bool(bear_full.reindex([t]).fillna(False).iloc[0]) == bool(
            p.loc[p["T"] == t, "bear"].iloc[0])
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
        for _s, grp in p.groupby("sym"):
            grp = grp.sort_values("T")
            w = grp[wcol].to_numpy(float)
            to = np.abs(w - np.concatenate([[0.0], w[:-1]]))
            assert np.allclose(grp[ccol].to_numpy(float), 0.0005 * to, rtol=1e-12, atol=1e-18)
        assert bool((p[ccol].to_numpy(float) >= 0.0).all())


def test_year_partition_covers_grid():
    r = _results()
    p = _panel()
    assert sum(y["n_bars"] for y in r["years"]) == r["meta"]["n_bars"]
    assert bool((p["T"] < CUTOFF).all())
    assert r["meta"]["n_bars"] == 10955
    assert len(p) == 10955 * 5
    # Affected + unaffected panel rows sum to the panel per year (by grid-year).
    bounds = [pd.Timestamp(d, tz="UTC") for d in
              (["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24", "2026-09-24"])]
    tot = 0
    for k, y in enumerate(r["years"]):
        m = (p["T"] >= bounds[k]) & (p["T"] < bounds[k + 1])
        assert int(m.sum()) == y["n_bars"] * 5
        tot += y["n_bars"]
    assert tot == 10955


def test_decision_matches_counts():
    r = _results()
    pn = sum(1 for y in r["years"] if y["pnl_not_lower"])
    dd = sum(1 for y in r["years"] if y["dd_not_worse"])
    assert r["decision"]["pnl_not_lower_count"] == f"{pn}/5"
    assert r["decision"]["dd_not_worse_count"] == f"{dd}/5"
    assert r["decision"]["promising"] == bool(pn >= 4 and dd >= 4)
    # Recompute P&L/DD comparisons from the panel (independent path sums).
    p = _panel()
    bounds = [pd.Timestamp(d, tz="UTC") for d in
              (["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24", "2026-09-24"])]
    for k, y in enumerate(r["years"]):
        m = (p["T"] >= bounds[k]) & (p["T"] < bounds[k + 1])
        assert abs(float(p.loc[m, "pnl_base"].sum()) - y["book_pnl_base"]) < 2e-6
        assert abs(float(p.loc[m, "pnl_rule"].sum()) - y["book_pnl_rule"]) < 2e-6
        assert (float(p.loc[m, "pnl_rule"].sum()) >= float(p.loc[m, "pnl_base"].sum())) == y["pnl_not_lower"]
