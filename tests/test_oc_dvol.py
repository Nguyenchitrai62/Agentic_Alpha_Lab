"""oc_dvol tests: strict as-of causality, cutoff causality, raw/panel coverage, universe counts."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_dvol"
RAW = ROOT / "data/raw/deribit_dvol_20261005"
sys.path.insert(0, str(OC))
import analyze_dvol as A

FEATS = ["dvol_z90", "dvol_chg24", "vrp"]
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]


@pytest.fixture(scope="module")
def dvol():
    return A.load_dvol()


@pytest.fixture(scope="module")
def daily():
    return A.load_daily()


@pytest.fixture(scope="module")
def feats():
    return pd.read_parquet(OC / "features_dvol.parquet")


def test_asof_strictly_before_T(dvol, daily, feats):
    """Truncating every panel to end < T must leave sampled features unchanged."""
    idx = [0, 1000, 3000, 5000, len(feats) - 1]
    sub = feats.iloc[idx].copy().reset_index(drop=True)
    Tns = sub["TT"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    ref = sub[FEATS].to_numpy(float)
    for i in range(len(sub)):
        T = Tns[i]
        dvol_t = {c: (e[e < T], v[e < T]) for c, (e, v) in dvol.items()}
        daily_t = {c: (e[e < T], v[e < T]) for c, (e, v) in daily.items()}
        # every retained bar strictly precedes T
        for c, (e, _) in list(dvol_t.items()) + list(daily_t.items()):
            assert (e < T).all(), f"panel {c} leaks at T={sub['TT'].iloc[i]}"
        row = sub.iloc[[i]].copy().reset_index(drop=True)
        got = A.compute_features(row, dvol_t, daily_t)[FEATS].to_numpy(float)[0]
        np.testing.assert_allclose(got, ref[i], rtol=1e-9, atol=1e-12,
                                   err_msg=f"rung {idx[i]} T={sub['TT'].iloc[i]}")


def test_cutoffs_match_and_causal(feats):
    """results.json cut-offs must equal the previous-data-only training pools."""
    res = json.loads((OC / "results.json").read_text())
    df = feats.copy()
    df["TT"] = pd.to_datetime(df["TT"], utc=True)
    for feat in FEATS:
        x = df[feat].to_numpy(float)
        # year-1 cut-offs
        tr = ((df["TT"] >= A.FEAT_START) & (df["TT"] < ANCHORS[0]) & np.isfinite(x)).to_numpy()
        assert tr.sum() >= 100
        assert df["TT"][tr].max() < ANCHORS[0]
        q33, q67 = np.quantile(x[tr], [1 / 3, 2 / 3])
        got = res["features"][feat]["yearly"][0]["cutoffs"]
        assert got["q33"] == pytest.approx(q33) and got["q67"] == pytest.approx(q67)
        # one LOYO fold (held-out 2023-24): training = the other four years
        h = 2
        trm = np.zeros(len(df), bool)
        for k in range(5):
            if k != h:
                trm |= ((df["TT"] >= ANCHORS[k]) & (df["TT"] < ANCHORS[k] + pd.Timedelta(days=365))).to_numpy()
        trm &= np.isfinite(x)
        held = ((df["TT"] >= ANCHORS[h]) & (df["TT"] < ANCHORS[h] + pd.Timedelta(days=365))).to_numpy()
        assert not (trm & held).any(), "LOYO training must exclude the held-out year"
        q33, q67 = np.quantile(x[trm], [1 / 3, 2 / 3])
        # compare against analyze's own LOYO info path via stored spread inputs
        lo = res["features"][feat]["loyo"][h]
        assert lo["q33"] == pytest.approx(q33) and lo["q67"] == pytest.approx(q67)


def test_manifest_and_panel(dvol):
    man = json.loads((RAW / "manifest.json").read_text())
    assert len(man["files"]) == 132, "2 coins x 66 months"
    for name, e in man["files"].items():
        assert e["url"].startswith("https://www.deribit.com/api/v2/public/get_volatility_index_data")
        h = hashlib.sha256((RAW / name).read_bytes()).hexdigest()
        assert h == e["sha256"], f"sha mismatch {name}"
    panel = pd.read_parquet(OC / "dvol_hourly.parquet")
    for sym in ("BTCDVOL", "ETHDVOL"):
        g = panel[panel["sym"] == sym].sort_values("t")
        assert g["t"].min() <= pd.Timestamp("2021-04-01 01:00", tz="UTC")
        assert g["t"].max() >= pd.Timestamp("2026-09-23 00:00", tz="UTC")
        steps = g["t"].diff().dropna().unique()
        assert len(steps) == 1 and steps[0] == pd.Timedelta(hours=1), f"gaps in {sym}"


def test_universe_counts(feats):
    assert len(feats) == 6876
    assert feats["TT"].min() == pd.Timestamp("2020-08-25 12:00", tz="UTC")
    assert feats["TT"].max() == pd.Timestamp("2026-09-23 12:00", tz="UTC")
    counts = [int(((feats["TT"] >= a) & (feats["TT"] < a + pd.Timedelta(days=365))).sum()) for a in ANCHORS]
    assert counts == [990, 1045, 1330, 989, 1144]
    assert set(feats["sym"].unique()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
