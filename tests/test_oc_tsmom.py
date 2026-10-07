"""Causality + accounting tests for oc_tsmom (no outcome tuning here)."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research" / "tournament" / "oc_tsmom"
sys.path.insert(0, str(OC))
import run_tsmom as R

ANCHORS = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")


def _results():
    return json.loads((OC / "results.json").read_text())


def _synth_closes(n=70, seed=3):
    idx = pd.date_range("2021-01-01", periods=n, freq="D", tz="UTC")
    rng = np.random.RandomState(seed)
    lr = 0.002 + 0.02 * rng.randn(n, 2)
    px = 100.0 * np.exp(np.cumsum(lr, axis=0))
    return pd.DataFrame(px, index=idx, columns=R.COINS)


def test_signal_uses_only_past_closes():
    c = _synth_closes()
    s0, v0, p0 = R.compute_positions(c)
    # perturb one close; signals may change only at D in [D0, D0+30]
    c2 = c.copy()
    d0 = c.index[40]
    c2.loc[d0, "BTCUSDT"] *= 1.5
    s1, _v1, p1 = R.compute_positions(c2)
    changed = s1["BTCUSDT"] != s0["BTCUSDT"]
    lo, hi = c.index.get_loc(d0), c.index.get_loc(d0) + 30
    assert changed.iloc[:lo].sum() == 0
    assert changed.iloc[hi + 1:].sum() == 0
    # ETH untouched
    assert (s1["ETHUSDT"] == s0["ETHUSDT"]).all()
    # position held on day E depends only on closes <= E-1: truncate and compare
    e = c.index[50]
    strunc, _, _ = R.compute_positions(c.loc[: e - pd.Timedelta(days=1)])
    # full-panel signal for holding day e uses signal at e-1
    assert (s0.loc[e - pd.Timedelta(days=1)] == strunc.loc[e - pd.Timedelta(days=1)]).all()
    # signal identity: sign of the 30d return by direct recompute
    d = c.index[45]
    want = np.sign(c.loc[d, "BTCUSDT"] / c.loc[d - pd.Timedelta(days=30), "BTCUSDT"] - 1.0)
    assert s0.loc[d, "BTCUSDT"] == int(want)


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
    # (iii) flat closes -> signal 0, vol NaN, position 0
    idx = pd.date_range("2021-01-01", periods=45, freq="D", tz="UTC")
    flat = pd.DataFrame(100.0, index=idx, columns=R.COINS)
    s, v, p = R.compute_positions(flat)
    assert (s == 0).all().all()
    assert v.isna().all().all()
    assert (p == 0.0).all().all()

    # (i/ii) noisy trend: pos == signal * min(0.10/vol, 1) with hand vol
    c = _synth_closes()
    s, v, p = R.compute_positions(c)
    d = c.index[-1]
    for sym in R.COINS:
        rets = np.log(c[sym].to_numpy()[-30:] / c[sym].to_numpy()[-31:-1])
        hand_vol = float(np.std(rets, ddof=1) * np.sqrt(365))
        assert v.loc[d, sym] == pytest.approx(hand_vol, rel=1e-9)
        want = int(np.sign(c[sym].iloc[-1] / c[sym].iloc[-31] - 1.0)) * min(0.10 / hand_vol, 1.0)
        assert p.loc[d, sym] == pytest.approx(want, rel=1e-9)

    # (v) tiny oscillation + tiny drift -> vol ~0 -> capped at exactly +/-1.0
    # (drift breaks the exact even-lag tie so the signal is nonzero)
    alt = pd.DataFrame(index=idx, columns=R.COINS, dtype=float)
    alt["BTCUSDT"] = [100.0 + 1e-6 * i + 0.001 * (i % 2) for i in range(len(idx))]
    alt["ETHUSDT"] = [50.0 - 1e-6 * i - 0.0005 * (i % 2) for i in range(len(idx))]
    s5, _v5, p5 = R.compute_positions(alt)
    assert s5.loc[idx[-1], "BTCUSDT"] == 1
    assert s5.loc[idx[-1], "ETHUSDT"] == -1
    assert abs(p5.loc[idx[-1], "BTCUSDT"]) == pytest.approx(1.0)
    assert abs(p5.loc[idx[-1], "ETHUSDT"]) == pytest.approx(1.0)

    # (iv) one-day open-to-open math, no prior position: short pays no funding
    days = pd.date_range("2021-06-01", periods=4, freq="D", tz="UTC")
    opens = pd.DataFrame(index=days, columns=R.COINS, dtype=float)
    opens["BTCUSDT"] = [100.0, 102.0, 101.0, 103.0]
    opens["ETHUSDT"] = [50.0, 50.0, 50.0, 50.0]
    pos = pd.DataFrame(0.0, index=days, columns=R.COINS)
    pos.loc[days[1], "BTCUSDT"] = -0.4  # signal at close of day1, held over day2
    got = R.sleeve_daily(opens, pos, [days[2]])
    gross = -0.4 * (103.0 / 101.0 - 1.0)  # O(day2)=101 -> O(day3)=103
    assert got.loc[days[2], "gross"] == pytest.approx(gross, rel=1e-12)
    assert got.loc[days[2], "cost"] == pytest.approx(0.00055 * 0.4, rel=1e-12)
    assert got.loc[days[2], "fund"] == pytest.approx(0.0, abs=1e-15)
    assert got.loc[days[2], "r_s"] == pytest.approx(gross - 0.00055 * 0.4, rel=1e-12)

    # (v) long day deducts exactly 0.0003*pos funding; rebalance pays on delta
    pos2 = pd.DataFrame(0.0, index=days, columns=R.COINS)
    pos2.loc[days[0], "BTCUSDT"] = 0.5
    pos2.loc[days[1], "BTCUSDT"] = 0.5
    pos2.loc[days[2], "BTCUSDT"] = 0.2
    got2 = R.sleeve_daily(opens, pos2, [days[1], days[2], days[3]])
    # day1: fresh entry 0 -> 0.5, held from O(day1)
    assert got2.loc[days[1], "cost"] == pytest.approx(0.00055 * 0.5, rel=1e-12)
    assert got2.loc[days[1], "fund"] == pytest.approx(0.0003 * 0.5, rel=1e-12)
    # day2: no change, no cost, funding on 0.5
    assert got2.loc[days[2], "cost"] == pytest.approx(0.0, abs=1e-15)
    assert got2.loc[days[2], "fund"] == pytest.approx(0.0003 * 0.5, rel=1e-12)
    # day3: 0.5 -> 0.2 trade, funding on the newly held 0.2
    assert got2.loc[days[3], "cost"] == pytest.approx(0.00055 * 0.3, rel=1e-12)
    assert got2.loc[days[3], "fund"] == pytest.approx(0.0003 * 0.2, rel=1e-12)

    # unit checks: equity_from / max_dd (equity LEVELS, path starts at 1.0) / sharpe_ann
    assert list(R.equity_from(np.array([0.01, -0.02]))) == pytest.approx([1.01, 0.9898])
    assert R.max_dd(np.array([1.05, 0.95, 1.14])) == pytest.approx(1 - 0.95 / 1.05, rel=1e-9)
    assert R.max_dd(np.array([1.01, 1.02])) == pytest.approx(0.0, abs=1e-15)
    assert R.sharpe_ann(np.array([0.01, 0.01])) == pytest.approx(0.0, abs=1e-15)


def test_recompute():
    """Stored per-year stats equal independent recomputation from stored series."""
    r = _results()
    n_ret = n_dd = 0
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
        assert st["ret_pass"] == y["ret_pass"]
        assert st["dd_pass"] == y["dd_pass"]
        assert st["r_comb"] == pytest.approx(y["r_comb"], abs=2e-8)
        assert len(y["days"]) == y["n_days"] == len(rs) == len(rb)
        n_ret += st["ret_pass"]
        n_dd += st["dd_pass"]
    assert r["decision"]["ret_higher"] == f"{n_ret}/5" == "5/5"
    assert r["decision"]["dd_not_worse"] == f"{n_dd}/5" == "0/5"
    assert r["decision"]["promising"] is False
    assert r["decision"]["variantA"]["promising"] is False
    n_loyo = sum(1 for L in r["loyo_sleeve_sign"]["pools"] if L["sign_match"])
    assert r["loyo_sleeve_sign"]["match"] == f"{n_loyo}/5"


def test_base_sanity():
    """Year nets compound from stored daily returns; v411 keys exact; kpi match."""
    r = _results()
    assert r["checks"]["max_compound_residual_pp"] < 1e-3
    runs = pickle.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2"
                         / "v411" / "v411_runs.pkl").read_bytes())
    assert set(runs) == {0, 1, 2, 3}
    for s in runs:
        assert set(runs[s]["R2B1D17BF"]) == {"t", "eq", "eq_min"}
    # reset base reproduces the published oc_kpi monthly R (same convention)
    assert r["checks"]["max_base_monthly_gap_vs_kpi_pp"] < 0.05
    for y in r["years"]:
        ref = y["kpi_reference"]
        assert ref is not None
        assert y["base"]["monthly_pct"] == pytest.approx(ref["R"], abs=0.05)
    assert r["checks"]["n_days"] == [y["n_days"] for y in r["years"]]
