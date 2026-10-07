"""Tests for research/tournament/oc_expirycb (pre-registered in PLAN.md)."""
from __future__ import annotations

import calendar
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research" / "tournament" / "oc_expirycb"
OC_EXP = ROOT / "research" / "tournament" / "oc_expirybook"
OC_PREM = ROOT / "research" / "tournament" / "oc_cbpremium"
CACHE = ROOT / "artifacts" / "research" / "engine_real"
CB = ROOT / "data/raw/coinbase_20260925/BTC-USD_1h.parquet"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)
NS = 1_000_000_000


def _results():
    return json.loads((HERE / "results.json").read_text())


def _panel() -> pd.DataFrame:
    p = pd.read_parquet(HERE / "panel.parquet")
    p["T"] = pd.to_datetime(p["T"], utc=True)
    return p


def _expiry(y: int, m: int) -> pd.Timestamp:
    last_day = calendar.monthrange(y, m)[1]
    d = pd.Timestamp(y, m, last_day, tz="UTC")
    back = (d.weekday() - 4) % 7
    return (d - pd.Timedelta(days=int(back))).replace(hour=8, minute=0, second=0)


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


def test_results_exists_and_schema():
    r = _results()
    assert set(r) == {"meta", "years", "full_path", "decision"}
    assert len(r["years"]) == 5
    for y in r["years"]:
        for k in ("n_bars", "n_exp_bars", "exp_share", "coverage_z",
                  "book_pnl_base", "book_pnl_exp", "book_pnl_prem", "book_pnl_both",
                  "worst_week_base", "worst_week_exp", "worst_week_prem", "worst_week_both",
                  "maxDD_base", "maxDD_exp", "maxDD_prem", "maxDD_both",
                  "cost_base", "cost_exp", "cost_prem", "cost_both",
                  "dd_not_worse_vs_base", "pnl_higher_vs_base"):
            assert k in y, k
    assert set(r["full_path"]) == {"base", "exp", "prem", "both"}
    assert set(r["decision"]) == {"dd_not_worse_count", "pnl_higher_count", "promising"}


def test_books_match_parents():
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


def test_expiry_calendar_hand_checked():
    assert _expiry(2025, 9) == pd.Timestamp("2025-09-26 08:00", tz="UTC")
    assert _expiry(2024, 2) == pd.Timestamp("2024-02-23 08:00", tz="UTC")
    assert _expiry(2026, 6) == pd.Timestamp("2026-06-26 08:00", tz="UTC")
    for y in (2021, 2022, 2023, 2024, 2025, 2026):
        for mm in range(1, 13):
            e = _expiry(y, mm)
            assert e.weekday() == 4
            assert (e.hour, e.minute) == (8, 0)
    p = _panel()
    idx = p["T"].drop_duplicates().sort_values().reset_index(drop=True)
    exp_list = [_expiry(y, mm) for y in range(2021, 2027) for mm in range(1, 13)]
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
    assert 0.05 < float(got.mean()) < 0.08


def test_premium_and_bear_causal():
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
        trunc = prem[prem["end"] <= T - pd.Timedelta(seconds=1)]
        expect = float(trunc["cbprem_z90"].iloc[-1]) if len(trunc) else np.nan
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
    # Bear flags match rolling(1200, min 600) on full BTC opens (NaN -> False).
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    btc = opens_full["BTCUSDT"].sort_index()
    ma = btc.rolling(1200, min_periods=600).mean()
    bear_full = (btc < ma).fillna(False)
    for t in p["T"].drop_duplicates().iloc[::997]:
        assert bool(bear_full.reindex([t]).fillna(False).iloc[0]) == bool(
            p.loc[p["T"] == t, "bear"].iloc[0])
    # Weight algebra across the four paths.
    z = p["z"].to_numpy(float)
    bear = p["bear"].to_numpy(bool)
    inexp = p["in_exp"].to_numpy(bool)
    w0 = p["w_raw"].to_numpy(float)
    wb = p["w_base"].to_numpy(float)
    we = p["w_exp"].to_numpy(float)
    wp = p["w_prem"].to_numpy(float)
    wboth = p["w_both"].to_numpy(float)
    mult = p["mult"].to_numpy(float)
    # BASE = v410: longs halved exactly where flagged; shorts/flats unchanged.
    pos0 = w0 > 0
    assert np.all(wb[pos0 & bear] == 0.5 * w0[pos0 & bear])
    assert np.all(wb[pos0 & ~bear] == w0[pos0 & ~bear])
    assert np.all(wb[w0 < 0] == w0[w0 < 0])
    assert np.all(wb[w0 == 0] == 0.0)
    # PREM: NaN-z never tilted; shorts/flats bit-identical; tilted longs exact.
    nan_m = ~np.isfinite(z)
    assert np.all(wp[nan_m] == wb[nan_m])
    assert np.all(wp[wb < 0] == wb[wb < 0])
    assert np.all(wp[wb == 0] == 0.0)
    posb = wb > 0
    up = posb & np.isfinite(z) & (z > 1.0)
    down = posb & np.isfinite(z) & (z < -1.0)
    flat = posb & ~(up | down)
    assert np.all(wp[up] == 1.15 * wb[up])
    assert np.all(wp[down] == 0.85 * wb[down])
    assert np.all(wp[flat] == wb[flat])
    assert np.all(mult[np.isfinite(z) & (z > 1.0)] == 1.15)
    assert np.all(mult[np.isfinite(z) & (z < -1.0)] == 0.85)
    assert np.all(mult[nan_m | ((z >= -1.0) & (z <= 1.0))] == 1.0)
    # EXP: exactly half the base on window bars (both sides), bit-identical off-window.
    assert np.all(we[inexp] == 0.5 * wb[inexp])
    assert np.all(we[~inexp] == wb[~inexp])
    # BOTH: expiry halving applied after the premium tilt.
    assert np.all(wboth[inexp] == 0.5 * wp[inexp])
    assert np.all(wboth[~inexp] == wp[~inexp])


