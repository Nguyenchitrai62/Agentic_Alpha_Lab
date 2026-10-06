"""Tests for oc_cbpremium (PLAN-pinned causality + alignment)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_cbpremium"
CACHE = ROOT / "artifacts/research/engine_real"
CB = ROOT / "data/raw/coinbase_20260925/BTC-USD_1h.parquet"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)
NS = 1_000_000_000


def _panel() -> pd.DataFrame:
    p = pd.read_parquet(HERE / "panel.parquet")
    p["T"] = pd.to_datetime(p["T"], utc=True)
    return p


def _premium_grid() -> pd.DataFrame:
    cb = pd.read_parquet(CB).copy()
    cb["t"] = pd.to_datetime(cb["open_time"], utc=True)
    cb = cb[cb["t"] < CUTOFF][["t", "close"]].rename(columns={"close": "cb"})
    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h = h[h["sym"] == "BTCUSDT"].copy()
    h["t"] = pd.to_datetime(h["t"], utc=True)
    h = h[h["t"] < CUTOFF][["t", "close"]].rename(columns={"close": "bin"})
    g = pd.merge(cb, h, on="t", how="inner").sort_values("t").reset_index(drop=True)
    g["prem"] = g["cb"] / g["bin"] - 1
    g["mean24"] = g["prem"].rolling(24, min_periods=20).mean()
    r = g["mean24"].rolling(2160, min_periods=1728)
    g["cbprem_z90"] = (g["mean24"] - r.mean().shift(1)) / r.std(ddof=1).shift(1)
    g["end"] = g["t"] + pd.Timedelta(hours=1)
    return g


def test_books_match_bearshort():
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


def test_premium_causal():
    p = _panel()
    prem = _premium_grid()
    ends_ns = prem["end"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    vals = prem["cbprem_z90"].to_numpy(float)
    grid = p["T"].drop_duplicates().sort_values().to_numpy()
    rng = np.random.default_rng(60)
    sample = rng.choice(np.arange(700, len(grid)), size=5, replace=False)
    for i in sorted(sample):
        T = pd.Timestamp(grid[i]).tz_convert("UTC")
        Tns = int(T.value)
        # Strict truncation: only rows with end <= T - 1s are usable.
        trunc = prem[prem["end"] <= T - pd.Timedelta(seconds=1)]
        expect = float(trunc["cbprem_z90"].iloc[-1]) if len(trunc) else np.nan
        # Same lookup as compute_cbpremium.asof_z.
        ii = int(np.searchsorted(ends_ns, Tns - NS, side="left") - 1)
        got_lookup = float(vals[ii]) if ii >= 0 else np.nan
        if np.isnan(expect):
            assert np.isnan(got_lookup)
        else:
            assert got_lookup == expect or np.isclose(got_lookup, expect, equal_nan=True)
        got = float(p[p["T"] == T].iloc[0]["z"])
        if np.isnan(expect):
            assert np.isnan(got)
        else:
            assert np.isclose(got, expect, equal_nan=True), f"z mismatch at {T}"
    # NaN-z rows are never tilted; shorts/flats bit-identical; tilted longs exact.
    z = p["z"].to_numpy(float)
    wb = p["w_base"].to_numpy(float)
    wru = p["w_rule"].to_numpy(float)
    mult = p["mult"].to_numpy(float)
    nan_m = ~np.isfinite(z)
    assert np.all(wru[nan_m] == wb[nan_m])
    assert np.all(wru[wb < 0] == wb[wb < 0])
    assert np.all(wru[wb == 0] == 0.0)
    pos = wb > 0
    up = pos & np.isfinite(z) & (z > 1.0)
    down = pos & np.isfinite(z) & (z < -1.0)
    flat = pos & ~(up | down)
    assert np.all(wru[up] == 1.15 * wb[up])
    assert np.all(wru[down] == 0.85 * wb[down])
    assert np.all(wru[flat] == wb[flat])
    assert np.all(mult[up] == 1.15)
    assert np.all(mult[down] == 0.85)
    # mult is a bar-level signal (same for all syms in the bar): it depends
    # only on z, while the tilt application is additionally gated by w_base>0.
    assert np.all(mult[np.isfinite(z) & (z > 1.0)] == 1.15)
    assert np.all(mult[np.isfinite(z) & (z < -1.0)] == 0.85)
    assert np.all(mult[nan_m | ((z >= -1.0) & (z <= 1.0))] == 1.0)
    tilted = p["tilted"].to_numpy(bool)
    assert np.all(tilted == (up | down))


def test_bear_first():
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
    # RULE never touches shorts: rule shorts equal base shorts everywhere.
    wru = p["w_rule"].to_numpy(float)
    neg = wb < 0
    assert np.all(wru[neg] == wb[neg])


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
    # Long-leg membership fixed by base sign in results.json.
    for k, y in enumerate(res["years"]):
        m = (p["T"] >= bounds[k]) & (p["T"] < bounds[k + 1])
        sub = p[m & (p["w_base"] > 0)]
        assert round(float(sub["pnl_base"].sum()), 6) == y["long_pnl_base"]
        assert round(float(sub["pnl_rule"].sum()), 6) == y["long_pnl_rule"]
        assert round(float(p[m]["pnl_base"].sum()), 6) == y["book_pnl_base"]
        assert round(float(p[m]["pnl_rule"].sum()), 6) == y["book_pnl_rule"]
    assert res["decision"]["pnl_higher_count"] == "5/5"
    assert res["decision"]["dd_not_worse_count"] == "2/5"
    assert res["decision"]["promising"] is False
