"""oc_optctx tests: strict as-of causality, bar-is-start, cutoff causality, spans, universe counts, dvol merge."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_optctx"
sys.path.insert(0, str(OC))
import analyze_optctx as A

FEATS = A.FEATURES
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")


@pytest.fixture(scope="module")
def grids():
    return A.load_options("BTC"), A.load_options("ETH"), A.load_premium()


@pytest.fixture(scope="module")
def feats():
    return pd.read_parquet(OC / "features_optctx.parquet")


def test_asof_strictly_before_T(grids, feats):
    """Truncating every grid to end < T must leave sampled features unchanged."""
    opt_btc, opt_eth, prem = grids
    idx = [0, 1000, 3000, 5000, len(feats) - 1]
    sub = feats.iloc[idx].copy().reset_index(drop=True)
    Tns = sub["TT"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    ref = sub[FEATS].to_numpy(float)
    for i in range(len(sub)):
        T = Tns[i]
        gb = opt_btc[opt_btc["end"] < pd.Timestamp(T, tz="UTC")].copy()
        ge = opt_eth[opt_eth["end"] < pd.Timestamp(T, tz="UTC")].copy()
        gp = prem[prem["end"] < pd.Timestamp(T, tz="UTC")].copy()
        assert len(gb) and len(gp), f"empty truncated grid at {sub['TT'].iloc[i]}"
        for g in (gb, ge, gp):
            assert ((g["end"].to_numpy(dtype="datetime64[ns]").astype(np.int64)) < T).all()
        row = sub.iloc[[i]].copy().reset_index(drop=True)
        got = A.compute_features(row, gb, ge, gp)[FEATS].to_numpy(float)[0]
        np.testing.assert_allclose(got, ref[i], rtol=1e-9, atol=1e-12,
                                   err_msg=f"rung {idx[i]} T={sub['TT'].iloc[i]}")


def test_bar_is_start(grids):
    """Options `bar` is the 4h bar START (all bars on the 4h grid)."""
    for g in grids[:2]:
        mins = (g["bar"].dt.hour * 60 + g["bar"].dt.minute).to_numpy()
        assert set(np.unique(mins)) <= {0, 240, 480, 720, 960, 1200}
        assert (g["end"] == g["bar"] + pd.Timedelta(hours=4)).all()


def test_cutoffs_match_and_causal(feats):
    """results.json cut-offs must equal the previous-data-only training pools."""
    res = json.loads((OC / "results.json").read_text())
    df = feats.copy()
    df["TT"] = pd.to_datetime(df["TT"], utc=True)
    for feat in FEATS:
        x = df[feat].to_numpy(float)
        tr = ((df["TT"] < ANCHORS[0]) & np.isfinite(x)).to_numpy()
        assert int(tr.sum()) >= 100
        assert df["TT"][tr].max() < ANCHORS[0]
        q33, q67 = np.quantile(x[tr], [1 / 3, 2 / 3])
        got = res["features"][feat]["yearly"][0]["cutoffs"]
        assert got["q33"] == pytest.approx(q33) and got["q67"] == pytest.approx(q67)
        h = 2
        trm = np.zeros(len(df), bool)
        for k in range(5):
            if k != h:
                trm |= ((df["TT"] >= ANCHORS[k]) & (df["TT"] < ANCHORS[k] + pd.Timedelta(days=365))).to_numpy()
        trm &= np.isfinite(x)
        held = ((df["TT"] >= ANCHORS[h]) & (df["TT"] < ANCHORS[h] + pd.Timedelta(days=365))).to_numpy()
        assert not (trm & held).any(), "LOYO training must exclude the held-out year"
        q33, q67 = np.quantile(x[trm], [1 / 3, 2 / 3])
        lo = res["features"][feat]["loyo"][h]
        assert lo["q33"] == pytest.approx(q33) and lo["q67"] == pytest.approx(q67)


def test_panel_span_and_cutoff(grids):
    opt_btc, opt_eth, prem = grids
    for g in (opt_btc, opt_eth, prem):
        key = "bar" if "bar" in g.columns else "t"
        assert (g[key] < CUTOFF).all(), "no bar at/after 2026-09-24 00:00 UTC may be used"
    assert opt_btc["bar"].min() <= pd.Timestamp("2019-01-02", tz="UTC")
    assert opt_eth["bar"].min() <= pd.Timestamp("2019-03-22", tz="UTC")
    assert prem["t"].min() <= pd.Timestamp("2020-08-02", tz="UTC")
    assert prem["t"].max() >= pd.Timestamp("2026-09-23 00:00", tz="UTC")


def test_universe_counts(feats):
    assert len(feats) == 6876
    assert feats["TT"].min() == pd.Timestamp("2020-08-25 12:00", tz="UTC")
    assert feats["TT"].max() == pd.Timestamp("2026-09-23 12:00", tz="UTC")
    counts = [int(((feats["TT"] >= a) & (feats["TT"] < a + pd.Timedelta(days=365))).sum()) for a in ANCHORS]
    assert counts == [990, 1045, 1330, 989, 1144]
    assert set(feats["sym"].unique()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
    for feat in FEATS:
        cov = [float(np.isfinite(feats[feat][((feats["TT"] >= a) & (feats["TT"] < a + pd.Timedelta(days=365))).to_numpy()]).mean())
               for a in ANCHORS]
        assert all(c == 1.0 for c in cov), f"coverage must be 100% in all anchor years: {feat} {cov}"


def test_dvol_merge(feats):
    dz = pd.read_parquet(ROOT / "research/tournament/oc_dvol/features_dvol.parquet",
                         columns=["TT", "sym", "x1", "dvol_z90"])
    dz["TT"] = pd.to_datetime(dz["TT"], utc=True)
    m = pd.merge(feats[["TT", "sym", "x1", "dvol_z90"]], dz, on=["TT", "sym", "x1"],
                 suffixes=("", "_ref"))
    assert len(m) == len(feats)
    both = m["dvol_z90"].notna() & m["dvol_z90_ref"].notna()
    assert (m.loc[both, "dvol_z90"] == m.loc[both, "dvol_z90_ref"]).all()
