"""Tests for the v154 descriptive error analysis.

The full rebuild (three member books) takes tens of minutes, so these tests
run against research/diagnostics/v154_error_analysis/summary.json +
REPORT.md produced by analyze.py. They skip with a clear message when the
artifacts are absent (run analyze.py first).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

HERE = Path(__file__).parent
DIAG = HERE.parent / "research" / "diagnostics" / "v154_error_analysis"
SUMMARY = DIAG / "summary.json"
REPORT = DIAG / "REPORT.md"
ANALYZE = DIAG / "analyze.py"
V154_RESULT = HERE.parent / "research" / "parallel" / "rounds" / "parallel-20260906-r2" / "v154" / "v154_result.json"

TOL = 0.01


def _load_summary():
    if not SUMMARY.exists():
        pytest.skip(f"{SUMMARY} absent - run analyze.py first (tens of minutes)")
    return json.loads(SUMMARY.read_text())


def test_analyze_imports_leader_modules():
    src = ANALYZE.read_text()
    for sym in ("books_v142", "books_with_options", "books_coinbase", "summarize"):
        assert sym in src, f"analyze.py must use the leader module entry point {sym}"
    assert "train_predict" not in src, "analyze.py must not reimplement model training"
    assert "pre-registered" in src, "analyze.py must carry the descriptive-only disclaimer"


def test_reconstruction_matches_v154_primary():
    s = _load_summary()
    ref = json.loads(V154_RESULT.read_text())["primary_t25_governed"]
    assert abs(s["reconstruction"]["monthly_pct"] - ref["monthly_pct"]) <= TOL
    assert abs(s["reconstruction"]["full_path_dd"] - ref["full_path_dd"]) <= TOL
    assert s["reconstruction"]["passed"] is True


def test_decomposition_sums_equal_totals():
    s = _load_summary()
    t = s["totals"]
    close = lambda a, b: abs(a - b) < 1e-9  # noqa: E731

    assert close(t["gross"] - t["cost"] - t["funding"] + t["carry_net"], t["net"])

    a = s["by_asset"]
    assert close(sum(r["gross"] for r in a), t["gross"])
    assert close(sum(r["cost"] for r in a), t["cost"])
    assert close(sum(r["funding"] for r in a), t["funding"])
    assert close(sum(r["net_ex_carry"] for r in a) + t["carry_net"], t["net"])

    m = s["by_member"]
    assert close(sum(r["gross"] for r in m), t["gross"])
    assert close(sum(r["net_standalone"] for r in m)
                 - s["member_cost_netting_residual"] - s["member_funding_netting_residual"], t["net"])

    for mm in ("A", "B", "D"):
        part = sum(r["gross"] for r in s["by_book"] if r["member"] == mm)
        ref = next(r["gross"] for r in m if r["member"] == mm)
        assert close(part, ref)

    ls = s["long_short"]
    assert close(ls["long"]["gross"] + ls["short"]["gross"], t["gross"])
    assert close(ls["long"]["net"] + ls["short"]["net"], t["net"])

    for tbl in (s["by_ribbon"], s["by_vol_tercile"]["rows"], s["by_year"]):
        assert close(sum(r["gross"] for r in tbl), t["gross"])
        assert close(sum(r["net"] for r in tbl), t["net"])

    for e in s["episodes"]:
        assert close(sum(e["by_asset_gross"].values()), e["window_gross"])
        assert close(sum(e["by_member_gross"].values()), e["window_gross"])
        assert close(sum(e["by_book_gross"].values()), e["window_gross"])
        assert close(e["long_gross"] + e["short_gross"], e["window_gross"])
    assert len(s["episodes"]) == 5


def test_report_disclaimer_and_tables():
    if not REPORT.exists():
        pytest.skip(f"{REPORT} absent - run analyze.py first (tens of minutes)")
    rep = REPORT.read_text()
    assert "pre-registered" in rep and "prospective" in rep
    assert "PASSED" in rep
