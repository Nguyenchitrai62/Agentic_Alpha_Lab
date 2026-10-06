"""Blind-audit test for oc_capacity (reads JSONs only; fast, no parquet)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
REP = ROOT / "research/tournament/audit_capacity/replication.json"
ORIG = ROOT / "research/tournament/oc_capacity/results.json"


def _load():
    rep = json.loads(REP.read_text())
    orig = json.loads(ORIG.read_text())
    return rep, orig


def test_replication_exists():
    assert REP.exists(), "replication.json must be saved (blind, before comparison)"


def test_coverage_matches():
    rep, orig = _load()
    n_matched = sum(v["n_matched"] for v in rep["symbols"].values())
    n_bad = sum(v["n_badprint"] for v in rep["symbols"].values())
    assert n_matched == orig["coverage"]["n_matched"] == 41981
    assert n_bad == orig["coverage"]["n_badprint_below_p05"] == 1618


def test_shares_within_1pp():
    rep, orig = _load()
    key = {"share_r1_gt_1pct": "gt1_1pct", "share_r1_gt_5pct": "gt5_1pct",
           "share_r1_gt_20pct": "gt20_1pct", "share_r02_gt_1pct": "gt1_02pct",
           "share_r02_gt_5pct": "gt5_02pct", "share_r02_gt_20pct": "gt20_02pct"}
    for E in ("10000", "50000", "100000"):
        for sym, cells in rep["totals"][E].items():
            ofrac = orig["per_symbol"][E][sym]["frac"]
            assert cells["n"] == orig["per_symbol"][E][sym]["n"]
            for mine_k, orig_k in key.items():
                assert abs(cells[mine_k] - ofrac[orig_k]["share"]) <= 0.01, (E, sym, mine_k)


def test_drag_within_0_05pp():
    rep, orig = _load()
    for E in ("10000", "50000", "100000"):
        assert abs(rep["drag"][E]["drag_pp_per_month"] - orig["haircut"][E]["drag_pp_month"]) <= 0.05, E


def test_materiality_calls_agree():
    rep, _ = _load()
    assert rep["drag"]["10000"]["material_ge_0_5pp"] is False
    assert rep["drag"]["50000"]["material_ge_0_5pp"] is False
    assert rep["drag"]["100000"]["material_ge_0_5pp"] is True
