"""Tests for oc_bookcoinbrake (PLAN-pinned causality + alignment)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_bookcoinbrake"
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
    rng = np.random.default_rng(45)
    sample = rng.choice(np.arange(700, len(grid)), size=5, replace=False)
    for i in sorted(sample):
        T = pd.Timestamp(grid[i]).tz_convert("UTC")
        cut = opens_full[opens_full.index <= T]
        btc = cut["BTCUSDT"].sort_index()
        ma = btc.rolling(1200, min_periods=600).mean()
        expect = bool((btc.loc[T] < ma.loc[T]) if T in ma.index and np.isfinite(ma.loc[T]) else False)
        got = bool(p[(p["T"] == T)].iloc[0]["bear"])
        assert got == expect, f"bear mismatch at {T}"
    # Shorts/flats bit-identical under bear; longs halved exactly where flagged.
    bear = p["bear"].to_numpy(bool)
    wr = p["w_raw"].to_numpy(float)
    wb = p["w_base"].to_numpy(float)
    assert np.all(wb[(wr < 0)] == wr[(wr < 0)])
    assert np.all(wb[(wr == 0)] == 0.0)
    pos = wr > 0
    assert np.all(wb[pos & bear] == 0.5 * wr[pos & bear])
    assert np.all(wb[pos & ~bear] == wr[pos & ~bear])


def test_brake_causal():
    p = _panel()
    # Recompute S30/M/brake for sampled (T,s) from rows strictly < T.
    wide_pnl = p.pivot_table(index="T", columns="sym", values="pnl_base").sort_index()
    times = wide_pnl.index
    rng = np.random.default_rng(451)
    idx = rng.choice(np.arange(600, len(times)), size=4, replace=False)
    syms = [SYMS[i % 5] for i in range(4)]
    for i, s in zip(sorted(idx), syms):
        T = times[i]
        win30 = wide_pnl[s][(times >= T - pd.Timedelta(days=30)) & (times < T)]
        expect_s30 = float(win30.sum())
        got = p[(p["T"] == T) & (p["sym"] == s)].iloc[0]
        assert abs(got["S30"] - expect_s30) < 1e-9, f"S30 mismatch at {T} {s}"
        hist = []
        for t in times[(times >= T - pd.Timedelta(days=365)) & (times < T)]:
            w = wide_pnl[s][(times >= t - pd.Timedelta(days=30)) & (times < t)]
            hist.append(float(w.sum()))
        if len(hist) >= 200:
            expect_m = float(np.median(np.abs(np.asarray(hist))))
            assert abs(got["M"] - expect_m) < 1e-9, f"M mismatch at {T} {s}"
        else:
            assert not np.isfinite(got["M"]), f"M should be NaN at {T} {s}"
    # Exit transitions happen on S30 > 0; shorts unchanged under the rule.
    for s in SYMS:
        g = p[p["sym"] == s].sort_values("T")
        b = g["brake_on"].to_numpy(bool)
        exits = np.where(b[:-1] & ~b[1:])[0] + 1
        assert all(float(g.iloc[e]["S30"]) > 0 for e in exits[:50])
    neg = p["w_base"].to_numpy(float) < 0
    assert np.all(p["w_rule"].to_numpy(float)[neg] == p["w_base"].to_numpy(float)[neg])


def test_grid_bounds():
    p = _panel()
    assert (p["T"] < CUTOFF).all()
    grid = p["T"].drop_duplicates().sort_values()
    bounds = ANCHORS + [LAST_BOUND]
    total = 0
    for k in range(5):
        m = (grid >= bounds[k]) & (grid < bounds[k + 1])
        total += int(m.sum())
    assert total == len(grid)
    # Rule longs exactly 0.5x base where brake_on, else identical.
    br = p["brake_on"].to_numpy(bool)
    wb = p["w_base"].to_numpy(float)
    wru = p["w_rule"].to_numpy(float)
    pos = wb > 0
    assert np.all(wru[pos & br] == 0.5 * wb[pos & br])
    assert np.all(wru[pos & ~br] == wb[pos & ~br])
    assert np.all(wru[~pos] == wb[~pos])
