"""Tests for research/tournament/oc_expirybook (pre-registered in PLAN.md)."""
from __future__ import annotations

import calendar
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
OC = ROOT / "research" / "tournament" / "oc_expirybook"
CACHE = ROOT / "artifacts" / "research" / "engine_real"
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")


def _results():
    return json.loads((OC / "results.json").read_text())


def _panel():
    p = pd.read_parquet(OC / "panel.parquet")
    p["T"] = pd.to_datetime(p["T"], utc=True)
    return p


def _expiry(y: int, m: int) -> pd.Timestamp:
    last_day = calendar.monthrange(y, m)[1]
    d = pd.Timestamp(y, m, last_day, tz="UTC")
    back = (d.weekday() - 4) % 7
    return (d - pd.Timedelta(days=int(back))).replace(hour=8, minute=0, second=0)


def test_results_exists_and_schema():
    r = _results()
    assert set(r) == {"meta", "years", "full_path", "decision"}
    assert len(r["years"]) == 5
    for y in r["years"]:
        for k in ("n_bars", "n_exp_bars", "exp_share", "win_pnl_base",
                  "win_pnl_rule", "out_pnl_base", "out_pnl_rule",
                  "cost_base", "cost_rule", "book_pnl_base", "book_pnl_rule",
                  "retention", "worst_week_base", "worst_week_rule",
                  "maxDD_base", "maxDD_rule", "dd_not_worse",
                  "retention_ge98"):
            assert k in y, k
    assert set(r["full_path"]) == {"maxDD_base", "maxDD_rule",
                                   "total_pnl_base", "total_pnl_rule"}
    assert set(r["decision"]) == {"dd_not_worse_count", "retention_ge98_count",
                                 "promising"}


def test_expiry_calendar_hand_checked():
    assert _expiry(2025, 9) == pd.Timestamp("2025-09-26 08:00", tz="UTC")
    assert _expiry(2024, 2) == pd.Timestamp("2024-02-23 08:00", tz="UTC")
    assert _expiry(2026, 6) == pd.Timestamp("2026-06-26 08:00", tz="UTC")
    for y in (2021, 2022, 2023, 2024, 2025, 2026):
        for m in range(1, 13):
            e = _expiry(y, m)
            assert e.weekday() == 4
            assert (e.hour, e.minute) == (8, 0)
    # Window flags equal [E-48h, E) membership (pure timestamps).
    p = _panel()
    idx = p["T"].drop_duplicates().sort_values().reset_index(drop=True)
    exp_list = [_expiry(y, m) for y in range(2021, 2027) for m in range(1, 13)]
    exp_list = [e for e in exp_list if e < CUTOFF + pd.Timedelta(days=1)]
    ti = idx.astype("int64").to_numpy()
    expect = np.zeros(len(idx), bool)
    H = np.int64(3_600_000_000_000)
    for e in exp_list:
        ev = np.int64(e.value)
        expect |= (ti >= ev - np.int64(48) * H) & (ti < ev)
    got = p.groupby("T", sort=True)["in_exp"].first()
    got = got.reindex(idx).to_numpy(bool)
    assert bool((got == expect).all())
    # Share matches ~12 expiries x 12 bars/year (~6.6%).
    assert 0.05 < float(got.mean()) < 0.08


def test_rule_math():
    p = _panel()
    g = p.groupby("T", sort=True)
    wb = g["w_base"].apply(lambda s: s.to_numpy())
    wr = g["w_rule"].apply(lambda s: s.to_numpy())
    wx = g["in_exp"].first().to_numpy(bool)
    Wb = np.stack(wb.to_numpy())
    Wr = np.stack(wr.to_numpy())
    # Rule is exactly half the base on expiry-window bars (both sides).
    assert bool((Wr[wx] == 0.5 * Wb[wx]).all())
    # Off-window bars bit-identical.
    assert bool((Wb[~wx] == Wr[~wx]).all())


def test_bear_matches_v410():
    p = _panel()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    btc = opens_full["BTCUSDT"].sort_index()
    ma = btc.rolling(1200, min_periods=600).mean()
    bear_full = (btc < ma).fillna(False)
    for t in p["T"].drop_duplicates().iloc[::997]:
        assert bool(bear_full.reindex([t]).fillna(False).iloc[0]) == bool(
            p.loc[p["T"] == t, "bear"].iloc[0])
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


def test_turnover_cost_and_partition():
    p = _panel()
    for wcol, ccol in (("w_base", "cost_base"), ("w_rule", "cost_rule")):
        for _s, gg in p.groupby("sym"):
            gg = gg.sort_values("T")
            w = gg[wcol].to_numpy(float)
            to = np.abs(w - np.concatenate([[0.0], w[:-1]]))
            assert np.allclose(gg[ccol].to_numpy(float), 0.0002 * to,
                               rtol=1e-12, atol=1e-18)
    r = _results()
    assert sum(y["n_bars"] for y in r["years"]) == r["meta"]["n_bars"]
    assert bool((p["T"] < CUTOFF).all())
    assert r["meta"]["n_bars"] == 10955
    # Window + complement P&L sums to totals each year.
    for y in r["years"]:
        assert abs(y["win_pnl_base"] + y["out_pnl_base"]
                   - y["book_pnl_base"]) < 2e-6
        assert abs(y["win_pnl_rule"] + y["out_pnl_rule"]
                   - y["book_pnl_rule"]) < 2e-6


def test_decision_matches_counts():
    r = _results()
    dd = sum(1 for y in r["years"] if y["dd_not_worse"])
    rt = sum(1 for y in r["years"] if y["retention_ge98"])
    assert r["decision"]["dd_not_worse_count"] == f"{dd}/5"
    assert r["decision"]["retention_ge98_count"] == f"{rt}/5"
    assert r["decision"]["promising"] == bool(dd >= 4 and rt >= 4)
    for y in r["years"]:
        assert y["dd_not_worse"] == bool(y["maxDD_rule"] <= y["maxDD_base"])
        if y["book_pnl_base"] > 0:
            assert y["retention_ge98"] == bool(
                y["book_pnl_rule"] >= 0.98 * y["book_pnl_base"])
