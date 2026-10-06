"""Causality + accounting tests for oc_beartp (no outcome tuning here)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research" / "tournament" / "oc_beartp"
sys.path.insert(0, str(OC))
sys.path.insert(0, str(ROOT / "research" / "tournament" / "ext"))
import analyze_beartp as A
import harness5 as H5

ANCHORS = [pd.Timestamp(a, tz="UTC") for a in (
    "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)


def _results():
    return json.loads((OC / "results.json").read_text())


def test_tp_mapping():
    """bear -> TP 0.5 / y0.5, non-bear -> deployed tp/y (synthetic)."""
    bear = np.array([True, False, True, False])
    tp_dep = np.array([1.0, 1.5, 1.0, 0.5])
    y05 = np.array([0.01, 0.02, -0.03, 0.04])
    yd = np.array([0.05, -0.06, 0.07, 0.04])
    tp_new = np.where(bear, 0.5, tp_dep)
    y_new = np.where(bear, y05, yd)
    assert list(tp_new) == [0.5, 1.5, 0.5, 0.5]
    assert list(y_new) == pytest.approx([0.01, -0.06, -0.03, 0.04])
    # NaN-MA maps to non-bear (False) -> deployed values kept.
    assert bool(((pd.Series([1.0]) < pd.Series([np.nan])) & pd.Series([np.nan]).notna()).fillna(False).iloc[0]) is False


def test_decision_counts_match():
    r = _results()
    n_dd = sum(1 for y in r["years"] if y["dd_not_worse"])
    n_sum = sum(1 for y in r["years"] if y["sum_not_lower"])
    assert r["decision"]["dd_not_worse"] == f"{n_dd}/5" == "4/5"
    assert r["decision"]["sum_not_lower"] == f"{n_sum}/5" == "0/5"
    assert r["decision"]["promising"] is False


def test_score_tp_match():
    """Stored per-year S_dep/S_new/gain equal harness5.score_tp recomputation."""
    d = H5.load()
    d["T"] = pd.to_datetime(d["T"], utc=True)
    feats = pd.read_parquet(OC / "features_beartp.parquet")
    key = feats[["T", "sym", "x1", "tp_new"]].drop_duplicates()
    d = d.merge(key, left_on=["T", "sym", "x1"], right_on=["T", "sym", "x1"], how="left")
    is_r2 = d["sym"].isin(MAJORS) & d["k"].isin(R2) & d["size_dep"].notna()
    tp_col = np.full(len(d), np.nan)
    tp_col[is_r2.to_numpy()] = d.loc[is_r2, "tp_new"].to_numpy(float)
    got = H5.score_tp(d, tp_col, name="check")
    r = _results()
    for k, yr in enumerate(got["years"]):
        assert yr["S_dep"] == pytest.approx(r["years"][k]["S_dep"])
        assert yr["S_new"] == pytest.approx(r["years"][k]["S_new"])
        assert yr["gain"] == pytest.approx(r["years"][k]["gain"])


def test_bear_causal_truncate():
    """bear[T] from opens truncated to start <= T equals the stored value."""
    feats = pd.read_parquet(OC / "features_beartp.parquet")
    feats["T"] = pd.to_datetime(feats["T"], utc=True)
    opens = A.load_btc_4h_opens()
    # Sample from the scored universe (size_dep non-NaN: full 1200-bar
    # history exists for every test T, so MA1200 is finite there).
    scored = feats[feats["size_dep"].notna()].drop_duplicates("T").sort_values("T").reset_index(drop=True)
    assert scored["ma1200"].notna().all()
    samp = scored.iloc[[0, len(scored) // 3, len(scored) // 2, -1]]
    for _, row in samp.iterrows():
        T = pd.Timestamp(row["T"]).tz_convert("UTC")
        trunc = opens[opens.index <= T]
        assert (trunc.index <= T).all()
        got = A.bear_from_opens(trunc).loc[T]
        assert bool(got) == bool(row["bear"])
        # stored MA1200 equals the truncated rolling mean at T
        exp_ma = trunc.rolling(1200, min_periods=600).mean().loc[T]
        assert float(exp_ma) == pytest.approx(float(row["ma1200"]), rel=1e-9)


def test_T_and_bounds():
    f = pd.read_parquet(ROOT / "research" / "tournament" / "ext" / "fills_U_ext.parquet",
                        columns=["t_fill", "f"])
    T = pd.to_datetime(f["t_fill"], utc=True) - pd.to_timedelta(f["f"], unit="min")
    assert bool((T < pd.Timestamp("2026-09-24", tz="UTC")).all())
    h = pd.read_parquet(ROOT / "research" / "tournament" / "ext" / "hourly_ext.parquet",
                        columns=["t"])
    assert bool((pd.to_datetime(h["t"], utc=True) < pd.Timestamp("2026-09-24", tz="UTC")).all())
    feats = pd.read_parquet(OC / "features_beartp.parquet")
    Tt = pd.to_datetime(feats["T"], utc=True)
    assert bool((Tt.dt.hour % 4 == 0).all() & (Tt.dt.minute == 0).all())
    assert bool((Tt < pd.Timestamp("2026-09-24", tz="UTC")).all())


def test_universe_counts():
    r = _results()
    assert [y["n"] for y in r["years"]] == [990, 1045, 1330, 989, 1144]
    assert sum(y["n"] for y in r["years"]) == 5498