def test_grid_bounds_costs_partition():
    p = _panel()
    r = _results()
    assert bool((p["T"] < CUTOFF).all())
    grid = p["T"].drop_duplicates().sort_values()
    bounds = ANCHORS + [LAST_BOUND]
    total = 0
    for k in range(5):
        m = (grid >= bounds[k]) & (grid < bounds[k + 1])
        total += int(m.sum())
    assert total == len(grid)
    assert r["meta"]["n_bars"] == 10955
    assert sum(y["n_bars"] for y in r["years"]) == r["meta"]["n_bars"]
    for v in ("base", "exp", "prem", "both"):
        assert p[f"pnl_{v}"].notna().all()
        assert np.isfinite(p[f"pnl_{v}"].to_numpy(float)).all()
    for wcol, ccol in (("w_base", "cost_base"), ("w_exp", "cost_exp"),
                       ("w_prem", "cost_prem"), ("w_both", "cost_both")):
        for _s, gg in p.groupby("sym"):
            gg = gg.sort_values("T")
            w = gg[wcol].to_numpy(float)
            to = np.abs(w - np.concatenate([[0.0], w[:-1]]))
            assert np.allclose(gg[ccol].to_numpy(float), 0.0002 * to,
                               rtol=1e-12, atol=1e-18)
    # Per-year sums reproduce results.json on all four variants.
    for k, y in enumerate(r["years"]):
        m = (p["T"] >= bounds[k]) & (p["T"] < bounds[k + 1])
        for v in ("base", "exp", "prem", "both"):
            assert round(float(p[m][f"pnl_{v}"].sum()), 6) == y[f"book_pnl_{v}"]
        assert y["dd_not_worse_vs_base"] == bool(y["maxDD_both"] <= y["maxDD_base"] + 1e-12)
        assert y["pnl_higher_vs_base"] == bool(y["book_pnl_both"] > y["book_pnl_base"])
    dd = sum(1 for y in r["years"] if y["dd_not_worse_vs_base"])
    ph = sum(1 for y in r["years"] if y["pnl_higher_vs_base"])
    assert r["decision"]["dd_not_worse_count"] == f"{dd}/5"
    assert r["decision"]["pnl_higher_count"] == f"{ph}/5"
    assert r["decision"]["promising"] == bool(dd >= 4 and ph >= 4)


def test_singletons_reproduce_parents():
    r = _results()
    re_ = json.loads((OC_EXP / "results.json").read_text())
    rp = json.loads((OC_PREM / "results.json").read_text())
    for y, ye, yp in zip(r["years"], re_["years"], rp["years"]):
        assert y["year"] == ye["year"] == yp["year"]
        assert y["book_pnl_exp"] == ye["book_pnl_rule"]
        assert y["maxDD_exp"] == ye["maxDD_rule"]
        assert y["book_pnl_prem"] == yp["book_pnl_rule"]
        assert y["maxDD_prem"] == yp["maxDD_rule"]
        assert y["book_pnl_base"] == ye["book_pnl_base"] == yp["book_pnl_base"]
        assert y["maxDD_base"] == ye["maxDD_base"] == yp["maxDD_base"]
