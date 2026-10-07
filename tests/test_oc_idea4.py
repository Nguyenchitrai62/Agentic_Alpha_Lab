"""oc_idea4 tests: universe counts/T-grid, surprise causality, cutoff causality,
no-intraday-data, flag/outcome separation, results integrity."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_idea4"
sys.path.insert(0, str(OC))
import analyze_idea4 as A

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
COUNTS = [990, 1045, 1330, 989, 1144]
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")


def load_universe():
    f = pd.read_parquet(ROOT / "research/tournament/ext/fills_U_ext.parquet")
    f["T"] = pd.to_datetime(f["t_fill"], utc=True) - pd.to_timedelta(f["f"], unit="min")
    d = f[f["sym"].isin(MAJORS) & f["x1"].isin(R2)].copy().reset_index(drop=True)
    return d


def btc_tabs():
    """BTC-only settlement table mirroring analyze_idea4 (single coin, fast)."""
    f = pd.read_parquet(ROOT / "data/raw/binance_premium_20260928/BTCUSDT_funding.parquet")
    f["calc_time"] = pd.to_datetime(f["calc_time"], utc=True)
    f = f.sort_values("calc_time").reset_index(drop=True)
    S = f["calc_time"]
    settled = f["last_funding_rate"].to_numpy(dtype=float)
    Sf = S.dt.floor("min")
    p = pd.read_parquet(ROOT / "data/raw/binance_premium_20260928/BTCUSDT_premium_1m.parquet",
                        columns=["open_time", "close"])
    p["open_time"] = pd.to_datetime(p["open_time"], utc=True)
    p = p[p["open_time"] < CUTOFF].sort_values("open_time").reset_index(drop=True)
    t = p["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    c = p["close"].to_numpy(dtype=float)
    q = Sf.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    lo = np.searchsorted(t, q - 60 * 60_000_000_000, side="left")
    hi = np.searchsorted(t, q, side="left")
    P = np.full(len(q), np.nan)
    for i in range(len(q)):
        if hi[i] - lo[i] >= 30:
            P[i] = float(np.mean(c[lo[i]:hi[i]]))
    return pd.DataFrame({"S": S, "settled": settled, "P": P,
                         "s1": settled - P}), p


def test_universe_counts():
    d = load_universe()
    assert len(d) == 6876
    assert (d["T"] < CUTOFF).all()
    mins = (d["T"].to_numpy(dtype="datetime64[ns]").astype(np.int64) // 60_000_000_000) % (24 * 60)
    assert set(np.unique(mins)) <= {0, 240, 480, 720, 960, 1200}
    for k, a in enumerate(ANCHORS):
        m = (d["T"] >= a) & (d["T"] < a + pd.Timedelta(days=365))
        assert int(m.sum()) == COUNTS[k], f"year {a.date()}: {int(m.sum())}"


def test_surprise_strictly_before_T():
    tab, p = btc_tabs()
    d = load_universe()
    btc = d[d["sym"] == "BTCUSDT"].sort_values("T").reset_index(drop=True)
    sample = btc.iloc[::7].copy().reset_index(drop=True)  # every 7th BTC row
    s1 = A.surprise_at_T({"BTCUSDT": tab}, "BTCUSDT", pd.DatetimeIndex(sample["T"]), "s1")
    assert np.isfinite(s1).mean() > 0.99
    Sns = tab["S"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    q = pd.DatetimeIndex(sample["T"]).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    j = np.searchsorted(Sns, q, side="left") - 1
    assert (j >= 0).all()
    assert (Sns[j] < q).all(), "every settlement used is strictly before T"
    # premium window bars end <= S* < T: spot-check first 5 sampled rows
    tns = p["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    for k in range(5):
        Sk = pd.Timestamp(Sns[j[k]])
        Sf = Sk.floor("min")
        lo = np.searchsorted(tns, (Sf - pd.Timedelta(minutes=60)).value, side="left")
        hi = np.searchsorted(tns, Sf.value, side="left")
        assert hi - lo >= 30
        assert (tns[lo:hi] + 60_000_000_000 <= Sns[j[k]]).all()
        assert Sns[j[k]] < q[k]
    # truncate-all-data-at-T leaves surprise unchanged (causality)
    T0 = sample["T"].iloc[len(sample) // 2]
    trunc = tab[tab["S"] < T0]
    v_full = A.surprise_at_T({"BTCUSDT": tab}, "BTCUSDT", pd.DatetimeIndex([T0]), "s1")
    v_tr = A.surprise_at_T({"BTCUSDT": trunc}, "BTCUSDT", pd.DatetimeIndex([T0]), "s1")
    assert float(v_full[0]) == float(v_tr[0])


def test_cutoffs_causal():
    tab, _ = btc_tabs()
    d = load_universe()
    btc = d[d["sym"] == "BTCUSDT"].sort_values("T").reset_index(drop=True)
    btc["s1"] = A.surprise_at_T({"BTCUSDT": tab}, "BTCUSDT", pd.DatetimeIndex(btc["T"]), "s1")
    res = json.loads((OC / "results.json").read_text())
    y1 = res["variants"]["V1_prem"]["yearly"]
    for k, a0 in enumerate(ANCHORS):
        tr = btc[(btc["T"] < a0)]["s1"].dropna()
        assert len(tr) >= 100
        expect = float(tr.quantile(0.8)) * 1e4
        got = y1[k]["thr_bps"]["BTCUSDT"]
        # stored thresholds are rounded to 3 decimals in results.json
        assert got is not None and abs(got - expect) < 1e-3, f"year {a0.date()}"
    # LOYO path excludes the held-out year (structural check on the script)
    src = (OC / "analyze_idea4.py").read_text()
    assert "if a0 == ah:" in src and "in_any |= " in src


def test_no_intraday_1m():
    src = (OC / "analyze_idea4.py").read_text()
    for bad in ("majors_intraday", "btc_intraday", "alts2020", "spot_majors",
                "hourly_ext", "bar_open_ext", "newinfo_idea4"):
        assert bad not in src, bad
    p = pd.read_parquet(ROOT / "data/raw/binance_premium_20260928/BTCUSDT_premium_1m.parquet",
                        columns=["open_time"])
    assert pd.to_datetime(p["open_time"], utc=True).max() < CUTOFF + pd.Timedelta(days=3)
    # analysis window itself is cut off: every premium bar it could use starts before CUTOFF
    assert "CUTOFF" in src and "< CUTOFF" in src


def test_skip_recompute_no_outcome():
    tab, _ = btc_tabs()
    d = load_universe()
    res = json.loads((OC / "results.json").read_text())
    # flags recomputed with NO y-columns at all (T + surprise + stored thresholds)
    y1 = res["variants"]["V1_prem"]["yearly"][0]
    a0 = ANCHORS[0]
    yy = d[(d["T"] >= a0) & (d["T"] < a0 + pd.Timedelta(days=365))].copy().reset_index(drop=True)
    nomarket = yy[["T", "sym", "x1", "f", "t_fill"]].copy()
    s1 = np.full(len(nomarket), np.nan)
    for s in MAJORS:
        idx = (nomarket["sym"] == s).to_numpy()
        if s == "BTCUSDT":
            s1[idx] = A.surprise_at_T({"BTCUSDT": tab}, s, pd.DatetimeIndex(nomarket.loc[idx, "T"]), "s1")
    assert np.isfinite(s1[nomarket["sym"] == "BTCUSDT"]).all()
    # stored BTC threshold reproduces the BTC slice of the flag
    thr = y1["thr_bps"]["BTCUSDT"] / 1e4
    btc = nomarket["sym"] == "BTCUSDT"
    assert int(((s1[btc] > thr)).sum()) > 0
    # results integrity: pre-registered decision values
    v1 = res["variants"]["V1_prem"]["decision"]
    assert v1 == {"year_neg": 5, "loyo_neg": 4, "loyo_agree": 4, "tail_years": 3, "promising": False}
    v2 = res["variants"]["V2_innov"]["decision"]
    assert v2 == {"year_neg": 2, "loyo_neg": 2, "loyo_agree": 2, "tail_years": 0, "promising": False}
    assert res["overall_promising"] is False
    assert res["meta"]["n"] == 6876 and res["meta"]["per_year_n"] == COUNTS
