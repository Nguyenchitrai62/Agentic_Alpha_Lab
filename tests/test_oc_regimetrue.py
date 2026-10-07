"""Tests for oc_regimetrue: TRUE-pairing regime-split integrity (no simulation).

Fast checks only: file presence, PLAN-before-results, synthetic pairing/math,
year bucketing, regime causality, and results.json consistency vs oc_deepcheck.
"""
import importlib.util
import json
from bisect import bisect_left
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ME = ROOT / "research/tournament/oc_regimetrue"
DEEPCHECK = ROOT / "research/diagnostics/oc_deepcheck/results.json"


def _load():
    spec = importlib.util.spec_from_file_location("oc_regimetrue_mod", ME / "analyze_regimetrue.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _res():
    return json.loads((ME / "results.json").read_text())


def test_files_present():
    for f in ("PLAN.md", "analyze_regimetrue.py", "results.json", "REPORT.md"):
        assert (ME / f).exists(), f


def test_plan_predates_results():
    assert (ME / "PLAN.md").stat().st_mtime <= (ME / "results.json").stat().st_mtime


def test_year_of_boundaries():
    a = _load()
    assert a.year_of("2021-09-24 00:00:00+00:00") == 0
    assert a.year_of("2022-09-23 23:59:00+00:00") == 0
    assert a.year_of("2022-09-24 00:00:00+00:00") == 1
    assert a.year_of("2026-09-23 23:59:00+00:00") == 4
    assert a.year_of("2026-09-24 00:00:00+00:00") is None


def test_true_pairing_math():
    a = _load()
    ev = pd.DataFrame([
        dict(t="2022-01-01 00:01:00+00:00", symbol="BTCUSDT", kind="rung_fill",
             side="buy", price=100.0, weight=0.10, rung=2.5, ret=float("nan")),
        dict(t="2022-01-01 00:02:00+00:00", symbol="BTCUSDT", kind="rung_tp",
             side="sell", price=101.0, weight=0.10, rung=float("nan"), ret=0.01),
        # time inversion: deeper fill later, exits sooner (still adjacent)
        dict(t="2022-01-01 00:03:00+00:00", symbol="BTCUSDT", kind="rung_fill",
             side="buy", price=100.0, weight=0.20, rung=5.0, ret=float("nan")),
        dict(t="2022-01-01 00:04:00+00:00", symbol="BTCUSDT",
             kind="rung_sl", side="sell", price=90.0, weight=0.20, rung=float("nan"), ret=-0.10),
    ])
    ev["t"] = pd.to_datetime(ev["t"], utc=True)
    rows, viol, maxwd = a.pair_true(ev)
    assert viol == 0 and maxwd == 0.0 and len(rows) == 2
    assert rows[0]["depth"] == 2.5 and abs(rows[0]["pnl"] - 0.001) < 1e-12
    assert rows[1]["depth"] == 5.0 and abs(rows[1]["pnl"] + 0.02) < 1e-12
    # mismatch (wrong symbol after fill) counts a violation and skips the fill
    ev2 = pd.DataFrame([
        dict(t="2022-01-01 00:01:00+00:00", symbol="BTCUSDT", kind="rung_fill",
             side="buy", price=100.0, weight=0.10, rung=2.5, ret=float("nan")),
        dict(t="2022-01-01 00:02:00+00:00", symbol="ETHUSDT", kind="rung_tp",
             side="sell", price=101.0, weight=0.10, rung=float("nan"), ret=0.01),
    ])
    ev2["t"] = pd.to_datetime(ev2["t"], utc=True)
    rows2, viol2, _ = a.pair_true(ev2)
    assert viol2 == 1 and len(rows2) == 0


def test_floor_h4():
    a = _load()
    assert a.floor_h4(pd.Timestamp("2022-03-04 05:37:00+00:00")) == pd.Timestamp("2022-03-04 04:00:00+00:00")
    assert a.floor_h4(pd.Timestamp("2022-03-04 00:00:00+00:00")) == pd.Timestamp("2022-03-04 00:00:00+00:00")


def test_regime_causal_truncate():
    import numpy as np
    hourly = pd.read_parquet(ROOT / "research/tournament/ext/hourly_ext.parquet", columns=["t", "open", "sym"])
    hourly["t"] = pd.to_datetime(hourly["t"], utc=True)
    a = _load()
    per4h, btc_open, ma1200 = a.build_4h(hourly)
    rng = np.random.default_rng(7)
    grid = btc_open.index
    picks = rng.choice(np.arange(1300, len(grid) - 200), size=5, replace=False)
    for j in picks:
        t0 = grid[j]
        trunc = hourly[hourly["t"] <= t0]
        p2, b2, m2 = a.build_4h(trunc)
        assert abs(float(p2["BTCUSDT"]["open"].loc[t0]) - float(per4h["BTCUSDT"]["open"].loc[t0])) < 1e-9
        assert abs(float(p2["ETHUSDT"]["sigma"].loc[t0]) - float(per4h["ETHUSDT"]["sigma"].loc[t0])) < 1e-9
        assert abs(float(m2.loc[t0]) - float(ma1200.loc[t0])) < 1e-9 or (
            not np.isfinite(float(m2.loc[t0])) and not np.isfinite(float(ma1200.loc[t0])))
        assert (trunc["t"] > t0).sum() == 0


def test_tercile_walkforward():
    r = _res()
    a = _load()
    hourly = pd.read_parquet(ROOT / "research/tournament/ext/hourly_ext.parquet", columns=["t", "open", "sym"])
    hourly["t"] = pd.to_datetime(hourly["t"], utc=True)
    per4h, _, _ = a.build_4h(hourly)
    for coin in ("BTCUSDT", "XRPUSDT"):
        s = per4h[coin]["sigma"].dropna()
        for k in range(5):
            hist = s[s.index < (a.ANCH[k] - a.EMBARGO)]
            p33, p66 = float(hist.quantile(0.33)), float(hist.quantile(0.66))
            got = r["cutoffs_sigma"][coin][str(k)]
            assert abs(got[0] - p33) < 2e-6 and abs(got[1] - p66) < 2e-6  # stored rounded to 6dp
    # bucket rule on synthetic sigmas vs stored cutoffs
    p33, p66 = r["cutoffs_sigma"]["BTCUSDT"]["0"]
    assert (p33 - 1e-9) <= p33 <= p66
    bucket = lambda sg: "low" if sg <= p33 else ("high" if sg > p66 else "mid")
    assert bucket(p33) == "low" and bucket(p66) == "mid" and bucket(p66 + 1e-9) == "high"


def test_n_causal():
    # same-shift only: other-shift fills never counted; future/own/old excluded
    fills_s0 = [
        (pd.Timestamp("2022-01-01 10:00:00+00:00"), "BTCUSDT"),
        (pd.Timestamp("2022-01-01 10:00:00+00:00"), "SOLUSDT"),
        (pd.Timestamp("2022-01-01 12:00:00+00:00"), "BNBUSDT"),  # future
        (pd.Timestamp("2022-01-01 08:00:00+00:00"), "XRPUSDT"),  # too old
    ]
    fills_s1 = [(pd.Timestamp("2022-01-01 10:20:00+00:00"), "BNBUSDT")]  # other shift
    per = {c: sorted(t for t, cc in fills_s0 if cc == c)
           for c in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")}

    def count(t, sym):
        lo = t - pd.Timedelta(minutes=60)
        n = 0
        for c in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"):
            if c == sym:
                continue
            arr = per[c]
            j = bisect_left(arr, lo)
            if j < len(arr) and arr[j] <= t:
                n += 1
        return n

    t = pd.Timestamp("2022-01-01 10:30:00+00:00")
    assert count(t, "ETHUSDT") == 2  # BTC + SOL only (s1 BNB ignored, future/old out)
    assert count(t, "BTCUSDT") == 1  # SOL only (own coin excluded)


def test_consistency():
    r = _res()
    a = _load()
    dc = json.loads(DEEPCHECK.read_text())["by_depth_fill_year"]["true"]
    assert r["checks"]["n_rungs"] == 21389
    assert r["checks"]["adjacency_violations"] == 0
    assert r["checks"]["max_fill_exit_wdiff"] == 0.0
    assert r["checks"]["outside_anchor_years"] == 0
    assert r["checks"]["unknown_sigma"] == 0
    # per-depth totals replicate oc_deepcheck TRUE tables (n and mix%)
    for y in list(range(5)) + ["pooled"]:
        yy = "pooled" if y == "pooled" else str(y)
        for dd in ("2.5", "3.0", "3.5", "4.0", "5.0"):
            assert r["totals"][str(y)][dd]["n"] == dc[yy][dd]["n"], (y, dd)
            assert abs(r["totals"][str(y)][dd]["pnl_mix_pct"] - dc[yy][dd]["pnl_mix_pct"]) < 1e-9, (y, dd)
    assert r["checks"]["replication_max_abs_mixdiff_vs_deepcheck_true"] == 0.0
    # per-dimension per-year n sums to depth totals; pooled = sum of years
    for dim in ("bear", "sigma_terc", "n"):
        for dd in ("2.5", "3.0", "3.5", "4.0", "5.0"):
            for y in range(5):
                tot = r["totals"][str(y)][dd]["n"]
                assert sum(v["n"] for v in r["tables"][dim][str(y)][dd].values()) == tot, (dim, y, dd)
            ptot = r["totals"]["pooled"][dd]["n"]
            assert sum(v["n"] for v in r["tables"][dim]["pooled"][dd].values()) == ptot, (dim, dd)
            assert ptot == sum(r["totals"][str(y)][dd]["n"] for y in range(5)), (dim, dd)
    assert sum(r["totals"]["pooled"][dd]["n"] for dd in ("2.5", "3.0", "3.5", "4.0", "5.0")) == 21389
    # flags recompute from tables
    for dim in ("bear", "sigma_terc", "n"):
        for dd, gd in r["flags"][dim].items():
            for v, f in gd.items():
                s = [r["tables"][dim][str(y)][dd][v]["pnl_mix_pct"] for y in range(5)]
                assert f["yearly_mix_pct"] == s, (dim, dd, v)
                assert f["n_years_ge0"] == sum(1 for x in s if x >= 0)
                assert f["lose_ge4"] == (sum(1 for x in s if x < 0) >= 4)
                assert f["win_5"] == all(x >= 0 for x in s)
    # exact-n s0 join covers the s0 TRUE pairs (joined + unknown == s0 pairs)
    ev0 = pd.read_parquet(ROOT / "research/tournament/oc_kpi/events_s0.parquet")
    rows0, _, _ = a.pair_true(ev0)
    n0_in = sum(1 for d in rows0 if a.year_of(d["fill_t"]) is not None)
    assert r["checks"]["n_exact_join_s0"] + r["checks"]["n_exact_unknown_s0"] == n0_in == 5466
    assert r["exact_n_s0"]["n_s0_joined"] == r["checks"]["n_exact_join_s0"]
    # no market data at/after 2026-09-24
    assert pd.to_datetime(ev0["t"], utc=True).max() < pd.Timestamp("2026-09-24", tz="UTC")
