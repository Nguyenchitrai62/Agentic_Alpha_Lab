"""oc_premfill tests: fill-time causality (bars END <= t_fill), cutoff causality, universe counts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_premfill"
sys.path.insert(0, str(OC))
import analyze_premfill as A

FEATS = ["prem", "prem_chg30", "prem_z7d"]
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
MIN_NS = 60_000_000_000


@pytest.fixture(scope="module")
def feats():
    df = pd.read_parquet(OC / "features_premfill.parquet")
    df["TT"] = pd.to_datetime(df["TT"], utc=True)
    df["t_fill"] = pd.to_datetime(df["t_fill"], utc=True)
    return df


def test_fill_bar_strictly_before_fill(feats):
    """Truncating each coin panel to bars with END <= t_fill leaves features unchanged."""
    for sym in ("BTCUSDT", "ETHUSDT", "XRPUSDT"):
        opens, closes = A.load_premium(sym)
        sub = feats[feats["sym"] == sym].iloc[[0, len(feats[feats['sym'] == sym]) // 2, -1]]
        tf = sub["t_fill"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
        ref = sub[FEATS].to_numpy(float)
        # every used bar must end at/before the fill
        for t in tf:
            assert (opens[opens <= t - MIN_NS] + MIN_NS <= t).all()
        got_full = A.compute_coin_features(tf, opens, closes)
        for i, t in enumerate(tf):
            keep = opens < t  # bar END = open + 1m <= t_fill
            assert (opens[keep] <= t - MIN_NS).all(), f"{sym} leaks at t_fill={sub['t_fill'].iloc[i]}"
            got = A.compute_coin_features(np.array([t]), opens[keep], closes[keep])
            for j, feat in enumerate(FEATS):
                want = got_full[feat][i]
                assert (np.isnan(got[feat][0]) and np.isnan(want)) or got[feat][0] == pytest.approx(want), \
                    f"{sym} {feat} row {i}"


def test_fminus1_exact_match(feats):
    """The f-1 bar must be an exact open_time == t_fill - 1m match (no fill-forward)."""
    opens, _ = A.load_premium("BTCUSDT")
    sub = feats[feats["sym"] == "BTCUSDT"].iloc[:500]
    tf = sub["t_fill"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    target = tf - MIN_NS
    pos = np.searchsorted(opens, target)
    exact = np.zeros(len(tf), bool)
    ok = pos < len(opens)
    exact[ok] = opens[pos[ok]] == target[ok]
    fin = sub["prem"].to_numpy(float)
    np.testing.assert_array_equal(np.isfinite(fin), exact,
                                  err_msg="prem finite iff exact f-1 bar exists")


def test_training_cutoffs_causal(feats):
    """results.json cut-offs must equal strictly-previous-data training pools."""
    res = json.loads((OC / "results.json").read_text())
    df = feats.copy()
    TT = df["TT"]
    for feat in FEATS:
        x = df[feat].to_numpy(float)
        for k, a0 in enumerate(ANCHORS):
            tr = ((TT < a0) & np.isfinite(x)).to_numpy()
            year = res["features"][feat]["yearly"][k]
            if year["cutoffs"]:
                assert tr.sum() >= 100
                assert df.loc[tr, "TT"].max() < a0
                q33, q67 = np.quantile(x[tr], [1 / 3, 2 / 3])
                assert year["cutoffs"]["q33"] == pytest.approx(q33)
                assert year["cutoffs"]["q67"] == pytest.approx(q67)
        h = 2
        trm = np.zeros(len(df), bool)
        for k in range(5):
            if k != h:
                trm |= ((TT >= ANCHORS[k]) & (TT < ANCHORS[k] + pd.Timedelta(days=365))).to_numpy()
        trm &= np.isfinite(x)
        held = ((TT >= ANCHORS[h]) & (TT < ANCHORS[h] + pd.Timedelta(days=365))).to_numpy()
        assert not (trm & held).any(), "LOYO training must exclude the held-out year"
        lo = res["features"][feat]["loyo"][h]
        if "q33" in lo:
            q33, q67 = np.quantile(x[trm], [1 / 3, 2 / 3])
            assert lo["q33"] == pytest.approx(q33) and lo["q67"] == pytest.approx(q67)


def test_cutoff_and_universe_counts(feats):
    for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"):
        opens, _ = A.load_premium(sym)
        assert pd.to_datetime(opens.max(), utc=True, unit="ns") < pd.Timestamp("2026-09-24", tz="UTC")
    assert len(feats) == 6876
    assert feats["TT"].min() == pd.Timestamp("2020-08-25 12:00", tz="UTC")
    assert feats["TT"].max() == pd.Timestamp("2026-09-23 12:00", tz="UTC")
    counts = [int(((feats["TT"] >= a) & (feats["TT"] < a + pd.Timedelta(days=365))).sum()) for a in ANCHORS]
    assert counts == [990, 1045, 1330, 989, 1144]
    assert set(feats["sym"].unique()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
