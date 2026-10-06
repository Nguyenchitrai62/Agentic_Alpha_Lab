"""Tests for oc_bearshort (PLAN-pinned causality + alignment)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_bearshort"
CACHE = ROOT / "artifacts/research/engine_real"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)


def _panel() -> pd.DataFrame:
    p = pd.read_parquet(HERE / "panel.parquet")
    p["T"] = pd.to_datetime(p["T"], utc=True)
    return p


def test_books_match_dvolshort():
    m = lambda f: pd.read_parquet(CACHE / f)[SYMS]  # noqa: E731
    A, Aq = m("member_A_O1_orders.parquet"), m("member_Aq_O1_orders.parquet")
    B, Bq = m("member_B_tv.parquet"), m("member_Bq_tv.parquet")
    idx = A.index.union(Aq.index)
    f = lambda X: X.reindex(idx).fillna(0.0)  # noqa: E731
    o1 = 0.5 * (f(A) + f(B)) / 2 + 0.5 * (f(Aq) + f(Bq)) / 2
    D = pd.read_parquet(CACHE / "members_v154.parquet").xs("D", axis=1, level=0)[SYMS]
    Dq = pd.read_parquet(CACHE / "members_quarterly_D.parquet")[SYMS]
    idx2 = o1.index.union(D.index).union(Dq.index)
    g = lambda X: X.reindex(idx2).fillna(0.0)  # noqa: E731
    books = 0.8 * g(o1) + 0.2 * (g(D) + g(Dq)) / 2
    p = _panel()
    piv = p.pivot_table(index="T", columns="sym", values="w_raw").reindex(books.index)
    common = piv.dropna(how="all").index.intersection(books.index)
    assert len(common) > 10000
    np.testing.assert_allclose(
        piv.reindex(common)[SYMS].to_numpy(float),
        books.reindex(common)[SYMS].to_numpy(float), rtol=0, atol=1e-12)


def test_bear_causal():
    p = _panel()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    grid = p["T"].drop_duplicates().sort_values().to_numpy()
    rng = np.random.default_rng(53)
    sample = rng.choice(np.arange(700, len(grid)), size=5, replace=False)
    for i in sorted(sample):
        T = pd.Timestamp(grid[i]).tz_convert("UTC")
        cut = opens_full[opens_full.index <= T]
        btc = cut["BTCUSDT"].sort_index()
        ma = btc.rolling(1200, min_periods=600).mean()
        expect = bool((btc.loc[T] < ma.loc[T]) if T in ma.index and np.isfinite(ma.loc[T]) else False)
        got = bool(p[(p["T"] == T)].iloc[0]["bear"])
        assert got == expect, f"bear mismatch at {T}"
    # BASE = v410: shorts/flats bit-identical; longs halved exactly where flagged.
    bear = p["bear"].to_numpy(bool)
    wr = p["w_raw"].to_numpy(float)
    wb = p["w_base"].to_numpy(float)
    assert np.all(wb[(wr < 0)] == wr[(wr < 0)])
    assert np.all(wb[(wr == 0)] == 0.0)
    pos = wr > 0
    assert np.all(wb[pos & bear] == 0.5 * wr[pos & bear])
    assert np.all(wb[pos & ~bear] == wr[pos & ~bear])
    # RULE: bear-row shorts exactly 1.25x base; everything else bit-identical.
    wru = p["w_rule"].to_numpy(float)
    neg = wb < 0
    assert np.all(wru[neg & bear] == 1.25 * wb[neg & bear])
    assert np.all(wru[neg & ~bear] == wb[neg & ~bear])
    assert np.all(wru[~neg] == wb[~neg])
    boosted = p["boosted"].to_numpy(bool)
    assert np.all(boosted == (neg & bear))


def test_grid_bounds():
    p = _panel()
    res = json.loads((HERE / "results.json").read_text())
    assert (p["T"] < CUTOFF).all()
    grid = p["T"].drop_duplicates().sort_values()
    bounds = ANCHORS + [LAST_BOUND]
    total = 0
    for k in range(5):
        m = (grid >= bounds[k]) & (grid < bounds[k + 1])
        total += int(m.sum())
    assert total == len(grid)
    assert p["pnl_base"].notna().all() and p["pnl_rule"].notna().all()
    # Short-leg membership fixed by base sign in results.json.
    for k, y in enumerate(res["years"]):
        m = (p["T"] >= bounds[k]) & (p["T"] < bounds[k + 1])
        sub = p[m & (p["w_base"] < 0)]
        assert round(float(sub["pnl_base"].sum()), 6) == y["short_pnl_base"]
        assert round(float(sub["pnl_rule"].sum()), 6) == y["short_pnl_rule"]
        assert round(float(p[m]["pnl_base"].sum()), 6) == y["book_pnl_base"]
        assert round(float(p[m]["pnl_rule"].sum()), 6) == y["book_pnl_rule"]
