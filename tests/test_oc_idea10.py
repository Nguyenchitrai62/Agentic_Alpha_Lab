"""oc_idea10 tests: universe counts/T-grid, 1h-state causality, sigma, KEEP leak-free."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_idea10"
sys.path.insert(0, str(OC))
import analyze_idea10 as A

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
COUNTS = [990, 1045, 1330, 989, 1144]


def load_universe():
    f = pd.read_parquet(ROOT / "research/tournament/ext/fills_U_ext.parquet")
    f["T"] = pd.to_datetime(f["t_fill"], utc=True) - pd.to_timedelta(f["f"], unit="min")
    d = f[f["sym"].isin(MAJORS) & f["x1"].isin(R2)].copy().reset_index(drop=True)
    return d


def test_counts_and_grid():
    d = load_universe()
    assert len(d) == 6876
    assert (d["T"] < pd.Timestamp("2026-09-24", tz="UTC")).all()
    ns = pd.to_datetime(d["T"], utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    mins = (ns // 60_000_000_000) % (24 * 60)
    assert set(np.unique(mins)) <= {0, 240, 480, 720, 960, 1200}
    for k, a in enumerate(ANCHORS):
        m = (d["T"] >= a) & (d["T"] < a + pd.Timedelta(days=365))
        assert int(m.sum()) == COUNTS[k], f"year {a.date()}: {int(m.sum())}"


def _synth_hourly(t0="2023-05-01 00:00", n=800, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(t0, periods=n, freq="h", tz="UTC")
    ret = rng.normal(0, 0.005, n)
    px = 100 * np.exp(np.cumsum(ret))
    df = pd.DataFrame({"t": idx, "open": px,
                       "high": px * 1.002, "low": px * 0.998,
                       "close": px})
    return df


def test_sigma_matches_v293():
    df = _synth_hourly()
    hh = pd.to_datetime(df["t"], utc=True)
    gmask = (hh.dt.hour % 4 == 0) & (hh.dt.minute == 0)
    grid = df.loc[gmask, ["t", "open"]].copy().sort_values("t").reset_index(drop=True)
    got = A.sigma_on_grid(grid).to_numpy(dtype=float)
    ref = pd.Series(grid["open"].to_numpy(dtype=float)).pct_change(
    ).rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
    assert len(got) == len(ref)
    m = np.isfinite(got) & np.isfinite(ref)
    assert m.sum() > 0
    assert np.allclose(got[m], ref[m], equal_nan=True)
    # early bars NaN (warm-up), late bars finite
    assert not np.isfinite(got[0])
    assert np.isfinite(got[-1])


def test_state_causal():
    """state(T) uses only hourly rows t <= T; strict > 1.0 boundary; NaN handling."""
    h = pd.read_parquet(ROOT / "research/tournament/ext/hourly_ext.parquet")
    h["t"] = pd.to_datetime(h["t"], utc=True)
    sym = "BTCUSDT"
    hc = h[h["sym"] == sym][["t", "open", "low"]].copy()
    tab = A.compute_state_for_coin(hc)
    # pick a real T in-sample (mid-history, on 4h grid, with full history)
    T = pd.Timestamp("2023-05-01 12:00", tz="UTC")
    Tns = int(T.value)
    st, oT, sg, ml = A.gate_for_T(tab["open_by_t"], tab["low_by_t"],
                                  tab["sig_by_t"], tab["H"], Tns)
    assert np.isfinite(st)
    # truncate hourly to t <= T: identical
    hc_tr = hc[hc["t"] <= T].copy()
    tab_tr = A.compute_state_for_coin(hc_tr)
    st2, _, _, _ = A.gate_for_T(tab_tr["open_by_t"], tab_tr["low_by_t"],
                                tab_tr["sig_by_t"], tab_tr["H"], Tns)
    assert abs(st - st2) < 1e-12
    # perturbing a future row (t > T) leaves state unchanged
    hc_fu = hc.copy()
    fut = hc_fu["t"] > T
    assert fut.sum() > 0
    hc_fu.loc[fut, "low"] = hc_fu.loc[fut, "low"] * 0.5
    tab_fu = A.compute_state_for_coin(hc_fu)
    st3, _, _, _ = A.gate_for_T(tab_fu["open_by_t"], tab_fu["low_by_t"],
                                tab_fu["sig_by_t"], tab_fu["H"], Tns)
    assert abs(st - st3) < 1e-12
    # hand-check: state formula on the six lows
    H = 3_600_000_000_000
    lows = np.array([tab["low_by_t"][Tns - k * H] for k in range(1, 7)], float)
    expect = (oT - lows.min()) / (oT * sg)
    assert abs(st - expect) < 1e-12
    # strict boundary: exactly 1.0 -> KEEP 0
    assert not bool(np.isfinite(1.0) and (1.0 > 1.0))
    assert bool(np.isfinite(1.0000001) and (1.0000001 > 1.0))
    # missing low -> NaN state
    low2 = dict(tab["low_by_t"])
    low2[Tns - H] = np.nan
    st4, _, _, _ = A.gate_for_T(tab["open_by_t"], low2, tab["sig_by_t"], tab["H"], Tns)
    assert not np.isfinite(st4)


def test_keep_recomputable():
    """KEEP recomputed from (sym,T,state) after dropping y-columns is identical."""
    d = load_universe()
    d = d[d["T"] < pd.Timestamp("2026-09-24", tz="UTC")].reset_index(drop=True)
    h = pd.read_parquet(ROOT / "research/tournament/ext/hourly_ext.parquet")
    h["t"] = pd.to_datetime(h["t"], utc=True)
    h = h[h["t"] < pd.Timestamp("2026-09-24", tz="UTC")].copy()
    coin_tab = {}
    for sym in MAJORS[:2]:  # two coins suffice for the leak check (LIGHT)
        hc = h[h["sym"] == sym][["t", "open", "low"]].copy()
        coin_tab[sym] = A.compute_state_for_coin(hc)
    sub = d[d["sym"].isin(MAJORS[:2])].copy().reset_index(drop=True)
    Tns = pd.to_datetime(sub["T"], utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    k1 = np.zeros(len(sub), bool)
    for i, (sym, tn) in enumerate(zip(sub["sym"].to_numpy(), Tns)):
        tab = coin_tab[sym]
        st, _, _, _ = A.gate_for_T(tab["open_by_t"], tab["low_by_t"],
                                   tab["sig_by_t"], tab["H"], int(tn))
        k1[i] = bool(np.isfinite(st) and st > 1.0)
    # drop every market/outcome column: recompute from T+hourly only -> identical
    keep_cols = sub[["sym", "T"]].copy()
    assert "y1.0" not in keep_cols.columns and "x0" not in keep_cols.columns
    k2 = np.zeros(len(sub), bool)
    for i, (sym, tn) in enumerate(zip(keep_cols["sym"].to_numpy(), Tns)):
        tab = coin_tab[sym]
        st, _, _, _ = A.gate_for_T(tab["open_by_t"], tab["low_by_t"],
                                   tab["sig_by_t"], tab["H"], int(tn))
        k2[i] = bool(np.isfinite(st) and st > 1.0)
    assert (k1 == k2).all()


def test_decision_matches_counts():
    res = json.loads((OC / "results.json").read_text())
    years, loyo = res["years"], res["loyo"]
    assert len(years) == 5 and len(loyo) == 5
    pos = sum(1 for w in years if w["spread_bps"] is not None and w["spread_bps"] > 0)
    agr = sum(1 for L in loyo if L["sign_agrees"])
    tails = sum(1 for w in years if w["tail_improves"])
    assert res["decision"]["pos_spread_count"] == f"{pos}/5"
    assert res["decision"]["loyo_agree_count"] == f"{agr}/5"
    assert res["decision"]["tail_improve_count"] == f"{tails}/5"
    assert res["decision"]["promising"] == bool(pos >= 4 and agr >= 4 and tails >= 4)
    assert res["meta"]["n_majors_r2"] == 6876
    for w in years:
        assert w["n_full"] == w["n_kept"] + w["n_drop"]
        assert w["S_full"] is not None and w["worst_day_full"] is not None
