"""Tests for oc_recent: diagnostic integrity (no simulation, fast)."""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REC = ROOT / "research/tournament/oc_recent"
KPI = ROOT / "research/tournament/oc_kpi"


def _res():
    return json.loads((REC / "results.json").read_text())


def _kpi():
    return json.loads((KPI / "results.json").read_text())


def test_files_present():
    for f in ("PLAN.md", "analyze_recent.py", "results.json", "REPORT.md"):
        assert (REC / f).exists(), f


def test_plan_predates_results():
    assert (REC / "PLAN.md").stat().st_mtime <= (REC / "results.json").stat().st_mtime


def test_pooled_matches_oc_kpi():
    r, k = _res(), _kpi()
    assert r["data"]["pooled_book"] == k["win_rates"]["pooled"]["n_book"] == 4955
    assert r["data"]["pooled_rungs"] == k["win_rates"]["pooled"]["n_rungs"] == 21389
    for y, ky in zip(r["per_year_sleeve"], k["win_rates"]["per_year"]):
        assert y["book_long"]["n"] + y["book_short"]["n"] == ky["n_book"]
        assert (y["dip"]["exits"]["rung_sl"] + y["dip"]["exits"]["rung_tp"]
                + y["dip"]["exits"]["rung_timeout"]) == ky["n_rungs"]
        assert y["dip"]["win"] == ky["win_rungs"]
        n = ky["n_book"] + ky["n_rungs"]
        assert y["book_long"]["n"] + y["book_short"]["n"] + sum(
            y["dip"]["exits"].values()) == n


def test_coin_split_sums_to_sleeve():
    r = _res()
    for y in r["per_year_sleeve"]:
        rows = [c for c in r["per_year_sleeve_coin"] if c["year"] == y["year"]]
        assert len(rows) == 5
        assert sum(c["book_long"]["n"] for c in rows) == y["book_long"]["n"]
        assert sum(c["book_short"]["n"] for c in rows) == y["book_short"]["n"]
        assert sum(c["dip"]["n"] for c in rows) == y["dip"]["n"]
        for c in rows:
            e = c["dip"]["exits"]
            assert e["rung_sl"] + e["rung_tp"] + e["rung_timeout"] == c["dip"]["n"]


def test_dip_months_sum_to_pooled():
    r = _res()
    pm = r["dip_per_fill_month"]
    assert sum(m["fills"] for m in pm) == r["data"]["pooled_rungs"]
    assert [m["month"] for m in pm] == sorted(m["month"] for m in pm)
    for m in pm:
        e = m["exits"]
        assert e["rung_sl"] + e["rung_tp"] + e["rung_timeout"] == m["fills"]


def test_monthly_path_verbatim():
    r, k = _res(), _kpi()
    assert r["monthly_path"]["monthly"] == [[m, v] for m, v in k["equity"]["monthly"]]
    assert [y["R"] for y in r["year_R"]] == [y["R"] for y in k["equity"]["years"]]


def test_no_data_at_or_after_cut():
    r = _res()
    assert r["checks"]["max_event_t_below_cut"]
    cut = pd.Timestamp("2026-09-24", tz="UTC")
    assert pd.Timestamp(r["checks"]["max_event_t"]) < cut
    ev = pd.read_parquet(KPI / "events_s0.parquet", columns=["t"])
    assert pd.to_datetime(ev["t"], utc=True).max() < cut
