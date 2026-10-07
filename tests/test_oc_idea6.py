"""Causality + accounting tests for oc_idea6 (no outcome tuning here)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research" / "tournament" / "oc_idea6"
sys.path.insert(0, str(OC))
sys.path.insert(0, str(ROOT / "research" / "tournament" / "ext"))
import analyze_idea6 as A
import harness5 as H5

ANCHORS = [pd.Timestamp(a, tz="UTC") for a in (
    "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
YEAR_LEN = pd.Timedelta(days=365)


def _results():
    return json.loads((OC / "results.json").read_text())


def _build_full():
    """Full causal rebuild of (grid, grid_mom, qb4) via the analysis code path."""
    h = pd.read_parquet(str(A.HOURLY), columns=["t", "close", "sym"])
    hb = h[h.sym == "BTCUSDT"][["t", "close"]].sort_values("t").reset_index(drop=True)
    hb["close_time"] = pd.to_datetime(hb["t"], utc=True) + pd.Timedelta(hours=1)
    perp = pd.DataFrame({"close_time": hb["close_time"],
                         "perp_close": hb["close"].astype(float)})
    perp = perp[perp["close_time"] < A.CUTOFF].sort_values("close_time").reset_index(drop=True)
    cm = A.load_venue_closes("cm_BTCUSD_*_1h.parquet")
    um = A.load_venue_closes("um_BTCUSDT_*_1h.parquet")
    q_um = A.venue_hourly_qb(um, perp)
    q_cm = A.venue_hourly_qb(cm, perp)
    qb = q_um["qb"].to_numpy(float).copy()
    fill = ~np.isfinite(qb)
    qb[fill] = q_cm["qb"].to_numpy(float)[fill]
    C = pd.DatetimeIndex(pd.to_datetime(perp["close_time"], utc=True))
    c4 = pd.date_range(start=A.GRID_START, end=A.CUTOFF, freq="4h", tz="UTC")
    c4 = c4[c4 < A.CUTOFF]
    qb_by_c = dict(zip(C.asi8, qb))
    c4n = c4.asi8
    qb4 = np.array([qb_by_c.get(t, np.nan) for t in c4n], dtype=float)
    grid = pd.date_range(start=A.GRID_START, end=A.CUTOFF, freq="4h", tz="UTC")
    grid = grid[grid < A.CUTOFF]
    gns = grid.asi8
    lag = np.int64(A.LAG24.total_seconds() * 1e9)
    grid_mom = A.basis_at(c4n, qb4, gns) - A.basis_at(c4n, qb4, gns - lag)
    return perp, cm, um, c4, qb4, grid, grid_mom


@pytest.fixture(scope="module")
def build():
    return _build_full()


def test_multiplier_mapping_boundaries():
    p20 = -0.01
    sym = np.array(["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ETHUSDT", "XRPUSDT"])
    mom = np.array([-0.5, np.nan, -0.01, -0.0100001, 3.0, -0.01, -1.0], dtype=float)
    m = A.assign_mult(sym, mom, p20)
    # market-wide: BTC throttled too; NaN -> 1.0; == p20 tie -> 1.0; strictly below -> 0.5
    assert list(m) == [0.5, 1.0, 1.0, 0.5, 1.0, 1.0, 0.5]


def test_decision_counts_match():
    r = _results()
    n_gain = sum(1 for y in r["years"] if y["gain_pass"])
    n_loyo = sum(1 for L in r["loyo"] if L["pass"])
    n_tail = sum(1 for y in r["years"] if y["tail_pass"])
    assert r["decision"]["gain_sequential"] == f"{n_gain}/5" == "2/5"
    assert r["decision"]["loyo_gain"] == f"{n_loyo}/5" == "3/5"
    assert r["decision"]["tail_not_worse"] == f"{n_tail}/5" == "1/5"
    assert r["decision"]["promising"] is False


def test_gain_signs_match_harness():
    """Stored per-year gains equal an independent harness5.score recomputation."""
    d = H5.load()
    d["T"] = pd.to_datetime(d["T"], utc=True)
    feats = pd.read_parquet(OC / "features_idea6.parquet")
    key = feats[["T", "sym", "x1", "mom"]].drop_duplicates()
    d = d.merge(key, left_on=["T", "sym", "x1"], right_on=["T", "sym", "x1"], how="left")
    assert d.loc[d["sym"].isin(MAJORS) & d["x1"].isin(R2), "mom"].notna().all()
    r = _results()
    size = np.full(len(d), np.nan)
    is_r2 = d["sym"].isin(MAJORS) & d["k"].isin(R2) & d["size_dep"].notna()
    for k, a0 in enumerate(ANCHORS):
        te = ((d["T"] >= a0) & (d["T"] < a0 + YEAR_LEN) & is_r2).to_numpy()
        m = A.assign_mult(d["sym"].to_numpy(dtype=object)[te],
                          d["mom"].to_numpy(float)[te], r["years"][k]["p20"])
        size[te] = d["size_dep"].to_numpy()[te] * m
    got = H5.score(d, size, name="check")
    for k, yr in enumerate(got["years"]):
        assert yr["gain"] == pytest.approx(r["years"][k]["gain"])
        assert yr["worst_day_new"] == pytest.approx(r["years"][k]["worst_day_new"])
        assert yr["S_new"] == pytest.approx(r["years"][k]["S_new"])


def test_cutoffs_causal(build):
    """Cut-offs equal strictly-previous bar-pool quantiles; pools exclude the test span."""
    _, _, _, _, _, grid, grid_mom = build
    r = _results()
    gns = grid.asi8
    for k, a0 in enumerate(ANCHORS):
        pool = grid_mom[(gns < int(a0.value)) & np.isfinite(grid_mom)]
        assert len(pool) == r["years"][k]["n_train_bars"]
        assert grid[gns < int(a0.value)].max() < a0
        assert float(np.quantile(pool, 0.20)) == pytest.approx(r["years"][k]["p20"])
    # LOYO held-out 2022-23: training = bars in the other four year windows only
    hh = 1
    other = np.zeros(len(grid), bool)
    for k in range(5):
        if k != hh:
            other |= (np.asarray(grid >= ANCHORS[k])
                      & np.asarray(grid < ANCHORS[k] + YEAR_LEN))
    held = (np.asarray(grid >= ANCHORS[hh])
            & np.asarray(grid < ANCHORS[hh] + YEAR_LEN))
    assert not (other & held).any()
    tr = grid_mom[other & np.isfinite(grid_mom)]
    assert len(tr) == r["loyo"][hh]["n_train_bars"] == 8760
    assert float(np.quantile(tr, 0.20)) == pytest.approx(r["loyo"][hh]["p20"])


def test_basis_causal_truncate():
    """mom(T) from inputs truncated to close_time < Tcheck equals stored values;
    perturbing inputs at/after Tcheck leaves mom(T) for T <= Tcheck unchanged."""
    Tcheck = pd.Timestamp("2023-06-01", tz="UTC")
    h = pd.read_parquet(str(A.HOURLY), columns=["t", "close", "sym"])
    hb = h[h.sym == "BTCUSDT"][["t", "close"]].sort_values("t").reset_index(drop=True)
    hb["close_time"] = pd.to_datetime(hb["t"], utc=True) + pd.Timedelta(hours=1)
    perp = pd.DataFrame({"close_time": hb["close_time"],
                         "perp_close": hb["close"].astype(float)})
    perp = perp[perp["close_time"] < A.CUTOFF].reset_index(drop=True)
    cm = A.load_venue_closes("cm_BTCUSD_*_1h.parquet")
    um = A.load_venue_closes("um_BTCUSDT_*_1h.parquet")

    def build_qb(perp_f, cm_f, um_f):
        q_um = A.venue_hourly_qb(um_f, perp_f)
        q_cm = A.venue_hourly_qb(cm_f, perp_f)
        qb = q_um["qb"].to_numpy(float).copy()
        f = ~np.isfinite(qb)
        qb[f] = q_cm["qb"].to_numpy(float)[f]
        C = pd.DatetimeIndex(pd.to_datetime(perp_f["close_time"], utc=True))
        return C, qb

    C, qb_full = build_qb(perp, cm, um)
    # truncated rebuild: same expiry calendar, rows with close_time < Tcheck only
    tc_ns = int(Tcheck.value)
    perp_t = perp[pd.DatetimeIndex(perp["close_time"]).asi8 < tc_ns]
    cm_t = {e: df[pd.DatetimeIndex(df["close_time"]).asi8 < tc_ns] for e, df in cm.items()}
    um_t = {e: df[pd.DatetimeIndex(df["close_time"]).asi8 < tc_ns] for e, df in um.items()}
    Ct, qb_tr = build_qb(perp_t, cm_t, um_t)
    m = C.asi8 < tc_ns
    np.testing.assert_allclose(qb_tr, qb_full[m], rtol=1e-12, atol=0, equal_nan=True)

    feats = pd.read_parquet(OC / "features_idea6.parquet")
    feats["T"] = pd.to_datetime(feats["T"], utc=True)
    samp = feats[(feats["T"] <= Tcheck)].drop_duplicates("T").sort_values("T")
    samp = samp.iloc[[0, len(samp) // 2, len(samp) - 1]]
    # mom from the truncated rebuild at sampled T equals stored features
    c4 = pd.date_range(start=A.GRID_START, end=A.CUTOFF, freq="4h", tz="UTC")
    c4 = c4[c4 < A.CUTOFF]
    qb_by_c = dict(zip(Ct.asi8, qb_tr))
    qb4t = np.array([qb_by_c.get(t, np.nan) for t in c4.asi8], dtype=float)
    lag = np.int64(A.LAG24.total_seconds() * 1e9)
    Tns = pd.DatetimeIndex(samp["T"]).asi8
    mom_t = A.basis_at(c4.asi8, qb4t, Tns) - A.basis_at(c4.asi8, qb4t, Tns - lag)
    np.testing.assert_allclose(mom_t, samp["mom"].to_numpy(float),
                               rtol=1e-9, atol=0, equal_nan=True)
    # perturbation at/after Tcheck is effective somewhere but invisible at sampled T
    perp_p = perp.copy()
    pm = pd.DatetimeIndex(perp_p["close_time"]).asi8 >= tc_ns
    assert bool(pm.any())
    perp_p.loc[pm, "perp_close"] = perp_p.loc[pm, "perp_close"] * 2.0
    cm_p = {e: df.copy() for e, df in cm.items()}
    for e, df in cm_p.items():
        dm = pd.DatetimeIndex(df["close_time"]).asi8 >= tc_ns
        df.loc[dm, "close"] = df.loc[dm, "close"] * 2.0
    Cp, qb_pt = build_qb(perp_p, cm_p, um)
    assert np.isfinite(qb_pt[pd.DatetimeIndex(Cp).asi8 >= tc_ns]).any()
    assert (qb_pt[pd.DatetimeIndex(Cp).asi8 >= tc_ns]
            != qb_full[pd.DatetimeIndex(C).asi8 >= tc_ns]).any()
    qb_byc = dict(zip(Cp.asi8, qb_pt))
    qb4p = np.array([qb_byc.get(t, np.nan) for t in c4.asi8], dtype=float)
    mom_p = A.basis_at(c4.asi8, qb4p, Tns) - A.basis_at(c4.asi8, qb4p, Tns - lag)
    np.testing.assert_allclose(mom_p, samp["mom"].to_numpy(float),
                               rtol=1e-12, atol=0, equal_nan=True)


def test_mom_lag_synthetic():
    """Strict-< sampling + 24h lag + NaN rules on a hand-built 4h series."""
    c4 = pd.date_range("2021-01-01", periods=12, freq="4h", tz="UTC")
    qb4 = np.arange(12, dtype=float)  # 1.0 per 4h bar
    cns = c4.asi8
    lag = np.int64(pd.Timedelta(hours=24).total_seconds() * 1e9)
    T = np.array([c4[6].value, c4[7].value], dtype=np.int64)
    # basis(T) = qb4 at last close < T = qb4[5] = 5.0; basis(T-24h) = qb4 at last close < T-24h
    b = A.basis_at(cns, qb4, T)
    assert list(b) == [5.0, 6.0]
    mom = b - A.basis_at(cns, qb4, T - lag)
    # T-24h of c4[6] = c4[0]; last close strictly < c4[0] does not exist -> NaN
    assert np.isnan(A.basis_at(cns, qb4, T - lag)[0])
    assert np.isnan(mom[0])
    # c4[7] - 24h = c4[1]; last close < c4[1] is c4[0] = 0.0
    assert A.basis_at(cns, qb4, T - lag)[1] == 0.0
    assert mom[1] == pytest.approx(6.0 - 0.0)
    # exact-boundary: query equal to a close never uses that close
    assert A.basis_at(cns, qb4, np.array([c4[3].value]))[0] == 2.0


def test_universe_counts():
    r = _results()
    assert [y["n"] for y in r["years"]] == [990, 1045, 1330, 989, 1144]
    assert all(y["coverage"] == 1.0 for y in r["years"])
    feats = pd.read_parquet(OC / "features_idea6.parquet")
    feats["T"] = pd.to_datetime(feats["T"], utc=True)
    assert bool((feats["T"] < CUTOFF).all())
    assert bool(((feats["T"].dt.hour % 4 == 0) & (feats["T"].dt.minute == 0)).all())
    assert [int(((feats["T"] >= a0) & (feats["T"] < a0 + YEAR_LEN)
                 & feats["size_dep"].notna()).sum()) for a0 in ANCHORS] == [990, 1045, 1330, 989, 1144]
    assert set(feats["mult"].dropna().unique()) <= {0.5, 1.0}


def test_no_1m_and_cutoff():
    src = (OC / "analyze_idea6.py").read_text().lower()
    for banned in ("btc_intraday", "majors_intraday", "alts2020_intraday",
                   "klines_1m", "1m_20", "minute_0", "premium_1m"):
        assert banned not in src, banned
    assert "qbasis_20261003" in src and "hourly_ext" in src
    h = pd.read_parquet(str(A.HOURLY), columns=["t", "sym"])
    hb = h[h.sym == "BTCUSDT"]["t"]
    assert (pd.to_datetime(hb, utc=True) + pd.Timedelta(hours=1)).max() <= CUTOFF
    feats = pd.read_parquet(OC / "features_idea6.parquet", columns=["T"])
    assert pd.to_datetime(feats["T"], utc=True).max() < CUTOFF
