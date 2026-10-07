"""Tests for oc_tsmom_official (sleeve exactness + official-metric accounting)."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research" / "tournament" / "oc_tsmom_official"
sys.path.insert(0, str(OC))
import run_official as R

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
    s0, _, _ = R.compute_positions(c)
    c2 = c.copy()
    d0 = c.index[40]
    c2.loc[d0, "BTCUSDT"] *= 1.5
    s1, _, _ = R.compute_positions(c2)
    changed = s1["BTCUSDT"] != s0["BTCUSDT"]
    lo, hi = c.index.get_loc(d0), c.index.get_loc(d0) + 30
    assert changed.iloc[:lo].sum() == 0
    assert changed.iloc[hi + 1:].sum() == 0
    assert (s1["ETHUSDT"] == s0["ETHUSDT"]).all()


def test_hand_cases_and_caps():
    idx = pd.date_range("2021-01-01", periods=45, freq="D", tz="UTC")
    flat = pd.DataFrame(100.0, index=idx, columns=R.COINS)
    s, v, p = R.compute_positions(flat)
    assert (s == 0).all().all()
    assert (p == 0.0).all().all()
    c = _synth_closes()
    s, v, p = R.compute_positions(c)
    d = c.index[-1]
    for sym in R.COINS:
        rets = np.log(c[sym].to_numpy()[-30:] / c[sym].to_numpy()[-31:-1])
        hand_vol = float(np.std(rets, ddof=1) * np.sqrt(365))
        assert v.loc[d, sym] == pytest.approx(hand_vol, rel=1e-9)
        want = int(np.sign(c[sym].iloc[-1] / c[sym].iloc[-31] - 1.0)) * min(0.10 / hand_vol, 1.0)
        assert p.loc[d, sym] == pytest.approx(want, rel=1e-9)
    assert float(p.abs().max().max()) <= 1.0 + 1e-12
    days = pd.date_range("2021-06-01", periods=3, freq="D", tz="UTC")
    opens = pd.DataFrame(index=days, columns=R.COINS, dtype=float)
    opens["BTCUSDT"] = [100.0, 102.0, 101.0]
    opens["ETHUSDT"] = [50.0, 50.0, 50.0]
    pos = pd.DataFrame(0.0, index=days, columns=R.COINS)
    pos.loc[days[1], "BTCUSDT"] = -0.4
    got = R.sleeve_daily(opens, pos, [days[2]])
    assert got.loc[days[2], "fund"] == pytest.approx(0.0, abs=1e-15)
    pos2 = pd.DataFrame(0.0, index=days, columns=R.COINS)
    pos2.loc[days[1], "BTCUSDT"] = 0.5
    got2 = R.sleeve_daily(opens, pos2, [days[2]])
    assert got2.loc[days[2], "fund"] == pytest.approx(0.0003 * 0.5, rel=1e-12)
    # year_reset-style DD helper: peak from eq, trough from eq_min
    assert R.max_dd_from(np.array([1.0, 1.02, 1.01]), np.array([1.0, 1.01, 1.005])) == \
        pytest.approx(1 - 1.005 / 1.02, rel=1e-12)


def test_data_cap_and_sources():
    h = pd.read_parquet(ROOT / "research/tournament/ext/hourly_ext.parquet",
                        columns=["t", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    assert bool((h["t"] < CAP).all())
    r = _results()
    assert r["meta"]["data_cap"] == "2026-09-24T00:00:00Z"
    assert set(r["meta"]["weights"]) == {0.10, 0.25}
    assert len(r["combos"]) == 6  # 3 rows x 2 weights
    for f in ("PLAN.md", "run_official.py", "results.json", "REPORT.md"):
        assert (OC / f).exists(), f
    for label, vdir, pkl, row in R.SPECS:
        runs = pickle.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2"
                             / vdir / pkl).read_bytes())
        assert set(runs) == {0, 1, 2, 3}
        for s in runs:
            assert set(runs[s][row]) == {"t", "eq", "eq_min"}
    src = (OC / "run_official.py").read_text()
    for bad in ("btc_intraday", "majors_intraday", "alts2020", "minutes()",
                "bar_open_ext", "fills_U_ext"):
        assert bad not in src  # no 1m / fill-time data


def test_sleeve_exact_vs_octsmom():
    r = _results()
    assert r["checks"]["max_sleeve_abs_gap_vs_octsmom"] < 1e-6
    assert r["checks"]["max_day_boundary_gap"] < 1e-9
    assert r["checks"]["max_eqmin_above_eq"] <= 0.0
    assert (R.COINS, R.VOL_TARGET, R.POS_CAP, R.TAKER, R.FUND_PER_DAY) == \
        (["BTCUSDT", "ETHUSDT"], 0.10, 1.0, 0.00055, 0.0003)


def test_base_proof_reproduces_official():
    r = _results()
    proof = {b["row"]: b for b in r["base_proof"]}
    assert proof["R2B1D13BF"]["official"]["R"] == pytest.approx(4.971)
    assert proof["R2B1D13BF"]["official"]["DD"] == pytest.approx(14.98)
    for b in r["base_proof"]:
        assert b["match_R"] and b["match_DD"] and b["match_full"]
        for rec, off in zip(b["recomputed"], b["official"]["years"]):
            assert rec["R"] == pytest.approx(off[0])
            assert rec["DD"] == pytest.approx(off[1])


def test_recompute_aggregates_and_stretch():
    r = _results()
    for c in r["combos"]:
        tots = np.array([y["total_pct"] / 100 for y in c["years"]])
        R5 = float(np.prod(1 + tots) ** (1 / 60) - 1) * 100
        assert R5 == pytest.approx(c["R_5y"], abs=1e-3)
        assert min(y["monthly_pct"] for y in c["years"]) == pytest.approx(c["W"], abs=1e-9)
        assert max(y["maxDD_pct"] for y in c["years"]) == pytest.approx(c["DD_maxyearly"], abs=1e-9)
        for y in c["years"]:
            for tot, m in ((y["total_pct"], y["monthly_pct"]),
                           (y["base_total_pct"], y["base_monthly_pct"])):
                assert (1 + tot / 100) ** (1 / 12) - 1 == pytest.approx(m / 100, abs=1e-4)
            assert y["monthly_pct"] - y["base_monthly_pct"] == \
                pytest.approx(y["excess_monthly_pp"], abs=2e-3)
            assert y["maxDD_pct"] - y["base_maxDD_pct"] == \
                pytest.approx(y["dd_delta_pp"], abs=2e-2)
        assert c["stretch"] == bool(c["R_5y"] >= 5.0 and c["DD_maxyearly"] < 15.0)
        assert np.isfinite(c["full_path_dd"])
    # closest combo still misses stretch on the official metric
    best = min(r["combos"], key=lambda c: c["DD_maxyearly"] if c["R_5y"] >= 5.0 else 1e9)
    assert best["row"] == "R2B1D13BF" and best["w"] == 0.10
    assert best["stretch"] is False
    assert r["checks"]["max_monthly_total_residual_pp"] < 1e-2
