"""Causality + accounting tests for oc_idea7 (no outcome tuning here)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research" / "tournament" / "oc_idea7"
sys.path.insert(0, str(OC))
sys.path.insert(0, str(ROOT / "research" / "tournament" / "ext"))
import analyze_idea7 as A
import harness5 as H5

ANCHORS = [pd.Timestamp(a, tz="UTC") for a in (
    "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)


def _results():
    return json.loads((OC / "results.json").read_text())


def test_multiplier_mapping_boundaries():
    q33, q67 = -0.2, 0.8
    m = A.assign_mult(np.array([np.nan, -5.0, -0.2, 0.0, 0.8, 5.0]), q33, q67)
    assert list(m) == [1.0, 0.75, 0.75, 1.0, 1.0, 1.25]


def test_decision_counts_match():
    r = _results()
    n_gain = sum(1 for y in r["years"] if y["gain_pass"])
    n_loyo = sum(1 for L in r["loyo"] if L["pass"])
    n_tail = sum(1 for y in r["years"] if y["tail_pass"])
    assert r["decision"]["gain_sequential"] == f"{n_gain}/5" == "4/5"
    assert r["decision"]["loyo_gain"] == f"{n_loyo}/5" == "4/5"
    assert r["decision"]["tail_not_worse"] == f"{n_tail}/5" == "2/5"
    assert r["decision"]["promising"] is False


def test_gain_signs_match_harness():
    """Stored per-year gains equal an independent harness5.score recomputation."""
    d = H5.load()
    d["T"] = pd.to_datetime(d["T"], utc=True)
    feats = pd.read_parquet(OC / "features_idea7.parquet")
    key = feats[["T", "sym", "x1", "VRP_z"]].drop_duplicates()
    d = d.merge(key, left_on=["T", "sym", "x1"], right_on=["T", "sym", "x1"], how="left")
    r = _results()
    size = np.full(len(d), np.nan)
    is_r2 = d["sym"].isin(MAJORS) & d["k"].isin(R2) & d["size_dep"].notna()
    for k, a0 in enumerate(ANCHORS):
        cut = r["years"][k]["cutoffs"]
        te = ((d["T"] >= a0) & (d["T"] < a0 + pd.Timedelta(days=365)) & is_r2).to_numpy()
        zv = d["VRP_z"].to_numpy(float)[te]
        m = A.assign_mult(zv, cut["q33"], cut["q67"])
        size[te] = d["size_dep"].to_numpy()[te] * m
    got = H5.score(d, size, name="check")
    for k, yr in enumerate(got["years"]):
        assert yr["gain"] == pytest.approx(r["years"][k]["gain"])
        assert yr["worst_day_new"] == pytest.approx(r["years"][k]["worst_day_new"])


def test_cutoffs_causal():
    """Year-1 + one LOYO cut-off equal strictly-previous-data pool quantiles."""
    feats = pd.read_parquet(OC / "features_idea7.parquet")
    feats["T"] = pd.to_datetime(feats["T"], utc=True)
    r = _results()
    pool = feats[(feats["T"] >= pd.Timestamp("2021-06-30", tz="UTC"))
                 & (feats["T"] < ANCHORS[0])
                 & feats["sym"].isin(MAJORS) & feats["x1"].isin(R2)
                 & np.isfinite(feats["VRP_z"].to_numpy())]
    assert len(pool) == r["years"][0]["cutoffs"]["n_train"] == 113
    assert pool["T"].max() < ANCHORS[0]
    q33, q67 = np.quantile(pool["VRP_z"].to_numpy(), [1 / 3, 2 / 3])
    assert r["years"][0]["cutoffs"]["q33"] == pytest.approx(q33)
    assert r["years"][0]["cutoffs"]["q67"] == pytest.approx(q67)
    # LOYO held-out 2022-23: training = the other four anchor years only
    h = 1
    trm = np.zeros(len(feats), bool)
    for k in range(5):
        if k != h:
            trm |= ((feats["T"] >= ANCHORS[k])
                    & (feats["T"] < ANCHORS[k] + pd.Timedelta(days=365))).to_numpy()
    trm &= (feats["sym"].isin(MAJORS) & feats["x1"].isin(R2)
            & np.isfinite(feats["VRP_z"].to_numpy())).to_numpy()
    held = ((feats["T"] >= ANCHORS[h])
            & (feats["T"] < ANCHORS[h] + pd.Timedelta(days=365))).to_numpy()
    assert not (trm & held).any()
    q33, q67 = np.quantile(feats["VRP_z"].to_numpy()[trm], [1 / 3, 2 / 3])
    assert r["loyo"][h]["q33"] == pytest.approx(q33)
    assert r["loyo"][h]["q67"] == pytest.approx(q67)


def test_vrpz_causal_truncate():
    """VRP_z(T) from panels truncated to end<T equals the stored value."""
    feats = pd.read_parquet(OC / "features_idea7.parquet")
    d_ends, d_cl = A.load_dvol_arrays()
    c_ends, c_cl = A.load_btc_daily()
    maj = feats[feats["sym"].isin(MAJORS) & np.isfinite(feats["VRP_z"].to_numpy())].drop_duplicates("T").sort_values("T")
    samp = maj.iloc[[0, len(maj) // 3, len(maj) // 2, -1]]
    for _, row in samp.iterrows():
        T = pd.Timestamp(row["T"]).tz_convert("UTC")
        Tns = int(T.value)
        assert (d_ends[d_ends < Tns] < Tns).all()
        dt_ = (d_ends[d_ends < Tns], d_cl[d_ends < Tns])
        ct_ = (c_ends[c_ends < Tns], c_cl[c_ends < Tns])
        z, _ = A.vrpz_from_arrays(pd.DatetimeIndex([T]), dt_[0], dt_[1], ct_[0], ct_[1])
        assert np.isfinite(row["VRP_z"])
        assert float(z.iloc[0]) == pytest.approx(float(row["VRP_z"]), rel=1e-9)


def test_T_and_bounds():
    f = pd.read_parquet(ROOT / "research" / "tournament" / "ext" / "fills_U_ext.parquet",
                        columns=["t_fill", "f"])
    T = f["t_fill"] - pd.to_timedelta(f["f"], unit="min")
    assert bool((T < pd.Timestamp("2026-09-24", tz="UTC")).all())
    dv = pd.read_parquet(ROOT / "research" / "tournament" / "oc_dvol" / "dvol_hourly.parquet")
    assert bool((dv["t"] < pd.Timestamp("2026-09-24", tz="UTC")).all())
    h = pd.read_parquet(ROOT / "research" / "tournament" / "ext" / "hourly_ext.parquet",
                        columns=["t"])
    assert bool((h["t"] < pd.Timestamp("2026-09-24", tz="UTC")).all())


def test_universe_counts():
    r = _results()
    assert [y["n"] for y in r["years"]] == [990, 1045, 1330, 989, 1144]
    assert all(y["coverage"] == 1.0 for y in r["years"])
