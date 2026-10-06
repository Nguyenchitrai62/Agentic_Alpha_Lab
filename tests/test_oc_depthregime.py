"""Tests for oc_depthregime: diagnostic regime-split integrity (no simulation).

Fast checks only: file presence, PLAN-before-results, synthetic pairing/math,
year bucketing, regime causality, and results.json consistency vs oc_contrib.
"""
import importlib.util
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ME = ROOT / "research/tournament/oc_depthregime"
KPI = ROOT / "research/tournament/oc_kpi"
CONTRIB = ROOT / "research/tournament/oc_contrib"


def _load():
    spec = importlib.util.spec_from_file_location("oc_depthregime_mod", ME / "analyze_depthregime.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _res():
    return json.loads((ME / "results.json").read_text())


def test_files_present():
    for f in ("PLAN.md", "analyze_depthregime.py", "results.json", "REPORT.md"):
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


def test_pair_rungs_fifo_math():
    a = _load()
    ev = pd.DataFrame([
        dict(t="2022-01-01 00:01:00+00:00", symbol="BTCUSDT", kind="rung_fill",
             side="buy", price=100.0, weight=0.10, rung=2.5, ret=float("nan")),
        dict(t="2022-01-01 00:02:00+00:00", symbol="BTCUSDT", kind="rung_tp",
             side="sell", price=101.0, weight=0.10, rung=float("nan"), ret=0.01),
        dict(t="2022-01-01 00:03:00+00:00", symbol="BTCUSDT", kind="rung_fill",
             side="buy", price=100.0, weight=0.20, rung=5.0, ret=float("nan")),
        dict(t="2022-01-01 00:04:00+00:00", symbol="BTCUSDT", kind="rung_sl",
             side="sell", price=90.0, weight=0.20, rung=float("nan"), ret=-0.10),
    ])
    ev["t"] = pd.to_datetime(ev["t"], utc=True)
    pairs, unpaired, left = a.pair_rungs(ev)
    assert unpaired == 0 and left == 0 and len(pairs) == 2
    assert pairs[0]["depth"] == 2.5 and abs(pairs[0]["pnl"] - 0.001) < 1e-12
    assert pairs[1]["depth"] == 5.0 and abs(pairs[1]["pnl"] + 0.02) < 1e-12


def test_floor_h4():
    a = _load()
    assert a.floor_h4(pd.Timestamp("2022-03-04 05:37:00+00:00")) == pd.Timestamp("2022-03-04 04:00:00+00:00")
    assert a.floor_h4(pd.Timestamp("2022-03-04 00:00:00+00:00")) == pd.Timestamp("2022-03-04 00:00:00+00:00")


def test_regime_causal_truncate():
    import numpy as np
    hourly = pd.read_parquet(ROOT / "research/tournament/ext/hourly_ext.parquet", columns=["t", "open", "sym"])
    hourly["t"] = pd.to_datetime(hourly["t"], utc=True)
    r = _res()
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


def test_nevt_causal():
    # synthetic fills: future fills excluded, own coin excluded, 60min+old excluded
    fills = [
        (pd.Timestamp("2022-01-01 10:00:00+00:00"), "BTCUSDT"),
        (pd.Timestamp("2022-01-01 10:30:00+00:00"), "ETHUSDT"),
        (pd.Timestamp("2022-01-01 10:00:00+00:00"), "SOLUSDT"),
        (pd.Timestamp("2022-01-01 12:00:00+00:00"), "BNBUSDT"),  # future
        (pd.Timestamp("2022-01-01 08:00:00+00:00"), "XRPUSDT"),  # too old
    ]
    from bisect import bisect_left
    per = {}
    for c in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"):
        per[c] = sorted(t for t, cc in fills if cc == c)
    t = pd.Timestamp("2022-01-01 10:30:00+00:00")
    lo = t - pd.Timedelta(minutes=60)
    n = 0
    for c in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"):
        if c == "ETHUSDT":
            continue
        arr = per[c]
        j = bisect_left(arr, lo)
        if j < len(arr) and arr[j] <= t:
            n += 1
    assert n == 2  # BTC + SOL only


def test_consistency():
    r = _res()
    c = json.loads((CONTRIB / "results.json").read_text())
    assert r["checks"]["n_rungs"] == c["pooled"]["n_rungs"] == 21389
    assert r["checks"]["unpaired_exits"] == 0
    assert r["checks"]["unknown_btc30"] == 0 and r["checks"]["unknown_sigma"] == 0
    # depth-group totals replicate oc_contrib exactly
    by_d = c["by_depth"]["pooled"]
    deep_ref = by_d["4.0"]["pnl_mix_pct"] + by_d["5.0"]["pnl_mix_pct"]
    sh_ref = by_d["2.5"]["pnl_mix_pct"] + by_d["3.0"]["pnl_mix_pct"] + by_d["3.5"]["pnl_mix_pct"]
    assert abs(r["totals"]["pooled"]["deep"]["pnl_mix_pct"] - deep_ref) < 1e-9
    assert abs(r["totals"]["pooled"]["shallow"]["pnl_mix_pct"] - sh_ref) < 1e-9
    # per-dimension per-year n sums to group totals; pooled = sum of years
    for dim in ("bear", "btc30", "sigma_terc", "n_evt", "hour", "exit"):
        for g in ("deep", "shallow"):
            for y in range(5):
                tot = r["totals"][str(y)][g]["n"]
                assert sum(v["n"] for v in r["tables"][dim][str(y)][g].values()) == tot, (dim, y, g)
            ptot = r["totals"]["pooled"][g]["n"]
            assert sum(v["n"] for v in r["tables"][dim]["pooled"][g].values()) == ptot, (dim, g)
    # exit win rates are degenerate by construction
    assert abs(r["tables"]["exit"]["pooled"]["deep"]["rung_tp"]["win"] - 1.0) < 1e-12
    assert abs(r["tables"]["exit"]["pooled"]["deep"]["rung_sl"]["win"] - 0.0) < 1e-12
    # deep_sign counts match tables
    for dim, vals in (("bear", ["bear", "bull"]), ("n_evt", ["n0", "n1", "n2p"])):
        for v in vals:
            s = [r["tables"][dim][str(y)]["deep"][v]["pnl_mix_pct"] for y in range(5)]
            assert r["deep_sign"][dim][v]["yearly_deep_mix_pct"] == s
