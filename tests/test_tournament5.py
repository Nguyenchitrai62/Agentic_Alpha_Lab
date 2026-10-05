"""Tournament5 extension tests: causality + alignment of the ext inputs and 5-fold re-scores.

Covers: no market data at/after 2026-09-24 is used; overlap with the original inputs is identical;
recorded causality checks passed; ext artifacts align with harness5.load()/folds; first-4-fold decisions
reproduce the original scored sizes/decisions; scores5 first-4-year gains reproduce the originals.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "research/tournament/ext"
sys.path.insert(0, str(EXT))
import harness5 as H5

CUT = pd.Timestamp("2026-09-24", tz="UTC")
CUT_OLD = pd.Timestamp("2025-09-24", tz="UTC")


def _load(name):
    return json.loads((EXT / name).read_text())


def test_no_data_at_or_after_cut():
    fills = pd.read_parquet(EXT / "fills_U_ext.parquet", columns=["t_fill", "t_exit"])
    assert fills.t_fill.max() < CUT and fills.t_exit.max() < CUT + pd.Timedelta(days=40)
    hourly = pd.read_parquet(EXT / "hourly_ext.parquet", columns=["t"])
    assert hourly.t.max() < CUT and (hourly.t >= CUT).sum() == 0
    chk = _load("features_check.json")
    assert chk["hourly_rows_after_cut"] == 0


def test_overlap_identical():
    fc = _load("fills_check.json")
    assert fc["only_old"] == 0 and fc["only_new"] == 0 and fc["same_order_exact"]
    assert all(v["max_abs"] == 0.0 and v["nan_mismatch"] == 0 for v in fc["diff"].values() if isinstance(v, dict) and "max_abs" in v)
    feat = _load("features_check.json")
    assert feat["old_rows_missing_in_ext"] == 0
    assert all(v["max_abs"] == 0.0 and v["nan_mismatch"] == 0 for v in feat["bar_open_diff"].values())
    assert feat["hourly_old_missing_in_ext"] == 0
    assert all(v == 0.0 for v in feat["hourly_maxdiff"].values())
    mc = _load("market_check.json")
    assert mc["old_rows_missing_in_new"] == 0 and mc["worst_max_abs"] == 0.0 and mc["total_nan_mismatch"] == 0


def test_recorded_causality_passed():
    feat = _load("features_check.json")
    assert feat["causality_passed"] and len(feat["causality_rows"]) == 20 and feat["causality_max_abs_diff"] == 0.0
    log = (EXT / "log_market.txt").read_text()
    assert "causality check passed" in log


def test_market_build_ignores_future_hours():
    """Genuine causality: appending future hourly rows must not change features at earlier T."""
    from build_market_features_ext import build
    rng = np.random.default_rng(3)
    syms = ["BTCUSDT"] + [f"C{i:02d}" for i in range(8)]
    t0 = pd.Timestamp("2023-01-01", tz="UTC")
    idx = pd.date_range(t0, periods=400, freq="1h")
    rows = []
    for s in syms:
        px = 100 * np.exp(np.cumsum(rng.normal(0, 0.005, len(idx))))
        rows.append(pd.DataFrame({"t": idx, "open": px, "high": px * 1.002, "low": px * 0.998,
                                  "close": px, "sym": s}))
    hourly = pd.concat(rows, ignore_index=True)
    req = pd.DataFrame({"T": [t0 + pd.Timedelta(hours=300), t0 + pd.Timedelta(hours=350)], "sym": ["C01", "BTCUSDT"]})
    base = build(hourly, req)
    extra = []
    idx2 = pd.date_range(idx.max() + pd.Timedelta(hours=1), periods=50, freq="1h")
    for s in syms:
        px = 100 * np.exp(np.cumsum(rng.normal(0, 0.005, len(idx2))))
        extra.append(pd.DataFrame({"t": idx2, "open": px, "high": px * 1.002, "low": px * 0.998,
                                   "close": px, "sym": s}))
    extended = pd.concat([hourly] + extra, ignore_index=True)
    again = build(extended, req)
    assert base.shape == again.shape
    assert ((base.isna()) == (again.isna())).all().all()
    assert np.nanmax(np.abs(base.to_numpy(float) - again.to_numpy(float))) < 1e-9
    # per-row truncation at T gives the identical row
    for i in range(len(req)):
        T = req["T"].iloc[i]
        one = build(hourly[hourly.t < T], req.iloc[[i]])
        a, b = one.to_numpy(float)[0], base.iloc[i].to_numpy(float)
        assert (np.isnan(a) == np.isnan(b)).all() and np.nanmax(np.abs(a - b)) < 1e-9


def test_ext_aligns_with_harness5():
    d = H5.load()
    assert (d.t_fill < H5.DEV_END).all()
    bo = pd.read_parquet(EXT / "bar_open_ext.parquet", columns=["j", "sym", "r"])
    assert len(bo) == len(d) and (bo.j.to_numpy() == d.j.to_numpy()).all() and (bo.sym.to_numpy() == d.sym.to_numpy()).all()
    mf = pd.read_parquet(EXT / "market_features_ext.parquet", columns=["T", "sym"])
    assert len(mf) == len(d) and (mf.sym.to_numpy() == d.sym.to_numpy()).all() and (mf["T"].to_numpy() == d["T"].to_numpy()).all()
    ns = [int(te.sum()) for _, _, _, te in H5.folds(d)]
    assert ns == [990, 1045, 1330, 989, 1144]
    # train/test discipline: train rows exit before anchor - 7d, test rows are majors R2 rungs inside the year
    for _, a0, tr, te in H5.folds(d):
        assert (d.t_exit[tr] < a0 - H5.EMBARGO).all()
        assert (d["T"][te] >= a0).all() and (d["T"][te] < a0 + pd.Timedelta(days=365)).all()
        assert d.sym[te].isin(H5.MAJORS).all() and d.k[te].isin(H5.R2).all()


def test_scores5_reproduce_first_four_years():
    cases = [("scores5_kelly_V2_meanvar.json", "kelly/score_V2_meanvar.json", "kelly5_overlap.json"),
             ("scores5_context_hgb_mono.json", "context/score_hgb_mono.json", "context5_overlap.json"),
             ("scores5_tp_v2_diff.json", "tp/score_v2_diff.json", "tp5_overlap.json")]
    for new, old, ov in cases:
        res = _load(new)
        ref = json.loads((ROOT / "research/tournament" / old).read_text())
        assert [r["year"] for r in res["years"]] == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
        for r5, ro in zip(res["years"][:4], ref["years"]):
            assert abs(r5["gain"] - ro["gain"]) < 5e-5 and r5["n"] == ro["n"] and r5["S_dep"] == ro["S_dep"]
        o = _load(ov)
        assert o["match_share_exact" if "match_share_exact" in o else "match_share_1e12"] == 1.0
        # graduation flag follows the harness5 rule
        gains = [r["gain"] for r in res["years"]]
        worst_d = min(r["worst_day_dep"] for r in res["years"])
        worst_n = min(r["worst_day_new"] for r in res["years"])
        expect = bool(sum(g > 0 for g in gains) >= H5.MIN_POS and sum(gains) > 0 and worst_n >= 1.2 * worst_d)
        assert res["graduates"] == expect


def test_decision_files_aligned():
    d = H5.load()
    sk = pd.read_parquet(EXT / "sizes5_kelly_V2.parquet", columns=["V2_meanvar", "sym", "T"])
    assert len(sk) == len(d) and (sk.sym.to_numpy() == d.sym.to_numpy()).all()
    assert ((sk.V2_meanvar.dropna() >= 0) & (sk.V2_meanvar.dropna() <= 2)).all()
    sc = pd.read_parquet(EXT / "sizes5_context_hgb_mono.parquet", columns=["hgb_mono", "sym", "T"])
    assert len(sc) == len(d) and set(sc.hgb_mono.dropna().unique()) <= {0.5, 1.0, 1.5}
    tp = pd.read_parquet(EXT / "tp5_v2_diff.parquet")
    assert set(tp.tp_new.unique()) <= {0.5, 1.0, 1.5} and len(tp) == 5498
