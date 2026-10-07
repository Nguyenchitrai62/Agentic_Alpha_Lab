"""Causality + accounting tests for oc_xsrev (no outcome tuning here)."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research" / "tournament" / "oc_xsrev"
sys.path.insert(0, str(OC))
import run_xsrev as R

ANCHORS = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")


def _results():
    return json.loads((OC / "results.json").read_text())


def _synth_closes(n=70, seed=3):
    idx = pd.date_range("2021-01-01", periods=n, freq="D", tz="UTC")
    rng = np.random.RandomState(seed)
    lr = 0.002 + 0.02 * rng.randn(n, 5)
    px = 100.0 * np.exp(np.cumsum(lr, axis=0))
    return pd.DataFrame(px, index=idx, columns=R.MAJORS)


def test_rank_uses_only_past_closes():
    c = _synth_closes()
    r0, w0 = R.compute_weights(c)
    # perturb one close; ret1 may change only at D0 and D0+1
    c2 = c.copy()
    d0 = c.index[40]
    c2.loc[d0, "BTCUSDT"] *= 1.5
    r1, w1 = R.compute_weights(c2)
    for sym in R.MAJORS:
        if sym == "BTCUSDT":
            continue
        # ret1 of untouched coins is bit-identical (NaN-aware: first row NaN)
        pd.testing.assert_series_equal(r1[sym], r0[sym])
        # NOTE: weights of untouched coins MAY change: ranking is
        # cross-sectional, so a BTC move can reshuffle ETH/SOL/BNB/XRP ranks.
    ch_r = (r1["BTCUSDT"] != r0["BTCUSDT"]) & ~(r1["BTCUSDT"].isna() & r0["BTCUSDT"].isna())
    lo = c.index.get_loc(d0)
    # ret1(D0) uses C(D0); ret1(D0+1) uses C(D0) as denominator; nothing else
    assert ch_r.iloc[:lo].sum() == 0
    assert ch_r.iloc[lo + 2:].sum() == 0
    assert ch_r.iloc[lo] and ch_r.iloc[lo + 1]
    # weights w(D) rank ret1(D): change only at D0 and D0+1
    ch_w = (w1 != w0).any(axis=1)
    assert ch_w.iloc[:lo].sum() == 0
    assert ch_w.iloc[lo + 2:].sum() == 0
    # weight held over E depends only on closes <= E-1: truncate and compare
    e = c.index[50]
    _, wtr = R.compute_weights(c.loc[: e - pd.Timedelta(days=1)])
    assert (w0.loc[e - pd.Timedelta(days=1)] == wtr.loc[e - pd.Timedelta(days=1)]).all()
    # ret1 identity by direct recompute
    d = c.index[45]
    want = c.loc[d, "BTCUSDT"] / c.loc[d - pd.Timedelta(days=1), "BTCUSDT"] - 1.0
    assert r0.loc[d, "BTCUSDT"] == pytest.approx(want, rel=1e-12)


def test_data_cap():
    h = pd.read_parquet(ROOT / "research/tournament/ext/hourly_ext.parquet",
                        columns=["t", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    assert bool((h["t"] < CAP).all())
    r = _results()
    assert r["data_cap"] == "2026-09-24T00:00:00Z"
    for y in r["years"]:
        assert y["last_day"] < "2026-09-24"
        assert y["first_day"] >= "2021-09-24"


def test_hand_cases():
    # (i) distinctly ordered 1d returns -> worst-2 long, best-2 short, middle 0
    idx = pd.date_range("2021-01-01", periods=5, freq="D", tz="UTC")
    closes = pd.DataFrame(index=idx, columns=R.MAJORS, dtype=float)
    # day-to-day multipliers on the last step (D=idx[-1] vs prev):
    # BTC worst, ETH 2nd worst, SOL middle, BNB 2nd best, XRP best
    mult = {"BTCUSDT": 0.90, "ETHUSDT": 0.95, "SOLUSDT": 1.00,
            "BNBUSDT": 1.05, "XRPUSDT": 1.10}
    for s in R.MAJORS:
        closes[s] = 100.0
        closes.loc[idx[-1], s] = 100.0 * mult[s]
    r, w = R.compute_weights(closes)
    assert w.loc[idx[-1], "BTCUSDT"] == pytest.approx(0.25)
    assert w.loc[idx[-1], "ETHUSDT"] == pytest.approx(0.25)
    assert w.loc[idx[-1], "SOLUSDT"] == pytest.approx(0.0)
    assert w.loc[idx[-1], "BNBUSDT"] == pytest.approx(-0.25)
    assert w.loc[idx[-1], "XRPUSDT"] == pytest.approx(-0.25)
    # ties broken alphabetically: equal returns -> first two alphabetically long
    closes2 = pd.DataFrame(100.0, index=idx, columns=R.MAJORS)
    closes2.loc[idx[-1]] = 100.0  # all ret1 == 0, tie
    _r2, w2 = R.compute_weights(closes2)
    # ordered alphabetically: BNB, BTC longs; SOL, XRP shorts (ETH middle)
    assert w2.loc[idx[-1], "BNBUSDT"] == pytest.approx(0.25)
    assert w2.loc[idx[-1], "BTCUSDT"] == pytest.approx(0.25)
    assert w2.loc[idx[-1], "SOLUSDT"] == pytest.approx(-0.25)
    assert w2.loc[idx[-1], "XRPUSDT"] == pytest.approx(-0.25)
    assert w2.loc[idx[-1], "ETHUSDT"] == pytest.approx(0.0)

    # (ii) NaN ret1 coin never selected
    closes3 = closes.copy()
    closes3.loc[idx[-1], "SOLUSDT"] = np.nan
    closes3.loc[idx[-2], "SOLUSDT"] = np.nan
    r3, w3 = R.compute_weights(closes3)
    assert np.isnan(r3.loc[idx[-1], "SOLUSDT"])
    assert w3.loc[idx[-1], "SOLUSDT"] == pytest.approx(0.0)

    # (iii) one-day open-to-open math: short-only day, no rebalance ambiguity
    days = pd.date_range("2021-06-01", periods=4, freq="D", tz="UTC")
    opens = pd.DataFrame(index=days, columns=R.MAJORS, dtype=float)
    for s in R.MAJORS:
        opens[s] = 100.0
    opens.loc[days[2], "XRPUSDT"] = 110.0  # held-day open move for the short
    opens.loc[days[3], "XRPUSDT"] = 99.0
    pos = pd.DataFrame(0.0, index=days, columns=R.MAJORS)
    pos.loc[days[1], "XRPUSDT"] = -0.25  # held over days[2]
    pos.loc[days[0]] = 0.0
    # isolate: call with days=[days[2]] so prev (w(E-2)=pos[days[0]]=0)
    got = R.sleeve_daily(opens, pos, [days[2]])
    gross = -0.25 * (99.0 / 110.0 - 1.0)
    assert got.loc[days[2], "gross"] == pytest.approx(gross, rel=1e-12)
    assert got.loc[days[2], "cost"] == pytest.approx(0.00055 * 0.25, rel=1e-12)
    assert got.loc[days[2], "fund"] == pytest.approx(0.0, abs=1e-15)
    assert got.loc[days[2], "r_s"] == pytest.approx(gross - 0.00055 * 0.25, rel=1e-12)

    # (iv) long day deducts exactly 0.0003*pos funding; rebalance pays on delta
    pos2 = pd.DataFrame(0.0, index=days, columns=R.MAJORS)
    pos2.loc[days[0], "BTCUSDT"] = 0.25
    pos2.loc[days[1], "BTCUSDT"] = 0.25
    pos2.loc[days[2], "BTCUSDT"] = -0.25
    for s in R.MAJORS:
        opens[s] = 100.0  # flat opens -> gross 0
    got2 = R.sleeve_daily(opens, pos2, [days[1], days[2], days[3]])
    assert got2.loc[days[1], "cost"] == pytest.approx(0.00055 * 0.25, rel=1e-12)
    assert got2.loc[days[1], "fund"] == pytest.approx(0.0003 * 0.25, rel=1e-12)
    assert got2.loc[days[2], "cost"] == pytest.approx(0.0, abs=1e-15)
    assert got2.loc[days[2], "fund"] == pytest.approx(0.0003 * 0.25, rel=1e-12)
    assert got2.loc[days[3], "cost"] == pytest.approx(0.00055 * 0.5, rel=1e-12)
    assert got2.loc[days[3], "fund"] == pytest.approx(0.0, abs=1e-15)

    # unit checks: equity_from / max_dd / sharpe_ann
    assert list(R.equity_from(np.array([0.01, -0.02]))) == pytest.approx([1.01, 0.9898])
    assert R.max_dd(np.array([1.05, 0.95, 1.14])) == pytest.approx(1 - 0.95 / 1.05, rel=1e-9)
    assert R.max_dd(np.array([1.01, 1.02])) == pytest.approx(0.0, abs=1e-15)
    assert R.sharpe_ann(np.array([0.01, 0.01])) == pytest.approx(0.0, abs=1e-15)


def test_recompute():
    """Stored per-year stats equal independent recomputation from stored series."""
    r = _results()
    n_pos = n_corr = n_dd = 0
    for y in r["years"]:
        rs = np.array(y["r_sleeve"], float)
        rb = np.array(y["r_base"], float)
        st = R.leg_stats(rs, rb)
        assert st["sleeve"]["total_pct"] == pytest.approx(y["sleeve"]["total_pct"], abs=1e-3)
        assert st["sleeve"]["monthly_pct"] == pytest.approx(y["sleeve"]["monthly_pct"], abs=1e-3)
        assert st["sleeve"]["maxDD_pct"] == pytest.approx(y["sleeve"]["maxDD_pct"], abs=1e-2)
        assert st["base"]["monthly_pct"] == pytest.approx(y["base"]["monthly_pct"], abs=1e-3)
        assert st["combined"]["monthly_pct"] == pytest.approx(y["combined"]["monthly_pct"], abs=1e-3)
        assert st["combined"]["maxDD_pct"] == pytest.approx(y["combined"]["maxDD_pct"], abs=1e-2)
        assert (st["corr_sleeve_base"] or 0) == pytest.approx(y["corr_sleeve_base"] or 0, abs=1e-3)
        assert st["pos_pass"] == y["pos_pass"]
        assert st["corr_pass"] == y["corr_pass"]
        assert st["dd_pass"] == y["dd_pass"]
        assert st["r_comb"] == pytest.approx(y["r_comb"], abs=2e-8)
        assert len(y["days"]) == y["n_days"] == len(rs) == len(rb)
        n_pos += st["pos_pass"]
        n_corr += st["corr_pass"]
        n_dd += st["dd_pass"]
    assert r["decision"]["sleeve_positive"] == f"{n_pos}/5" == "0/5"
    assert r["decision"]["corr_below_015"] == f"{n_corr}/5" == "3/5"
    assert r["decision"]["dd_not_worse"] == f"{n_dd}/5" == "0/5"
    assert r["decision"]["promising"] is False
    n_loyo = sum(1 for L in r["loyo_sleeve_pos"]["pools"] if L["pass"])
    assert r["loyo_sleeve_pos"]["match"] == f"{n_loyo}/5" == "0/5"


def test_base_sanity():
    """Year nets compound from stored daily returns; v411 keys exact; kpi match."""
    r = _results()
    assert r["checks"]["max_compound_residual_pp"] < 1e-3
    runs = pickle.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2"
                         / "v411" / "v411_runs.pkl").read_bytes())
    assert set(runs) == {0, 1, 2, 3}
    for s in runs:
        assert set(runs[s]["R2B1D17BF"]) == {"t", "eq", "eq_min"}
    assert r["checks"]["max_base_monthly_gap_vs_kpi_pp"] < 0.05
    for y in r["years"]:
        ref = y["kpi_reference"]
        assert ref is not None
        assert y["base"]["monthly_pct"] == pytest.approx(ref["R"], abs=0.05)
    assert r["checks"]["n_days"] == [y["n_days"] for y in r["years"]]
