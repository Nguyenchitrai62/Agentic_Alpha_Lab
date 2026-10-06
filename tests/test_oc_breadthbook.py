"""Tests for oc_breadthbook (PLAN-pinned causality + alignment)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_breadthbook"
CACHE = ROOT / "artifacts/research/engine_real"
EXT = ROOT / "research/tournament/ext"
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
    rng = np.random.default_rng(63)
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


def _breadth_from_truncated(hourly: pd.DataFrame, T: pd.Timestamp):
    """Recompute breadth/C0/M0 at T using only hourly bars with end <= T."""
    ends = hourly["t"] + pd.Timedelta(hours=1)
    h = hourly[ends <= T]
    c0, m0, above = {}, {}, {}
    e0 = T.normalize()
    for s in SYMS:
        g = h[h["sym"] == s].sort_values("t")
        ser = pd.Series(g["close"].to_numpy(float),
                        index=pd.to_datetime(g["t"] + pd.Timedelta(hours=1), utc=True))
        ser = ser[~ser.index.duplicated(keep="last")].sort_index()
        mid = ser[ser.index.normalize() == ser.index]
        mid.index = mid.index.normalize()
        mid = mid[~mid.index.duplicated(keep="last")].sort_index()
        c = float(mid.get(e0, np.nan)) if e0 in mid.index else float("nan")
        prior = mid[mid.index < e0].tail(200)
        m = float(prior.mean()) if len(prior) == 200 and np.isfinite(prior.to_numpy()).all() else float("nan")
        c0[s], m0[s] = c, m
        above[s] = bool(np.isfinite(c) and np.isfinite(m) and c > m)
    if all(np.isfinite(c0[s]) and np.isfinite(m0[s]) for s in SYMS):
        b = float(np.mean([above[s] for s in SYMS]))
    else:
        b = float("nan")
    on = bool(np.isfinite(b) and b == 1.0)
    return b, on, c0, m0


def test_breadth_causal():
    p = _panel()
    hourly = pd.read_parquet(EXT / "hourly_ext.parquet", columns=["t", "close", "sym"])
    hourly["t"] = pd.to_datetime(hourly["t"], utc=True)
    grid = p["T"].drop_duplicates().sort_values().to_numpy()
    rng = np.random.default_rng(630)
    sample = rng.choice(np.arange(500, len(grid)), size=5, replace=False)
    for i in sorted(sample):
        T = pd.Timestamp(grid[i]).tz_convert("UTC")
        b, on, c0, m0 = _breadth_from_truncated(hourly, T)
        got = p[p["T"] == T].sort_values("sym")
        got_b = float(got.iloc[0]["breadth"])
        got_on = bool(got.iloc[0]["breadth_on"])
        if np.isfinite(b):
            assert abs(got_b - b) < 1e-9, f"breadth mismatch at {T}"
        else:
            assert not np.isfinite(got_b), f"breadth should be NaN at {T}"
        assert got_on == on, f"breadth_on mismatch at {T}"
        assert (got["breadth_on"].to_numpy(bool) == on).all()
        for _, r in got.iterrows():
            s = r["sym"]
            ec, em = c0[s], m0[s]
            if np.isfinite(ec):
                assert abs(float(r["C0"]) - ec) < 1e-9, f"C0 mismatch at {T} {s}"
            else:
                assert not np.isfinite(float(r["C0"])), f"C0 should be NaN at {T} {s}"
            if np.isfinite(em):
                assert abs(float(r["M0"]) - em) < 1e-9, f"M0 mismatch at {T} {s}"
            else:
                assert not np.isfinite(float(r["M0"])), f"M0 should be NaN at {T} {s}"
    # NaN-breadth rows are never gated; shorts unchanged under the rule.
    nanm = ~np.isfinite(p["breadth"].to_numpy(float))
    assert np.all(p["w_rule"].to_numpy(float)[nanm] == p["w_base"].to_numpy(float)[nanm])
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
    # Rule longs exactly 0.75x base where breadth_on, else identical.
    br = p["breadth_on"].to_numpy(bool)
    wb = p["w_base"].to_numpy(float)
    wru = p["w_rule"].to_numpy(float)
    pos = wb > 0
    assert np.all(wru[pos & br] == 0.75 * wb[pos & br])
    assert np.all(wru[pos & ~br] == wb[pos & ~br])
    assert np.all(wru[~pos] == wb[~pos])
