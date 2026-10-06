"""Tests for oc_bookfunding (PLAN-pinned causality + alignment)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_bookfunding"
CACHE = ROOT / "artifacts/research/engine_real"
PREM = ROOT / "data/raw/binance_premium_20260928"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
FEAT_START = pd.Timestamp("2021-06-30", tz="UTC")
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
    rng = np.random.default_rng(56)
    sample = rng.choice(np.arange(700, len(grid)), size=5, replace=False)
    for i in sorted(sample):
        T = pd.Timestamp(grid[i]).tz_convert("UTC")
        cut = opens_full[opens_full.index <= T]
        btc = cut["BTCUSDT"].sort_index()
        ma = btc.rolling(1200, min_periods=600).mean()
        expect = bool((btc.loc[T] < ma.loc[T]) if T in ma.index and np.isfinite(ma.loc[T]) else False)
        got = bool(p[(p["T"] == T)].iloc[0]["bear"])
        assert got == expect, f"bear mismatch at {T}"
    bear = p["bear"].to_numpy(bool)
    wr = p["w_raw"].to_numpy(float)
    wb = p["w_base"].to_numpy(float)
    assert np.all(wb[(wr < 0)] == wr[(wr < 0)])
    assert np.all(wb[(wr == 0)] == 0.0)
    pos = wr > 0
    assert np.all(wb[pos & bear] == 0.5 * wr[pos & bear])
    assert np.all(wb[pos & ~bear] == wr[pos & ~bear])


def test_funding_causal():
    p = _panel()
    rng = np.random.default_rng(561)
    grid = p["T"].drop_duplicates().sort_values().to_numpy()
    idx = rng.choice(np.arange(500, len(grid)), size=4, replace=False)
    for i in sorted(idx):
        T = pd.Timestamp(grid[i]).tz_convert("UTC")
        s = SYMS[int(i) % 5]
        df = pd.read_parquet(PREM / f"{s}_funding.parquet")
        c = pd.to_datetime(df["calc_time"], utc=True)
        f = df["last_funding_rate"].to_numpy(float)
        sel = (c >= T - pd.Timedelta(days=7)) & (c < T)
        n = int(sel.sum())
        if n >= 14:
            expect = float(np.mean(f[sel.to_numpy()]))
        else:
            expect = np.nan
        got = p[(p["T"] == T) & (p["sym"] == s)].iloc[0]["F7"]
        if np.isnan(expect):
            assert not np.isfinite(got), f"F7 should be NaN at {T} {s} (n={n})"
        else:
            assert abs(float(got) - expect) < 1e-12, f"F7 mismatch at {T} {s}"
    # NaN-F7 rows never tilted; tilted longs exactly 0.75x base; shorts identical.
    f7 = p["F7"].to_numpy(float)
    tilt = p["tilt_on"].to_numpy(bool)
    assert not tilt[~np.isfinite(f7)].any()
    wb = p["w_base"].to_numpy(float)
    wru = p["w_rule"].to_numpy(float)
    pos = wb > 0
    assert np.all(wru[pos & tilt] == 0.75 * wb[pos & tilt])
    assert np.all(wru[pos & ~tilt] == wb[pos & ~tilt])
    assert np.all(wru[wb < 0] == wb[wb < 0])
    assert np.all(wru[wb == 0] == 0.0)


def test_cutoffs_causal():
    p = _panel()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    pre = opens_full.index[(opens_full.index >= FEAT_START) & (opens_full.index < ANCHORS[0])].sort_values()
    Tpre_ns = pre.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    ns7 = pd.Timedelta(days=7).to_timedelta64().astype("timedelta64[ns]").astype(np.int64)
    bounds = ANCHORS + [LAST_BOUND]
    for k, a0 in enumerate(ANCHORS):
        for s in SYMS:
            # panel rows strictly before A_k (book-grid part of the pool)
            tr_panel = p[(p["sym"] == s) & (p["T"] >= FEAT_START) & (p["T"] < a0)]["F7"].to_numpy(float)
            # pre-anchor 4h-grid part of the pool, recomputed from funding (strictly < each T)
            df = pd.read_parquet(PREM / f"{s}_funding.parquet")
            cns = pd.to_datetime(df["calc_time"], utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
            rates = df["last_funding_rate"].to_numpy(float)
            o = np.argsort(cns, kind="stable")
            cns, rates = cns[o], rates[o]
            cs = np.cumsum(np.concatenate([[0.0], rates]))
            left = np.searchsorted(cns, Tpre_ns - ns7, side="left")
            right = np.searchsorted(cns, Tpre_ns, side="left")
            n = right - left
            f_pre = np.full(len(Tpre_ns), np.nan)
            ok = (n >= 14) & (pre.to_numpy() < a0)
            f_pre[ok] = (cs[right[ok]] - cs[left[ok]]) / n[ok]
            tr = np.concatenate([f_pre[np.isfinite(f_pre)], tr_panel[np.isfinite(tr_panel)]])
            assert tr.size >= 100, f"year {k} {s}: only {tr.size} training values"
            expect = float(np.quantile(tr, 0.8))
            # all rows of year k share one q80 per coin; compare against panel value
            mk = (p["T"] >= bounds[k]) & (p["T"] < bounds[k + 1]) & (p["sym"] == s)
            assert np.allclose(p[mk]["q80"].to_numpy(float), expect, rtol=0, atol=1e-12), f"q80 mismatch year {k} {s}"
    # NaN-F7 rows never tilted (recheck across years).
    assert not p[~np.isfinite(p["F7"].to_numpy(float))]["tilt_on"].to_numpy(bool).any()


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
    tilt = p["tilt_on"].to_numpy(bool)
    wb = p["w_base"].to_numpy(float)
    wru = p["w_rule"].to_numpy(float)
    pos = wb > 0
    assert np.all(wru[pos & tilt] == 0.75 * wb[pos & tilt])
    assert np.all(wru[pos & ~tilt] == wb[pos & ~tilt])
    assert np.all(wru[~pos] == wb[~pos])
