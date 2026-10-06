"""Tests for oc_basisbook (PLAN-pinned causality + alignment)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_basisbook"
CACHE = ROOT / "artifacts/research/engine_real"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
POOL_START = pd.Timestamp("2020-08-01", tz="UTC")
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)


def _panel() -> pd.DataFrame:
    p = pd.read_parquet(HERE / "panel.parquet")
    p["T"] = pd.to_datetime(p["T"], utc=True)
    return p


def _mod():
    spec = importlib.util.spec_from_file_location(
        "oc_basisbook_mod", HERE / "compute_basisbook.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def test_basis_causal():
    p = _panel()
    mod = _mod()
    q = pd.read_parquet(CACHE / "qbasis_features_4h.parquet")
    q["close_time"] = pd.to_datetime(q["close_time"], utc=True)
    btc = q[q["sym"] == "BTCUSDT"].sort_values("close_time").reset_index(drop=True)
    btc = btc[btc["close_time"] < CUTOFF]
    ct = btc["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    qb = btc["qb_front"].to_numpy(float)
    grid = p["T"].drop_duplicates().sort_values().to_numpy()
    rng = np.random.default_rng(61)
    sample = rng.choice(np.arange(100, len(grid)), size=5, replace=False)
    for i in sorted(sample):
        T = pd.Timestamp(grid[i]).tz_convert("UTC")
        Tns = T.to_numpy().astype("datetime64[ns]").astype(np.int64)
        # Truncate source to strictly-before-T (and strictly-before-T-7d leg).
        keep = btc["close_time"] < T
        t2 = btc[keep]
        ct_t = t2["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
        qb_t = t2["qb_front"].to_numpy(float)
        got_trunc = mod.mom_for_times(np.array([Tns]), ct_t, qb_t)[0]
        got_full = mod.mom_for_times(np.array([Tns]), ct, qb)[0]
        assert (np.isnan(got_trunc) and np.isnan(got_full)) or got_trunc == got_full
        stored = float(p[p["T"] == T].iloc[0]["mom"])
        assert (np.isnan(stored) and np.isnan(got_full)) or stored == got_full
        # No used bar at/after its bound.
        used_now = ct[ct < Tns]
        used_lag = ct[ct < Tns - mod.LAG7]
        assert len(used_now) == 0 or used_now.max() < Tns
        assert len(used_lag) == 0 or used_lag.max() < Tns - mod.LAG7
    # Synthetic strict-< semantics: bar ending exactly at T (or T-7d) unused.
    day = np.int64(24 * 3600 * 1_000_000_000)
    T0 = np.int64(1_700_000_000_000_000_000)
    ct_s = np.array([T0 - 8 * day, T0 - 7 * day, T0 - 4 * day, T0 - 1 * day,
                     T0, T0 + 4 * day])
    qb_s = np.array([0.10, 0.20, 0.30, 0.40, 0.50, 0.60])
    # basis(T0) = last ct < T0 = 0.40; basis(T0-7d) = last ct < T0-7d = 0.10
    b = mod.basis_at(np.array([T0]), ct_s, qb_s)[0]
    assert b == 0.40
    mval = mod.mom_for_times(np.array([T0]), ct_s, qb_s)[0]
    assert abs(mval - (0.40 - 0.10)) < 1e-12
    # NaN iff either leg NaN (literal, no fill-forward).
    qb_n = qb_s.copy()
    qb_n[3] = np.nan
    assert np.isnan(mod.mom_for_times(np.array([T0]), ct_s, qb_n)[0])
    # NaN-mom rows are never flagged / never scaled.
    assert p[p["mom"].isna()]["flagged"].sum() == 0
    assert p[p["mom"].isna()]["scaled"].sum() == 0


def test_cutoffs_causal():
    p = _panel()
    res = json.loads((HERE / "results.json").read_text())
    mod = _mod()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    q = pd.read_parquet(CACHE / "qbasis_features_4h.parquet")
    q["close_time"] = pd.to_datetime(q["close_time"], utc=True)
    btc = q[q["sym"] == "BTCUSDT"].sort_values("close_time").reset_index(drop=True)
    btc = btc[btc["close_time"] < CUTOFF]
    ct = btc["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    qb = btc["qb_front"].to_numpy(float)
    bounds = ANCHORS + [LAST_BOUND]
    for k, a0 in enumerate(ANCHORS):
        pool_times = opens_full.index[
            (opens_full.index >= POOL_START) & (opens_full.index < a0)].sort_values()
        assert (pool_times < a0).all()
        pns = pool_times.to_numpy(dtype="datetime64[ns]").astype(np.int64)
        mom_pool = mod.mom_for_times(pns, ct, qb)
        mom_pool = mom_pool[np.isfinite(mom_pool)]
        assert len(mom_pool) >= 100
        expect = float(np.quantile(mom_pool, 0.2))
        assert abs(expect - res["years"][k]["p20"]) < 1e-6  # results.json rounds p20 to 6dp
        assert res["years"][k]["n_train"] == len(mom_pool)
        # Flagged rows in year k are exactly finite-mom bars below p20.
        m = (p["T"] >= bounds[k]) & (p["T"] < bounds[k + 1])
        sub = p[m].drop_duplicates("T")
        exp_flag = sub["mom"].notna() & (sub["mom"] < expect)
        assert (sub["flagged"].to_numpy(bool) == exp_flag.to_numpy()).all()
    # Scaling hits exactly the flagged long-base rows.
    wb = p["w_base"].to_numpy(float)
    wru = p["w_rule"].to_numpy(float)
    fl = p["flagged"].to_numpy(bool)
    pos = wb > 0
    assert np.all(wru[pos & fl] == 0.5 * wb[pos & fl])
    assert np.all(wru[pos & ~fl] == wb[pos & ~fl])
    assert np.all(wru[~pos] == wb[~pos])
    assert (p["scaled"].to_numpy(bool) == (pos & fl)).all()


def test_grid_bounds():
    p = _panel()
    res = json.loads((HERE / "results.json").read_text())
    assert (p["T"] < CUTOFF).all()
    assert (p["T"] >= ANCHORS[0]).all()
    grid = p["T"].drop_duplicates().sort_values()
    bounds = ANCHORS + [LAST_BOUND]
    total = 0
    for k in range(5):
        m = (grid >= bounds[k]) & (grid < bounds[k + 1])
        total += int(m.sum())
    assert total == len(grid)
    assert p["pnl_base"].notna().all() and p["pnl_rule"].notna().all()
    # BASE = v410: bear-row longs exactly halved in both paths; shorts untouched.
    bear = p["bear"].to_numpy(bool)
    wr = p["w_raw"].to_numpy(float)
    wb = p["w_base"].to_numpy(float)
    assert np.all(wb[(wr < 0)] == wr[(wr < 0)])
    pos = wr > 0
    assert np.all(wb[pos & bear] == 0.5 * wr[pos & bear])
    assert np.all(wb[pos & ~bear] == wr[pos & ~bear])
    # Yearly aggregates in results.json match the panel.
    for k, y in enumerate(res["years"]):
        m = (p["T"] >= bounds[k]) & (p["T"] < bounds[k + 1])
        assert round(float(p[m]["pnl_base"].sum()), 6) == y["book_pnl_base"]
        assert round(float(p[m]["pnl_rule"].sum()), 6) == y["book_pnl_rule"]
        sub = p[m & (p["w_base"] > 0)]
        assert round(float(sub["pnl_base"].sum()), 6) == y["long_pnl_base"]
        assert round(float(sub["pnl_rule"].sum()), 6) == y["long_pnl_rule"]
    assert res["decision"]["pnl_kept_count"] == "4/5"
    assert res["decision"]["dd_not_worse_count"] == "3/5"
    assert res["decision"]["promising"] is False


def test_no_1m():
    txt = (HERE / "compute_basisbook.py").read_text()
    for bad in ("btc_intraday_20260924", "majors_intraday_20260924",
                "alts2020_intraday_20260930", "premium_1m"):
        assert bad not in txt
