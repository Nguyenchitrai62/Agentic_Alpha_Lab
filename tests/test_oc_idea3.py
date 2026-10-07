"""oc_idea3 tests: T-grid, RV15 causality, v293 sigma, threshold causality, SKIP purity."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_idea3"

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
COUNTS = [990, 1045, 1330, 989, 1144]
START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24", tz="UTC")


def load_universe():
    f = pd.read_parquet(ROOT / "research/tournament/ext/fills_U_ext.parquet")
    f["T"] = pd.to_datetime(f["t_fill"], utc=True) - pd.to_timedelta(f["f"], unit="min")
    d = f[f["sym"].isin(MAJORS) & f["x1"].isin(R2)].copy().reset_index(drop=True)
    return d


def load_1m_slice(sym: str, lo: pd.Timestamp, hi: pd.Timestamp) -> pd.DataFrame:
    if sym == "BTCUSDT":
        pat = f"klines_1m_{lo.year}.parquet"
        files = [(ROOT / "data/raw/btc_intraday_20260924" / pat)]
        if hi.year != lo.year:
            files.append(ROOT / "data/raw/btc_intraday_20260924" / f"klines_1m_{hi.year}.parquet")
    else:
        files = [ROOT / "data/raw/majors_intraday_20260924" / f"{sym}_1m_{y}.parquet"
                 for y in range(lo.year, hi.year + 1)]
    files = [p for p in files if p.exists()]
    parts = [pd.read_parquet(p, columns=["open_time", "open", "high", "low", "close"]) for p in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    return m[(m.index >= lo - pd.Timedelta(days=70)) & (m.index < hi)]


def test_T_grid_and_bounds():
    d = load_universe()
    assert len(d) == 6876
    assert bool((d["T"] < END).all())
    ns = pd.to_datetime(d["T"], utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    mins = (ns // 60_000_000_000) % (24 * 60)
    assert set(np.unique(mins)) <= {0, 240, 480, 720, 960, 1200}
    for k, a in enumerate(ANCHORS):
        m = (d["T"] >= a) & (d["T"] < a + pd.Timedelta(days=365))
        assert int(m.sum()) == COUNTS[k], f"year {a.date()}: {int(m.sum())}"


def test_rv15_causal_truncate():
    rv = pd.read_parquet(OC / "rv15.parquet")
    rng = np.random.default_rng(3)
    valid = rv[np.isfinite(rv["RV15"].to_numpy())].reset_index(drop=True)
    assert len(valid) > 1000
    for i in rng.choice(len(valid), 3, replace=False):
        row = valid.iloc[i]
        sym, T = row["sym"], pd.to_datetime(row["T"], utc=True)
        m = load_1m_slice(sym, T, T + pd.Timedelta(minutes=16))
        hw = m["high"][(m.index >= T) & (m.index < T + pd.Timedelta(minutes=16))].to_numpy(dtype=float)
        lw = m["low"][(m.index >= T) & (m.index < T + pd.Timedelta(minutes=16))].to_numpy(dtype=float)
        assert len(hw) == 16 and np.all(np.isfinite(hw))
        assert len(lw) == 16 and np.all(np.isfinite(lw))
        o = m["open"].loc[T]
        expect = float((hw.max() - lw.min()) / (float(o) * float(row["sigma"])))
        # analysis stores float32 1m; test recomputes float64 -> allow 5e-6
        assert abs(expect - float(row["RV15"])) < 5e-6, f"{sym} {T}"
        # truncation: dropping minutes > T+15 leaves RV15 unchanged (nothing to drop
        # inside the window, but removing later data must not matter -> recompute same)
        hw2 = m["high"][(m.index >= T) & (m.index <= T + pd.Timedelta(minutes=15))].to_numpy(dtype=float)
        assert len(hw2) == 16
        assert abs(float((hw2.max() - lw.min()) / (float(o) * float(row["sigma"]))) - float(row["RV15"])) < 5e-6


def test_sigma_matches_v293():
    rv = pd.read_parquet(OC / "rv15.parquet")
    for sym in ["BTCUSDT", "ETHUSDT"]:
        sub = rv[rv["sym"] == sym].sort_values("T").reset_index(drop=True)
        sub = sub[np.isfinite(sub["sigma"].to_numpy())].reset_index(drop=True)
        pick = sub.iloc[len(sub) // 2: len(sub) // 2 + 5]
        lo = pd.to_datetime(pick["T"].min(), utc=True) - pd.Timedelta(days=70)
        hi = pd.to_datetime(pick["T"].max(), utc=True) + pd.Timedelta(hours=4)
        m = load_1m_slice(sym, lo, hi)
        full = pd.date_range(START, m.index.max() + pd.Timedelta(minutes=1), freq="1min", tz="UTC")
        # rebuild opens on the START grid up to hi and compare rolling sigma
        m_full = m.reindex(full)
        opens = m_full["open"].to_numpy(dtype=float)
        n = len(full)
        nb = n // 240
        O = opens[: nb * 240: 240]
        sig = pd.Series(O).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy(dtype=float)
        bt = full[: nb * 240: 240]
        smap = dict(zip(bt, sig))
        for _, r in pick.iterrows():
            T = pd.to_datetime(r["T"], utc=True)
            # float32 vs float64 opens -> allow 1e-7
            assert abs(float(smap[T]) - float(r["sigma"])) < 1e-7, f"{sym} {T}"


def test_thresholds_causal():
    rv = pd.read_parquet(OC / "rv15.parquet")
    res = json.loads((OC / "results.json").read_text())
    rv["T"] = pd.to_datetime(rv["T"], utc=True)
    for k, a in enumerate(ANCHORS):
        w = rv[(rv["T"] >= a - pd.Timedelta(days=365)) & (rv["T"] < a)
               & np.isfinite(rv["RV15"].to_numpy())]
        assert res["thresholds_seq"][k]["n_train"] == int(len(w)) >= 500
        assert abs(float(w["RV15"].quantile(0.80)) - res["thresholds_seq"][k]["q80"]) < 1e-12
    total_in_years = 0
    for k, a in enumerate(ANCHORS):
        total_in_years += int(((rv["T"] >= a) & (rv["T"] < a + pd.Timedelta(days=365))
                               & np.isfinite(rv["RV15"].to_numpy())).sum())
    for h, a in enumerate(ANCHORS):
        l = res["thresholds_loyo"][h]
        assert l["heldout"] == str(a.date())
        assert l["n_train"] == total_in_years - int(
            ((rv["T"] >= a) & (rv["T"] < a + pd.Timedelta(days=365))
             & np.isfinite(rv["RV15"].to_numpy())).sum())


def test_skip_recomputable():
    """SKIP from (sym,T,RV15,thresholds) without any y-column is identical."""
    res = json.loads((OC / "results.json").read_text())
    rv = pd.read_parquet(OC / "rv15.parquet")
    d = load_universe()
    d = d[d["T"] < END].reset_index(drop=True)
    dd = d.merge(rv[["T", "sym", "RV15"]], on=["T", "sym"], how="left")
    assert "y1.0" in dd.columns
    no_y = dd.drop(columns=[c for c in dd.columns if c.startswith("y")])
    rv15v = no_y["RV15"].to_numpy(dtype=float)
    skip = np.zeros(len(no_y), bool)
    for k, a in enumerate(ANCHORS):
        q = res["thresholds_seq"][k]["q80"]
        m = ((no_y["T"] >= a) & (no_y["T"] < a + pd.Timedelta(days=365))).to_numpy()
        if np.isfinite(q):
            skip |= (m & np.isfinite(rv15v) & (rv15v > q))
    for k, a in enumerate(ANCHORS):
        w = res["years"][k]
        m = ((no_y["T"] >= a) & (no_y["T"] < a + pd.Timedelta(days=365))).to_numpy()
        assert int((skip & m).sum()) == w["n_skip"]
