"""Causality + accounting tests for oc_idea8 (no outcome tuning here)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research" / "tournament" / "oc_idea8"
sys.path.insert(0, str(OC))
sys.path.insert(0, str(ROOT / "research" / "tournament" / "ext"))
import analyze_idea8 as A
import harness5 as H5

ANCHORS = [pd.Timestamp(a, tz="UTC") for a in (
    "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")


def _results():
    return json.loads((OC / "results.json").read_text())


def test_multiplier_mapping_boundaries():
    q67 = 0.02
    sym = np.array(["BTCUSDT", "ETHUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT"])
    dd = np.array([99.0, np.nan, 0.02, 0.0200001, -5.0, 5.0], dtype=float)
    m = A.assign_mult(sym, dd, q67)
    # BTC always 1.0 even when flagged; NaN -> 1.0; == q67 tie -> 1.0
    assert list(m) == [1.0, 1.0, 1.0, 0.5, 1.0, 0.5]


def test_decision_counts_match():
    r = _results()
    n_gain = sum(1 for y in r["years"] if y["gain_pass"])
    n_loyo = sum(1 for L in r["loyo"] if L["pass"])
    n_tail = sum(1 for y in r["years"] if y["tail_pass"])
    assert r["decision"]["gain_sequential"] == f"{n_gain}/5" == "4/5"
    assert r["decision"]["loyo_gain"] == f"{n_loyo}/5" == "5/5"
    assert r["decision"]["tail_not_worse"] == f"{n_tail}/5" == "3/5"
    assert r["decision"]["promising"] is False


def test_gain_signs_match_harness():
    """Stored per-year gains equal an independent harness5.score recomputation."""
    d = H5.load()
    d["T"] = pd.to_datetime(d["T"], utc=True)
    feats = pd.read_parquet(OC / "features_idea8.parquet")
    key = feats[["T", "sym", "x1", "ddom"]].drop_duplicates()
    d = d.merge(key, left_on=["T", "sym", "x1"], right_on=["T", "sym", "x1"], how="left")
    assert d.loc[d["sym"].isin(MAJORS) & d["x1"].isin(R2), "ddom"].notna().all()
    r = _results()
    size = np.full(len(d), np.nan)
    is_r2 = d["sym"].isin(MAJORS) & d["k"].isin(R2) & d["size_dep"].notna()
    for k, a0 in enumerate(ANCHORS):
        te = ((d["T"] >= a0) & (d["T"] < a0 + pd.Timedelta(days=365)) & is_r2).to_numpy()
        m = A.assign_mult(d["sym"].to_numpy(dtype=object)[te],
                          d["ddom"].to_numpy(float)[te], r["years"][k]["q67"])
        size[te] = d["size_dep"].to_numpy()[te] * m
    got = H5.score(d, size, name="check")
    for k, yr in enumerate(got["years"]):
        assert yr["gain"] == pytest.approx(r["years"][k]["gain"])
        assert yr["worst_day_new"] == pytest.approx(r["years"][k]["worst_day_new"])
        assert yr["S_new"] == pytest.approx(r["years"][k]["S_new"])


def test_cutoffs_causal():
    """Year-1 + one LOYO cut-off equal strictly-previous bar-pool quantiles."""
    opens = A.load_opens_grid()
    _, ddom = A.compute_dom_ddom(opens)
    bar = pd.DataFrame({"ddom": ddom.to_numpy(float)}, index=opens.index)
    r = _results()
    pool = bar[(bar.index < ANCHORS[0]) & np.isfinite(bar["ddom"].to_numpy())]
    assert len(pool) == r["years"][0]["n_train_bars"] == 8756
    assert pool.index.max() < ANCHORS[0]
    assert float(np.quantile(pool["ddom"].to_numpy(), 2 / 3)) == pytest.approx(r["years"][0]["q67"])
    # LOYO held-out 2022-23: training = bars in the other four year windows only
    h = 1
    other = np.zeros(len(bar), bool)
    for k in range(5):
        if k != h:
            other |= (np.asarray(bar.index >= ANCHORS[k])
                      & np.asarray(bar.index < ANCHORS[k] + pd.Timedelta(days=365)))
    held = (np.asarray(bar.index >= ANCHORS[h])
            & np.asarray(bar.index < ANCHORS[h] + pd.Timedelta(days=365)))
    assert not (other & held).any()
    tr = bar["ddom"].to_numpy(float)[other]
    tr = tr[np.isfinite(tr)]
    assert len(tr) == r["loyo"][h]["n_train_bars"] == 8760
    assert float(np.quantile(tr, 2 / 3)) == pytest.approx(r["loyo"][h]["q67"])


def test_dom_ddom_causal_truncate():
    """dom30/ddom at T from opens truncated to index <= T equals stored values."""
    opens = A.load_opens_grid()
    feats = pd.read_parquet(OC / "features_idea8.parquet")
    uniq = feats.drop_duplicates("T").sort_values("T").reset_index(drop=True)
    samp = uniq.iloc[[0, len(uniq) // 3, len(uniq) // 2, len(uniq) - 1]]
    for _, row in samp.iterrows():
        T = pd.Timestamp(row["T"]).tz_convert("UTC")
        trunc = opens[opens.index <= T]
        dom_t, ddom_t = A.compute_dom_ddom(trunc)
        assert np.isfinite(row["dom30"]) and np.isfinite(row["ddom"])
        assert float(dom_t.iloc[-1]) == pytest.approx(float(row["dom30"]), rel=1e-9)
        assert float(ddom_t.iloc[-1]) == pytest.approx(float(row["ddom"]), rel=1e-9)
    # doubling opens after T leaves dom30/ddom at T unchanged
    T = pd.Timestamp(samp.iloc[1]["T"]).tz_convert("UTC")
    trunc = opens[opens.index <= T]
    dom_t, ddom_t = A.compute_dom_ddom(trunc)
    later = opens[opens.index > T].copy() * 2.0
    grown = pd.concat([trunc, later])
    dom_g, ddom_g = A.compute_dom_ddom(grown)
    assert float(dom_g.loc[T]) == pytest.approx(float(dom_t.loc[T]), rel=1e-12)
    assert float(ddom_g.loc[T]) == pytest.approx(float(ddom_t.loc[T]), rel=1e-12)


def test_T_and_bounds():
    f = pd.read_parquet(ROOT / "research" / "tournament" / "ext" / "fills_U_ext.parquet",
                        columns=["t_fill", "f"])
    T = pd.to_datetime(f["t_fill"], utc=True) - pd.to_timedelta(f["f"], unit="min")
    assert bool((T < CUTOFF).all())
    o = pd.read_parquet(ROOT / "artifacts" / "research" / "engine_real" / "opens_v154.parquet")
    assert bool((o.index < CUTOFF).all() or (o.index[o.index < CUTOFF].max() < CUTOFF))
    r = _results()
    assert r["meta"]["missing_grid_T"] == 0
    assert r["meta"]["T_max"] < "2026-09-24"


def test_universe_counts():
    r = _results()
    assert [y["n"] for y in r["years"]] == [990, 1045, 1330, 989, 1144]
    assert all(y["coverage"] == 1.0 for y in r["years"])
    feats = pd.read_parquet(OC / "features_idea8.parquet")
    feats["T"] = pd.to_datetime(feats["T"], utc=True)
    in_any = np.zeros(len(feats), bool)
    for a0 in ANCHORS:
        in_any |= ((feats["T"] >= a0) & (feats["T"] < a0 + pd.Timedelta(days=365))).to_numpy()
    scored = feats[in_any & feats["size_dep"].notna()]
    assert [int(((feats["T"] >= a0) & (feats["T"] < a0 + pd.Timedelta(days=365))
                 & feats["size_dep"].notna()).sum()) for a0 in ANCHORS] == [990, 1045, 1330, 989, 1144]
    assert int((scored["sym"] != "BTCUSDT").sum()) == sum(
        y["per_coin"]["ETHUSDT"]["n"] + y["per_coin"]["SOLUSDT"]["n"]
        + y["per_coin"]["BNBUSDT"]["n"] + y["per_coin"]["XRPUSDT"]["n"] for y in r["years"])


def test_no_intraday():
    src = (OC / "analyze_idea8.py").read_text()
    for banned in ("intraday", "hourly_ext", "premium", "funding", "deribit",
                   "dvol", "qbasis", "bar_open_ext", "market_features"):
        assert banned not in src.lower(), banned
