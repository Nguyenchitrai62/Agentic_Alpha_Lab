"""Causality + accounting tests for oc_corrbudget (no outcome tuning here)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "research" / "tournament" / "oc_corrbudget" / "results.json"


def _results():
    return json.loads(RES.read_text())


def test_assign_buckets_boundaries():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "acb", ROOT / "research" / "tournament" / "oc_corrbudget" / "analyze_corrbudget.py")
    acb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acb)
    s = pd.Series([0.1, 0.5, 0.6, 0.9])
    b = acb.assign_buckets(s, 0.5, 0.6)
    assert list(b) == ["lo", "lo", "mid", "hi"]


def test_scaler_pass_logic_shape():
    r = _results()
    for y in r["years"]:
        assert y["S_base"] > 0  # retention defined every year here
        assert 0.0 < y["retention"] < 1.0
        # scaler always shrinks the worst loss but always cuts >10%: never passes
        assert y["W_scaled_bps"] > y["W_base_bps"]
        assert y["scaler_pass"] is False


def test_sequential_training_grows_by_prior_year_days():
    """n_train[k+1] - n_train[k] == n_days[k]: cut-offs use strictly previous days."""
    r = _results()
    ys = r["years"]
    for k in range(4):
        assert ys[k + 1]["terc"]["n_train"] - ys[k]["terc"]["n_train"] == ys[k]["n_days"]


def test_loyo_training_is_complement():
    """LOYO n_train[h] == total 5y fill-days minus held-out days: no held-out day used."""
    r = _results()
    total = sum(y["n_days"] for y in r["years"])
    for y, l in zip(r["years"], r["loyo"]):
        assert l["n_train"] == total - y["n_days"]
        assert l["heldout"] == y["anchor"]


def test_decision_counts_match():
    r = _results()
    e1_seq = sum(1 for y in r["years"] if y["terc"]["e1"] is True)
    e1_loyo = sum(1 for l in r["loyo"] if l["e1"] is True)
    n_scale = sum(1 for y in r["years"] if y["scaler_pass"])
    assert r["decision"]["e1_sequential"] == f"{e1_seq}/5" == "1/5"
    assert r["decision"]["e1_loyo"] == f"{e1_loyo}/5" == "0/5"
    assert r["decision"]["scaler_pass"] == f"{n_scale}/5" == "0/5"
    assert r["decision"]["promising"] is False


def test_T_and_bounds():
    f = pd.read_parquet(ROOT / "research" / "tournament" / "ext" / "fills_U_ext.parquet",
                        columns=["t_fill", "f"])
    T = f["t_fill"] - pd.to_timedelta(f["f"], unit="min")
    assert bool((T < pd.Timestamp("2026-09-24", tz="UTC")).all())
    r = _results()
    assert r["meta"]["T_max"] < "2026-09-24"
    assert r["meta"]["c_span"][1] <= "2026-09-23 00:00:00+00:00"


def test_corr_causal_truncate():
    """c(D) from hourly truncated to END < D equals the full-panel c(D)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "acb", ROOT / "research" / "tournament" / "oc_corrbudget" / "analyze_corrbudget.py")
    acb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acb)
    rng = np.random.default_rng(7)
    base = pd.Timestamp("2021-01-01", tz="UTC")
    hours = pd.date_range(base - pd.Timedelta(days=40), base + pd.Timedelta(days=10),
                          freq="h", tz="UTC")
    rows = []
    for sym in acb.MAJORS:
        px = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(hours))))
        for t, c in zip(hours, px):
            rows.append({"t": t, "close": float(c), "sym": sym})
    hm = pd.DataFrame(rows)
    full = acb.daily_corr(hm).set_index("D")["c"]
    for D in [base, base + pd.Timedelta(days=3), base + pd.Timedelta(days=9)]:
        trunc = hm[hm["t"] + pd.Timedelta(hours=1) < D].copy()
        part = acb.daily_corr(trunc).set_index("D")["c"]
        a, b = full.loc[D], part.loc[D]
        if np.isnan(a):
            assert np.isnan(b)
        else:
            assert abs(a - b) < 1e-12
