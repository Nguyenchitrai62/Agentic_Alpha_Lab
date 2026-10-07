"""Causality + accounting tests for oc_tsmomvar (no outcome tuning here)."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research" / "tournament" / "oc_tsmomvar"
OCM = ROOT / "research" / "tournament" / "oc_tsmom"
sys.path.insert(0, str(OC))
sys.path.insert(0, str(OCM))
import run_var as R

CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")


def _results():
    return json.loads((OC / "results.json").read_text())


def _synth_closes(n=130, seed=3, coins=None):
    coins = coins or ["BTCUSDT", "ETHUSDT"]
    idx = pd.date_range("2021-01-01", periods=n, freq="D", tz="UTC")
    rng = np.random.RandomState(seed)
    lr = 0.002 + 0.02 * rng.randn(n, len(coins))
    px = 100.0 * np.exp(np.cumsum(lr, axis=0))
    return pd.DataFrame(px, index=idx, columns=coins)


def test_signal_uses_only_past_closes():
    # V1 30d rule: perturb C(D0) moves signals only in [D0, D0+30]
    c = _synth_closes(coins=["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    s0, _v0, _p0 = R.compute_positions_30d(c)
    c2 = c.copy()
    d0 = c.index[40]
    c2.loc[d0, "BTCUSDT"] *= 1.5
    s1, _v1, _p1 = R.compute_positions_30d(c2)
    changed = s1["BTCUSDT"] != s0["BTCUSDT"]
    lo, hi = c.index.get_loc(d0), c.index.get_loc(d0) + 30
    assert changed.iloc[:lo].sum() == 0
    assert changed.iloc[hi + 1:].sum() == 0
    assert (s1["ETHUSDT"] == s0["ETHUSDT"]).all()
    assert (s1["SOLUSDT"] == s0["SOLUSDT"]).all()
    # V2 90d rule: perturb moves signals only in [D0, D0+90]
    c = _synth_closes(n=200)
    s0, _v0, _p0 = R.compute_positions_90d_longonly(c)
    c2 = c.copy()
    d0 = c.index[50]
    c2.loc[d0, "BTCUSDT"] *= 1.5
    s1, _v1, _p1 = R.compute_positions_90d_longonly(c2)
    changed = s1["BTCUSDT"] != s0["BTCUSDT"]
    lo, hi = c.index.get_loc(d0), c.index.get_loc(d0) + 90
    assert changed.iloc[:lo].sum() == 0
    assert changed.iloc[hi + 1:].sum() == 0
    assert (s1["ETHUSDT"] == s0["ETHUSDT"]).all()
    # V2 signal identity: +1 iff 90d return > 0 by direct recompute
    d = c.index[150]
    want = 1 if c.loc[d, "BTCUSDT"] / c.loc[d - pd.Timedelta(days=90), "BTCUSDT"] - 1.0 > 0 else 0
    assert s0.loc[d, "BTCUSDT"] == want


def test_data_cap():
    h = pd.read_parquet(ROOT / "research/tournament/ext/hourly_ext.parquet",
                        columns=["t", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    assert bool((h["t"] < CAP).all())
    r = _results()
    assert r["data_cap"] == "2026-09-24T00:00:00Z"
    for _tag, v in r["variants"].items():
        for y in v["years"]:
            assert y["last_day"] < "2026-09-24"
            assert y["first_day"] >= "2021-09-24"


def test_hand_cases():
    idx = pd.date_range("2021-01-01", periods=120, freq="D", tz="UTC")
    # flat closes -> signal 0, vol NaN, position 0 (both rules)
    flat5 = pd.DataFrame(100.0, index=idx, columns=R.V1_COINS)
    s, v, p = R.compute_positions_30d(flat5)
    assert (s == 0).all().all()
    assert v.isna().all().all()
    assert (p == 0.0).all().all()
    flat2 = pd.DataFrame(100.0, index=idx, columns=R.V2_COINS)
    s2, v2, p2 = R.compute_positions_90d_longonly(flat2)
    assert (s2 == 0).all().all()
    assert (p2 == 0.0).all().all()
    assert (p2.to_numpy() >= 0).all()  # long-only

    # 30d vol math by hand
    c = _synth_closes(n=70, coins=R.V1_COINS)
    s, v, p = R.compute_positions_30d(c)
    d = c.index[-1]
    for sym in R.V1_COINS:
        rets = np.log(c[sym].to_numpy()[-30:] / c[sym].to_numpy()[-31:-1])
        hand_vol = float(np.std(rets, ddof=1) * np.sqrt(365))
        assert v.loc[d, sym] == pytest.approx(hand_vol, rel=1e-9)

    # 90d vol math by hand
    c = _synth_closes(n=130, coins=R.V2_COINS)
    s, v, p = R.compute_positions_90d_longonly(c)
    d = c.index[-1]
    for sym in R.V2_COINS:
        rets = np.log(c[sym].to_numpy()[-90:] / c[sym].to_numpy()[-91:-1])
        hand_vol = float(np.std(rets, ddof=1) * np.sqrt(365))
        assert v.loc[d, sym] == pytest.approx(hand_vol, rel=1e-9)
        r90 = c[sym].iloc[-1] / c[sym].iloc[-91] - 1.0
        assert s.loc[d, sym] == (1 if r90 > 0 else 0)
        assert p.loc[d, sym] == pytest.approx((min(0.10 / hand_vol, 1.0) if r90 > 0 else 0.0), rel=1e-9)

    # straight-down 90d trend -> long-only flat 0 (never short)
    dn = pd.DataFrame(index=idx, columns=R.V2_COINS, dtype=float)
    for j, sym in enumerate(R.V2_COINS):
        dn[sym] = 100.0 * np.exp(-0.003 * np.arange(len(idx)) + 0.0001 * j)
    sd, _vd, pdn = R.compute_positions_90d_longonly(dn)
    assert (sd.loc[idx[-1]] == 0).all()
    assert (pdn.loc[idx[-1]] == 0.0).all()

    # sleeve_daily cost/fund math (5-coin book, short pays no funding)
    days = pd.date_range("2021-06-01", periods=4, freq="D", tz="UTC")
    coins = R.V1_COINS
    opens = pd.DataFrame(index=days, columns=coins, dtype=float)
    for sym in coins:
        opens[sym] = [100.0, 102.0, 101.0, 103.0]
    pos = pd.DataFrame(0.0, index=days, columns=coins)
    pos.loc[days[1], "BTCUSDT"] = -0.4
    got = R.sleeve_daily(opens, pos, [days[2]], coins)
    gross = -0.4 * (103.0 / 101.0 - 1.0)
    assert got.loc[days[2], "gross"] == pytest.approx(gross, rel=1e-12)
    assert got.loc[days[2], "cost"] == pytest.approx(0.00055 * 0.4, rel=1e-12)
    assert got.loc[days[2], "fund"] == pytest.approx(0.0, abs=1e-15)

    # unit checks
    assert list(R.equity_from(np.array([0.01, -0.02]))) == pytest.approx([1.01, 0.9898])
    assert R.max_dd(np.array([1.05, 0.95, 1.14])) == pytest.approx(1 - 0.95 / 1.05, rel=1e-9)
    assert R.sharpe_ann(np.array([0.01, 0.01])) == pytest.approx(0.0, abs=1e-15)


def test_v1_parity_with_oc_tsmom_rule():
    """V1 30d code run on BTC/ETH must match oc_tsmom's rule on synthetic data."""
    import run_tsmom as T

    c = _synth_closes(n=70, coins=["BTCUSDT", "ETHUSDT"])
    s_new, v_new, p_new = R.compute_positions_30d(c)
    s_old, v_old, p_old = T.compute_positions(c)
    assert (s_new == s_old).all().all()
    assert np.allclose(v_new.to_numpy(), v_old.to_numpy(), equal_nan=True)
    assert np.allclose(p_new.to_numpy(), p_old.to_numpy())
    # same daily grid as oc_tsmom
    r = _results()
    ref = json.loads((OCM / "results.json").read_text())
    for tag, v in r["variants"].items():
        assert [y["n_days"] for y in v["years"]] == [y["n_days"] for y in ref["years"]]
        for y, yr in zip(v["years"], ref["years"]):
            assert y["days"] == yr["days"]
            assert y["base"]["monthly_pct"] == pytest.approx(yr["base"]["monthly_pct"], abs=1e-9)


