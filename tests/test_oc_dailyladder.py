"""Tests for oc_dailyladder (synthetic causality/execution + ledger recompute)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "tournament" / "oc_dailyladder"))
import analyze_dailyladder as A

OUT = ROOT / "research" / "tournament" / "oc_dailyladder"
DEV_END = pd.Timestamp("2026-09-24", tz="UTC")


def test_daily_sigma_handcheck():
    opens = np.array([100.0, 101.0, 102.01, 101.0, 100.0])
    # r = [nan, .01, .01, -.0099.., -.0099..]; sigma[4] over r[0:4]
    sig = A.daily_sigma(opens, win=90, min_n=2)
    assert np.isnan(sig[0]) and np.isnan(sig[1])
    r = np.array([0.01, 0.01, 101.0 / 102.01 - 1, 100.0 / 101.0 - 1])
    assert abs(sig[4] - float(np.std(r, ddof=1))) < 1e-12
    # min_n enforced
    assert np.isnan(A.daily_sigma(opens, win=90, min_n=5)[4])


def test_daily_sigma_causal_truncation():
    rng = np.random.default_rng(7)
    opens = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 300)))
    full = A.daily_sigma(opens)
    for i in (61, 150, 299):
        assert full[i] == A.daily_sigma(opens[: i + 1])[i]


def test_first_fill_strict():
    lv = 100.0
    assert A.first_fill_idx(np.array([100.0, 99.96]), lv) == -1  # at buffer edge: no fill
    assert A.first_fill_idx(np.array([100.0, 99.94]), lv) == 1
    assert A.first_fill_idx(np.array([99.0, 98.0]), lv) == 0


def test_race_tp_stop_time_and_stop_first():
    assert A.race_window(np.array([105.0]), np.array([103.0]), 104.0, 90.0) == (0, "tp")
    assert A.race_window(np.array([103.0]), np.array([89.0]), 104.0, 90.0) == (0, "stop")
    # same bar both triggers -> stop wins
    assert A.race_window(np.array([105.0]), np.array([89.0]), 104.0, 90.0) == (0, "stop")
    # first bar quiet, second TPs
    assert A.race_window(np.array([100.0, 105.0]), np.array([95.0, 95.0]), 104.0, 90.0) == (1, "tp")
    # nothing -> time
    assert A.race_window(np.array([100.0]), np.array([95.0]), 104.0, 90.0) == (None, "time")
    # NaN bars never trigger
    assert A.race_window(np.array([np.nan]), np.array([np.nan]), 104.0, 90.0) == (None, "time")


def test_count_settlements_handcheck():
    F = pd.Timestamp("2024-01-02 10:00", tz="UTC").value
    E = pd.Timestamp("2024-01-03 09:00", tz="UTC").value
    # settlements in (10:00, next-day 09:00]: 16:00, 00:00, 08:00 -> 3
    assert A.count_settlements(F, E) == 3
    assert A.count_settlements(F, F) == 0
    E2 = pd.Timestamp("2024-01-02 16:00", tz="UTC").value
    assert A.count_settlements(F, E2) == 1  # inclusive end


def test_max_dd_handcheck():
    assert A.max_dd(np.array([1.0, -1.0, 2.0])) == 2.0
    assert A.max_dd(np.array([1.0, 2.0])) == 0.0


def test_ledger_bounds_and_coverage():
    tr = pd.read_parquet(OUT / "trades.parquet")
    assert len(tr) == 2132
    D = pd.to_datetime(tr["D"], utc=True)
    X = pd.to_datetime(tr["exit_day"], utc=True)
    assert (D < DEV_END).all() and (X <= DEV_END).all()
    assert (D.dt.floor("D") <= X).all()  # exit not before entry day
    assert np.isfinite(tr["net"].to_numpy(float)).all()
    assert set(tr["exit"].unique()) <= {"tp", "stop", "time"}
    assert set(tr["sym"].unique()) <= {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
    assert set(tr["k"].unique()) <= {1.5, 2.0, 2.5}


def test_ledger_net_accounting():
    tr = pd.read_parquet(OUT / "trades.parquet")
    fee_x = np.where(tr["exit"].to_numpy() == "tp", A.FEE_MAKER, A.FEE_TAKER)
    want = tr["exit_px"] / tr["level"] - 1.0 - A.FEE_MAKER - fee_x - tr["fund"]
    assert np.allclose(tr["net"].to_numpy(float), want.to_numpy(float), atol=1e-12)
    # funding is a nonnegative multiple of 1bp, at most 9 settlements in 3 days
    assert ((tr["fund"] >= 0) & (tr["fund"] <= 9 * A.FUND_8H)).all()
    assert np.allclose((tr["fund"] / A.FUND_8H).round(), tr["fund"] / A.FUND_8H)


def test_decision_recompute_matches_rule():
    res = json.loads((OUT / "results.json").read_text())
    tr = pd.read_parquet(OUT / "trades.parquet")
    tr["D"] = pd.to_datetime(tr["D"], utc=True)
    for y in res["years"]:
        m = (tr["D"] >= y["anchor"]) & (tr["D"] < str(pd.Timestamp(y["anchor"]) + pd.Timedelta(days=365)))
        assert int(m.sum()) == y["n"]
        assert round(float((tr.loc[m, "net"] > 0).mean()), 4) == y["win_rate"]
        assert bool((float(tr.loc[m, "net"].sum()) > 0)) == y["sum_pass"]
        assert abs(float(tr.loc[m, "net"].sum()) - y["sum"]) < 1e-3  # results.json rounds to 4dp
    d = res["decision"]
    assert d["sum_pos"] == f"{sum(1 for y in res['years'] if y['sum_pass'])}/5"
    assert d["corr_lt_0.5"] == (res["corr_full"] < 0.5)
    assert d["dd_not_worse"] == f"{sum(1 for t in res['dd_tests'] if t['pass'])}/5"
    assert d["promising"] == (d["sum_pos"] >= "4/5" and d["corr_lt_0.5"] and d["dd_not_worse"] >= "3/5")


def test_yearly_sums_and_corr_recompute():
    res = json.loads((OUT / "results.json").read_text())
    tr = pd.read_parquet(OUT / "trades.parquet")
    tr["D"] = pd.to_datetime(tr["D"], utc=True)
    tr["exit_day"] = pd.to_datetime(tr["exit_day"], utc=True)
    sys.path.insert(0, str(ROOT / "research" / "tournament" / "ext"))
    import harness5 as H5
    d = H5.load()
    d["T"] = pd.to_datetime(d["T"], utc=True)
    d["t_exit"] = pd.to_datetime(d["t_exit"], utc=True)
    sall, ball = [], []
    for yi, y in enumerate(res["years"]):
        a0 = pd.Timestamp(y["anchor"], tz="UTC")
        m = (tr["D"] >= a0) & (tr["D"] < a0 + pd.Timedelta(days=365))
        te = (d.sym.isin(H5.MAJORS) & d.k.isin(H5.R2) & (d["T"] >= a0)
              & (d["T"] < a0 + pd.Timedelta(days=365)) & d.size_dep.notna())
        assert int(te.sum()) == y["n_4h"]
        assert abs(float(d.loc[te, "y_dep"].sum()) - y["sum_4h"]) < 1e-3  # 4dp rounding
        grid = pd.date_range(a0, a0 + pd.Timedelta(days=368), freq="D", tz="UTC")
        sv = pd.Series(0.0, index=grid).add(
            tr[m].groupby(tr[m]["exit_day"].dt.floor("D"))["net"].sum(), fill_value=0.0
        ).reindex(grid, fill_value=0.0)
        bv = pd.Series(0.0, index=grid).add(
            d[te].groupby(d[te]["t_exit"].dt.floor("D"))["y_dep"].sum(), fill_value=0.0
        ).reindex(grid, fill_value=0.0)
        assert abs(float(sv.sum()) - y["sum"]) < 1e-3
        sall.append(sv)
        ball.append(bv)
    S = pd.concat(sall).groupby(level=0).sum().sort_index()
    B = pd.concat(ball).groupby(level=0).sum().sort_index()
    S, B = S.align(B, join="outer", fill_value=0.0)
    assert abs(float(np.corrcoef(S.to_numpy(), B.to_numpy())[0, 1]) - res["corr_full"]) < 1e-3
