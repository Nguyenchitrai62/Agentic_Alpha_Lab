"""Causality + accounting tests for oc_weekend (no outcome tuning here)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research" / "tournament" / "oc_weekend"
sys.path.insert(0, str(OC))
sys.path.insert(0, str(ROOT / "research" / "tournament" / "ext"))
import analyze_weekend as A
import harness5 as H5

ANCHORS = [pd.Timestamp(a, tz="UTC") for a in (
    "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)


def _results():
    return json.loads((OC / "results.json").read_text())


def test_weekend_flag_boundaries():
    t = pd.DatetimeIndex([
        "2021-09-24 20:00+00:00",  # Friday -> weekday
        "2021-09-25 00:00+00:00",  # Saturday 00:00 -> weekend
        "2021-09-26 12:00+00:00",  # Sunday -> weekend
        "2021-09-27 00:00+00:00",  # Monday 00:00 -> weekday
        "2021-09-28 04:00+00:00",  # Tuesday -> weekday
    ], tz="UTC")
    assert list(A.is_weekend(t)) == [False, True, True, False, False]
    assert list(A.assign_mult(t)) == [0.90, 1.25, 1.25, 0.90, 0.90]
    # vectorised helper matches row-wise weekday computation
    assert (A.assign_mult(t) == np.where(
        (t.dayofweek == 5) | (t.dayofweek == 6), 1.25, 0.90)).all()


def test_T_and_bounds():
    f = pd.read_parquet(ROOT / "research" / "tournament" / "ext" / "fills_U_ext.parquet",
                        columns=["t_fill", "f", "sym", "x1"])
    T = f["t_fill"] - pd.to_timedelta(f["f"], unit="min")
    assert bool((T < pd.Timestamp("2026-09-24", tz="UTC")).all())
    r = _results()
    assert [y["n"] for y in r["years"]] == [990, 1045, 1330, 989, 1144]
    assert sum(y["n_wknd"] + y["n_wkday"] == y["n"] for y in r["years"]) == 5


def test_decision_counts_match():
    r = _results()
    n_spread = sum(1 for y in r["years"] if y["spread_pass"])
    n_loyo = sum(1 for L in r["loyo"] if L["pass"])
    n_tail = sum(1 for y in r["years"] if y["tail_pass"])
    assert r["decision"]["spread_sequential"] == f"{n_spread}/5" == "2/5"
    assert r["decision"]["loyo_spread"] == f"{n_loyo}/5" == "3/5"
    assert r["decision"]["tail_not_worse"] == f"{n_tail}/5" == "4/5"
    assert r["decision"]["promising"] is False


def test_gain_signs_match_harness():
    """Stored gains/worst-days equal independent harness5.score recomputation."""
    d = H5.load()
    d["T"] = pd.to_datetime(d["T"], utc=True)
    size = np.full(len(d), np.nan)
    is_r2 = d["sym"].isin(MAJORS) & d["k"].isin(R2) & d["size_dep"].notna()
    size[is_r2.to_numpy()] = (
        d["size_dep"].to_numpy()[is_r2.to_numpy()]
        * A.assign_mult(d["T"].to_numpy()[is_r2.to_numpy()]))
    got = H5.score(d, size, name="check")
    r = _results()
    for k, yr in enumerate(got["years"]):
        assert yr["gain"] == pytest.approx(r["years"][k]["gain"])
        assert yr["S_dep"] == pytest.approx(r["years"][k]["S_dep"])
        assert yr["S_new"] == pytest.approx(r["years"][k]["S_new"])
        assert yr["worst_day_dep"] == pytest.approx(r["years"][k]["worst_day_dep"])
        assert yr["worst_day_new"] == pytest.approx(r["years"][k]["worst_day_new"])


def test_spread_recompute():
    """Stored spread/mean/win/n equal independent recomputation from fills."""
    d = H5.load()
    d["T"] = pd.to_datetime(d["T"], utc=True)
    is_r2 = d["sym"].isin(MAJORS) & d["k"].isin(R2) & d["size_dep"].notna()
    dr = d.loc[is_r2].copy()
    w = A.is_weekend(dr["T"])
    r = _results()
    for k, a0 in enumerate(ANCHORS):
        te = ((dr["T"] >= a0) & (dr["T"] < a0 + pd.Timedelta(days=365))).to_numpy()
        y = dr["y_dep"].to_numpy(float)[te]
        ww = w[te]
        yr = r["years"][k]
        assert yr["n"] == int(te.sum())
        assert yr["n_wknd"] == int(ww.sum())
        assert yr["n_wkday"] == int((~ww).sum())
        assert yr["mean_wknd"] == pytest.approx(float(y[ww].mean()), abs=2e-6)
        assert yr["mean_wkday"] == pytest.approx(float(y[~ww].mean()), abs=2e-6)
        assert yr["spread"] == pytest.approx(float(y[ww].mean() - y[~ww].mean()), abs=2e-6)
        assert yr["spread_bps"] == pytest.approx(float(y[ww].mean() - y[~ww].mean()) * 1e4, abs=2e-2)
        assert yr["win_wknd"] == pytest.approx(float((y[ww] > 0).mean()), abs=1e-4)
        assert yr["win_wkday"] == pytest.approx(float((y[~ww] > 0).mean()), abs=1e-4)
        assert yr["spread_pass"] == bool(float(y[ww].mean() - y[~ww].mean()) > 0)


def test_loyo_recompute():
    """Stored LOYO pooled spreads equal other-4-years recomputation."""
    d = H5.load()
    d["T"] = pd.to_datetime(d["T"], utc=True)
    is_r2 = d["sym"].isin(MAJORS) & d["k"].isin(R2) & d["size_dep"].notna()
    dr = d.loc[is_r2].copy().reset_index(drop=True)
    w = A.is_weekend(dr["T"])
    yv = dr["y_dep"].to_numpy(float)
    masks = [((dr["T"] >= a0) & (dr["T"] < a0 + pd.Timedelta(days=365))).to_numpy()
             for a0 in ANCHORS]
    r = _results()
    for hh in range(5):
        tr = np.zeros(len(dr), bool)
        for k in range(5):
            if k != hh:
                tr |= masks[k]
        sp = float(yv[tr & w].mean() - yv[tr & ~w].mean())
        rec = r["loyo"][hh]
        assert rec["spread_pool"] == pytest.approx(sp, abs=2e-6)
        assert rec["pass"] == bool(sp > 0)
        # held-out year excluded from its own pool
        assert not (masks[hh] & tr).any()