def test_recompute():
    r = _results()
    for tag, v in r["variants"].items():
        n_div = n_loyo = 0
        for y in v["years"]:
            rs = np.array(y["r_sleeve"], float)
            rb = np.array(y["r_base"], float)
            st = R.leg_stats(rs, rb)
            assert st["sleeve"]["monthly_pct"] == pytest.approx(y["sleeve"]["monthly_pct"], abs=1e-3)
            assert st["combined"]["monthly_pct"] == pytest.approx(y["combined"]["monthly_pct"], abs=1e-3)
            assert (st["corr_sleeve_base"] or 0) == pytest.approx(y["corr_sleeve_base"] or 0, abs=1e-3)
            assert st["r_comb"] == pytest.approx(y["r_comb"], abs=2e-8)
            assert len(y["days"]) == y["n_days"] == len(rs) == len(rb)
            div = bool(y["sleeve"]["monthly_pct"] > 0 and
                       y["corr_sleeve_base"] is not None and y["corr_sleeve_base"] < 0.15)
            assert y["div_pass"] == div
            n_div += div
        assert v["decision"]["div_pass"] == f"{n_div}/5"
        n_loyo = sum(1 for L in v["loyo_sleeve_sign"]["pools"] if L["sign_match"])
        assert v["loyo_sleeve_sign"]["match"] == f"{n_loyo}/5"
        assert v["decision"]["promising"] == bool(n_div >= 4 and n_loyo >= 4)
    assert r["variants"]["V1_5coin_30d"]["decision"]["promising"] is False
    assert r["variants"]["V2_btceth_90d_longonly"]["decision"]["promising"] is False


def test_base_sanity():
    r = _results()
    assert r["checks"]["max_compound_residual_pp"] < 1e-3
    assert r["checks"]["max_base_monthly_gap_vs_kpi_pp"] < 0.5
    runs = pickle.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2"
                         / "v411" / "v411_runs.pkl").read_bytes())
    assert set(runs) == {0, 1, 2, 3}
    for s in runs:
        assert set(runs[s]["R2B1D17BF"]) == {"t", "eq", "eq_min"}
