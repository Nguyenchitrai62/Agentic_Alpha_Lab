"""Tests for oc_kpi: reporting integrity of the R2B1D17BF goal metrics.

Fast checks only (no simulation): file presence/ordering, equity replica
match flags, monthly compounding, year partition cover, win-rate bounds,
cross-checks against v411_result.json.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
KPI = ROOT / "research/tournament/oc_kpi"
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"


def _res():
    return json.loads((KPI / "results.json").read_text())


def test_files_present():
    for f in ("PLAN.md", "run_kpi.py", "run_kpi_trades.py", "compute_kpi.py",
              "results.json", "REPORT.md", "results_equity.json"):
        assert (KPI / f).exists(), f
    for s in range(4):
        assert (KPI / f"events_s{s}.parquet").exists()
        assert (KPI / f"barsum_s{s}.parquet").exists()
        assert (KPI / f"check_s{s}.json").exists()


def test_plan_predates_results():
    assert (KPI / "PLAN.md").stat().st_mtime <= (KPI / "results.json").stat().st_mtime


def test_replica_match_1e9():
    for s in range(4):
        c = json.loads((KPI / f"check_s{s}.json").read_text())
        assert c["match_1e9"] and c["max_rel_diff"] <= 1e-9
        assert c["overlap"] == c["ref_bars"] == 10944


def test_monthly_compounds_to_net():
    r = _res()["equity"]
    assert r["n_months"] == 61 and len(r["monthly"]) == 61
    arr = np.array([v for _, v in r["monthly"]], float) / 100
    # rounded monthly table compounds to within rounding drift of the net
    assert abs(float(np.prod(1 + arr) - 1) - r["full_path"]["net_pct"] / 100) < 0.02
    # exact unrounded compounding residual recorded at compute time
    assert abs(_res()["checks"]["trade_months_compound_vs_net"]) < 1e-9
    assert 0 <= r["share_ge5_all"] <= 1 and 0 <= r["share_ge0_all"] <= 1
    assert r["longest_losing_streak_months"] == 2


def test_years_match_v411():
    v411 = json.loads((RD / "v411" / "v411_result.json").read_text())["rows"]["R2B1D17BF"]
    yrs = _res()["equity"]["years"]
    assert len(yrs) == 5
    for y, (rv, dd) in zip(yrs, v411["years"]):
        assert abs(y["R"] - rv) < 1e-9 and abs(y["DD_1m"] - dd) < 1e-9
    assert _res()["equity"]["full_path"]["DD_gate"] == v411["full_path_dd"]


def test_year_partition_covers_all_trades():
    r = _res()["win_rates"]
    p = r["pooled"]
    assert sum(y["n_all"] for y in r["per_year"]) == p["n_all"] == 26344
    assert sum(y["n_book"] for y in r["per_year"]) == p["n_book"] == 4955
    assert sum(y["n_rungs"] for y in r["per_year"]) == p["n_rungs"] == 21389
    for y in r["per_year"]:
        for k in ("win_book", "win_rungs", "win_all"):
            assert 0 <= y[k] <= 1
        e = y["rung_exits"]
        assert e["rung_sl"] + e["rung_tp"] + e["rung_timeout"] == y["n_rungs"]


def test_rung_exits_add_up():
    r = _res()["win_rates"]["pooled"]["rung_exits"]
    assert r["rung_sl"] + r["rung_tp"] + r["rung_timeout"] == _res()["win_rates"]["pooled"]["n_rungs"]
    assert r == {"rung_sl": 924, "rung_tp": 10761, "rung_timeout": 9704}


def test_no_data_at_or_after_cut():
    cut = pd.Timestamp("2026-09-24", tz="UTC")
    for s in range(4):
        ev = pd.read_parquet(KPI / f"events_s{s}.parquet", columns=["t"])
        assert pd.to_datetime(ev["t"], utc=True).max() < cut


def test_exposure_bounds():
    e = _res()["exposure"]
    assert 0 <= e["n_book_avg"] <= 5 and e["n_book_max"] == 5
    assert 0 < e["gross_book_avg"] < e["gross_book_max"]
    assert e["total_avg_open"] >= e["n_book_avg"]
    assert e["n_bars"] == 4 * 10944
