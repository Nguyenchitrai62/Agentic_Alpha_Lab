"""oc_filltime tests: grid alignment, feature causality (truncation), sigma match, cutoff causality."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_filltime"
sys.path.insert(0, str(OC))
import build_features as B

ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
EXPECT_N = [990, 1045, 1330, 989, 1144]


@pytest.fixture(scope="module")
def feats():
    df = pd.read_parquet(OC / "features_filltime.parquet")
    df["TT"] = pd.to_datetime(df["TT"], utc=True)
    return df


def test_T_grid_and_f_range(feats):
    assert ((feats["t_fill"] - feats["TT"]).dt.total_seconds() / 60.0 == feats["f"]).all()
    assert feats["f"].between(16, 238).all()
    mins = (feats["TT"] - B.START).dt.total_seconds() / 60.0
    assert np.allclose(mins % 240, 0), "TT must sit on 4h boundaries"
    for k, a in enumerate(ANCHORS):
        n = int((((feats["TT"] >= a) & (feats["TT"] < a + pd.Timedelta(days=365)))).sum())
        assert n == EXPECT_N[k], f"year {a.date()}: {n} != {EXPECT_N[k]}"


def test_age24_definition():
    h = np.arange(1440, dtype=float)  # strictly rising -> high at m
    assert B.age24_of(h, 1439) == 0.0
    h2 = np.zeros(1440)
    h2[100] = 5.0  # unique max 1339 min ago
    assert B.age24_of(h2, 1439) == 1339.0
    h3 = h2.copy()
    h3[1439] = np.nan
    assert np.isnan(B.age24_of(h3, 1439))
    assert np.isnan(B.age24_of(h, 100))  # window incomplete


@pytest.fixture(scope="module")
def btc():
    m = B.load_1m("BTCUSDT")
    full = pd.date_range(B.START, B.END - pd.Timedelta(minutes=1), freq="1min", tz="UTC")
    return m, full


def test_age_truncation(feats, btc):
    """age24 from highs truncated to t <= m equals the stored value."""
    m, full = btc
    H = m["high"].to_numpy(dtype=float)
    pos = pd.Series(np.arange(len(full)), index=full)
    sub = feats[(feats["sym"] == "BTCUSDT") & np.isfinite(feats["age24"])].iloc[[0, 50, 200, 500, 900]]
    for _, r in sub.iterrows():
        mt = pd.Timestamp(r["TT"]) + pd.Timedelta(minutes=int(r["f"]) - 1)
        mp = int(pos[mt])
        assert B.age24_of(H[: mp + 1], mp) == pytest.approx(float(r["age24"]))
        # shifting data after m leaves it unchanged (uses only t <= m)
        H2 = H.copy()
        H2[mp + 1:] = np.nan
        assert B.age24_of(H2, mp) == pytest.approx(float(r["age24"]))


def test_nweak_truncation(feats, btc):
    """n_weak uses only closes at minute m and bar-open O/sigma."""
    m, full = btc
    C = m["close"].to_numpy(dtype=float)
    t0, opens, sigma = B.bar_opens_sigma(m)
    pos = pd.Series(np.arange(len(full)), index=full)
    sub = feats[np.isfinite(feats["n_weak"])].iloc[[10, 300, 700, 1500, 3000]]
    closes = {"BTCUSDT": C}
    for sym in ("ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"):
        px = B.load_1m(sym)
        closes[sym] = px["close"].to_numpy(dtype=float)
        del px
    grids = {}
    for sym in B.MAJORS:
        if sym == "BTCUSDT":
            grids[sym] = (t0, opens, sigma)
        else:
            px = B.load_1m(sym)
            grids[sym] = B.bar_opens_sigma(px)
            del px
    for _, r in sub.iterrows():
        mt = pd.Timestamp(r["TT"]) + pd.Timedelta(minutes=int(r["f"]) - 1)
        mp = int(pos[mt])
        parts = []
        for c in [x for x in B.MAJORS if x != r["sym"]]:
            t0c, oc, sgc = grids[c]
            j = int(round((pd.Timestamp(r["TT"]) - B.START).total_seconds() / 60 / 240))
            cl = closes[c][mp]  # only minute m is read
            w = 1.0 if cl <= oc[j] * (1 - 2.5 * sgc[j]) else 0.0
            parts.append(w)
        assert sum(parts) == pytest.approx(float(r["n_weak"]))


def test_sigma_matches_v293(btc):
    m, _ = btc
    t0, opens, sigma = B.bar_opens_sigma(m)
    ref = pd.Series(opens).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy(dtype=float)
    assert len(sigma) == len(ref)
    ok = np.isfinite(sigma) & np.isfinite(ref)
    np.testing.assert_allclose(sigma[ok], ref[ok], rtol=1e-12)
    assert ok.sum() > 1000


def test_cutoffs_causal(feats):
    res = json.loads((OC / "results.json").read_text())
    for feat in ("f", "age24", "n_weak"):
        x = feats[feat].to_numpy(dtype=float)
        tr = ((feats["TT"] < ANCHORS[0]) & np.isfinite(x)).to_numpy()
        assert tr.sum() >= 100 and feats["TT"][tr].max() < ANCHORS[0]
        q33, q67 = np.quantile(x[tr], [1 / 3, 2 / 3])
        got = res["features"][feat]["yearly"][0]["cutoffs"]
        assert got["q33"] == pytest.approx(q33) and got["q67"] == pytest.approx(q67)
        h = 2
        trm = np.zeros(len(feats), bool)
        for k in range(5):
            if k != h:
                trm |= ((feats["TT"] >= ANCHORS[k]) & (feats["TT"] < ANCHORS[k] + pd.Timedelta(days=365))).to_numpy()
        trm &= np.isfinite(x)
        held = ((feats["TT"] >= ANCHORS[h]) & (feats["TT"] < ANCHORS[h] + pd.Timedelta(days=365))).to_numpy()
        assert not (trm & held).any()
        q33, q67 = np.quantile(x[trm], [1 / 3, 2 / 3])
        lo = res["features"][feat]["loyo"][h]
        assert lo["q33"] == pytest.approx(q33) and lo["q67"] == pytest.approx(q67)
