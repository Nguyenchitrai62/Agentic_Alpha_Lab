"""Tests for oc_idea5 (research/tournament/oc_idea5). Schema, partition, causality."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_idea5"
RES = OC / "results.json"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
CUTOFF = pd.Timestamp("2026-09-24 00:00", tz="UTC")


def _load():
    return json.loads(RES.read_text())


def _mod():
    spec = importlib.util.spec_from_file_location("oc_idea5_compute", OC / "compute_idea5.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_results_exists_and_schema():
    assert RES.exists(), "run research/tournament/oc_idea5/compute_idea5.py first"
    r = _load()
    for k in ("definitions", "symbols", "anchor_years", "n_bars", "premium",
              "variants", "decision", "scale_summary"):
        assert k in r, k
    assert set(r["variants"]) == {"base_60d", "gated_z2"}
    assert r["n_bars"] == 10955
    assert r["symbols"] == SYMS
    for name, v in r["variants"].items():
        assert len(v["per_year"]) == 5, name
        for row in v["per_year"]:
            for k in ("n_bars", "ret", "dd", "sharpe", "worst_day"):
                assert k in row, (name, row)
    assert r["premium"]["z_thresh"] == 2.0


def test_year_partition_covers_grid():
    r = _load()
    ns = [row["n_bars"] for row in r["variants"]["base_60d"]["per_year"]]
    assert ns == [2190, 2190, 2196, 2190, 2189], ns
    assert sum(ns) == r["n_bars"]
    ns2 = [row["n_bars"] for row in r["variants"]["gated_z2"]["per_year"]]
    assert ns2 == ns
    assert pd.Timestamp(r["grid_end"]) < CUTOFF
    assert pd.Timestamp(r["grid_start"]) == ANCHORS[0]


def test_base_matches_oc_bookvol():
    """BASE must reproduce the oc_bookvol V0 row (same books, same math)."""
    r = _load()
    want_ret = [0.304858, 0.64167, 0.967846, 1.15555, 0.817877]
    want_dd = [0.228127, 0.105103, 0.153012, 0.104646, 0.135891]
    rows = r["variants"]["base_60d"]["per_year"]
    for row, wr, wd in zip(rows, want_ret, want_dd):
        assert abs(row["ret"] - wr) < 1e-6, row
        assert abs(row["dd"] - wd) < 1e-6, row


def test_turnover_cost_nonnegative():
    r = _load()
    for name, v in r["variants"].items():
        assert v["total_turnover"] >= 0, name
        assert v["total_cost"] >= 0, name
        assert abs(v["total_cost"] - 0.0005 * v["total_turnover"]) < 5e-4, name


def test_decision_matches_counts():
    r = _load()
    d = r["decision"]
    n_dd = sum(1 for x in d["dDD"] if x is not None and x > 0)
    assert d["dd_pos"] == f"{n_dd}/5"
    assert d["loyo_dd"] == f"{sum(d['loyo_detail'])}/5"
    assert d["tail_pos"] == f"{sum(d['tail_ok'])}/5"
    expect = n_dd >= 4 and sum(d["loyo_detail"]) >= 4 and sum(d["tail_ok"]) >= 4
    assert d["promising"] == expect
    assert d["promising"] is False
    assert d["dd_pos"] == "1/5" and d["loyo_dd"] == "0/5" and d["tail_pos"] == "5/5"


def test_no_1m_refs_and_cutoff_in_source():
    src = (OC / "compute_idea5.py").read_text()
    for bad in ("majors_intraday_20260924", "btc_intraday_20260924", "alts2020_intraday_20260930"):
        assert bad not in src, bad
    assert "2026-09-24" in src  # cutoff filter present


def test_premium_causal_truncate():
    """x/z at sampled T use only hourly bars with START < T."""
    mod = _mod()
    bn = mod.load_hourly_close()
    cb = {c: mod.load_coinbase_close(c) for c in SYMS}
    books = mod.research_books_d2()
    grid = books.index.intersection(
        pd.read_parquet(mod.CACHE / "opens_v154.parquet").dropna(how="all").index).sort_values()
    grid_ext = pd.date_range(grid.min() - pd.Timedelta(days=90), grid.max(), freq="4h", tz="UTC")
    grid_ext = grid_ext.union(grid).sort_values()
    x_ext, z_ext, _ = mod.build_xz(grid_ext, bn, cb)
    rng = np.random.default_rng(11)
    picks = rng.choice(len(grid), 5, replace=False)
    for i in picks:
        T = grid[i]
        # perturb every hourly/Coinbase bar with START >= T -> x/z at T must not move
        bn2 = bn.copy()
        bn2.loc[bn2.index >= T - pd.Timedelta(hours=1)] = np.nan
        cb2 = {}
        for c, s in cb.items():
            if len(s) == 0:
                cb2[c] = s
                continue
            s2 = s.copy()
            s2.loc[s2.index >= T - pd.Timedelta(hours=1)] = np.nan
            cb2[c] = s2
        # full rebuild would NaN the wanted bar itself; instead perturb strictly >= T
        bn3 = bn.copy()
        bn3.loc[bn3.index >= T] = bn3.loc[bn3.index >= T] * 1.5 + 7.0
        cb3 = {}
        for c, s in cb.items():
            if len(s) == 0:
                cb3[c] = s
                continue
            s3 = s.copy()
            m = s3.index >= T
            s3.loc[m] = s3.loc[m] * 1.5 + 7.0
            cb3[c] = s3
        x3, z3, _ = mod.build_xz(grid_ext, bn3, cb3)
        pd.testing.assert_series_equal(x_ext.loc[[T]].iloc[0], x3.loc[[T]].iloc[0], check_names=False)
        a, b = z_ext.loc[T].to_numpy(float), z3.loc[T].to_numpy(float)
        assert (np.isnan(a) == np.isnan(b)).all()
        np.testing.assert_allclose(np.nan_to_num(a), np.nan_to_num(b), atol=1e-12)
        # and no used bar has START >= T: x(T) comes from START=T-1h
        assert (bn.index < CUTOFF).all()


def test_z_window_strictly_before_T():
    """z(T) equals (x(T)-mean/std) over x(S), S in [T-90d, T)."""
    mod = _mod()
    bn = mod.load_hourly_close()
    cb = {c: mod.load_coinbase_close(c) for c in SYMS}
    books = mod.research_books_d2()
    grid = books.index.intersection(
        pd.read_parquet(mod.CACHE / "opens_v154.parquet").dropna(how="all").index).sort_values()
    grid_ext = pd.date_range(grid.min() - pd.Timedelta(days=90), grid.max(), freq="4h", tz="UTC")
    grid_ext = grid_ext.union(grid).sort_values()
    x_ext, z_ext, _ = mod.build_xz(grid_ext, bn, cb)
    T = grid[3000]
    c = "BTCUSDT"
    W = x_ext[c][(x_ext.index < T) & (x_ext.index >= T - pd.Timedelta(days=90))].dropna()
    W = W.iloc[-540:]
    assert len(W) >= 270
    expect = (x_ext[c].loc[T] - W.mean()) / W.std(ddof=1)
    got = z_ext[c].loc[T]
    if np.isnan(expect):
        assert np.isnan(got)
    else:
        assert abs(got - expect) < 1e-9


def test_flip_veto_logic_synthetic():
    mod = _mod()
    idx = pd.date_range("2023-01-01", periods=8, freq="4h", tz="UTC")
    w = pd.DataFrame(0.0, index=idx, columns=SYMS)
    w["BTCUSDT"] = [0.1, 0.1, -0.1, -0.1, 0.1, 0.0, 0.1, -0.2]
    z = pd.DataFrame(0.0, index=idx, columns=SYMS)
    # bar2: flip to short with z=-3 -> veto (short into negative)
    # bar4: flip to long with z=+1.9 -> no veto (below threshold)
    # bar5: 0.1->0.0 is exit, not a flip
    # bar6: 0.0->0.1 is entry, not a flip
    # bar7: flip to short with z=NaN -> no veto
    z["BTCUSDT"] = [0.0, 0.0, -3.0, 0.0, 1.9, 0.0, 5.0, np.nan]
    flip, veto = mod.compute_veto(w, z)
    assert flip["BTCUSDT"].tolist() == [False, False, True, False, True, False, False, True]
    assert veto["BTCUSDT"].tolist()[2] is True or veto["BTCUSDT"].tolist()[2] == True
    assert veto["BTCUSDT"].tolist()[4] == False  # |z|<2
    assert veto["BTCUSDT"].tolist()[5] == False  # exit via zero
    assert veto["BTCUSDT"].tolist()[6] == False  # entry via zero
    assert veto["BTCUSDT"].tolist()[7] == False  # NaN never
    # boundary: exactly +-2.0 does not fire (strict >)
    z2 = pd.DataFrame(0.0, index=idx, columns=SYMS)
    z2["BTCUSDT"] = [0.0, 0.0, -2.0, 0.0, 2.0, 0.0, 0.0, 0.0]
    _, veto2 = mod.compute_veto(w, z2)
    assert veto2["BTCUSDT"].tolist()[2] == False
    assert veto2["BTCUSDT"].tolist()[4] == False
    # BNB never vetoes even on a flip with huge z
    w3 = pd.DataFrame(0.0, index=idx, columns=SYMS)
    w3["BNBUSDT"] = [0.1, -0.1, -0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
    z3 = pd.DataFrame(0.0, index=idx, columns=SYMS)
    z3["BNBUSDT"] = [-9.0, -9.0, 9.0, 9.0, 0.0, 0.0, 0.0, 0.0]
    # BNB z is NaN in practice; force-check the NaN path instead:
    z3n = z3.copy()
    z3n["BNBUSDT"] = np.nan
    _, veto3 = mod.compute_veto(w3, z3n)
    assert not veto3["BNBUSDT"].any()
    # max 1-bar delay: consecutive vetoes -> hold only the first
    ws = pd.DataFrame(0.1, index=idx, columns=SYMS)
    ws["BTCUSDT"] = [0.1, 0.1, -0.3, -0.3, -0.3, -0.3, -0.3, -0.3]
    vv = pd.DataFrame(False, index=idx, columns=SYMS)
    vv["BTCUSDT"] = [False, False, True, True, False, False, False, False]
    gated = mod.apply_gate(ws, vv)
    assert gated["BTCUSDT"].iloc[2] == 0.1  # held
    assert gated["BTCUSDT"].iloc[3] == -0.3  # no stacking: executes despite veto
