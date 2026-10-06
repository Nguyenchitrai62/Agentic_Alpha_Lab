"""Tests for oc_ddanat17 (light: no simulation, checks results.json + PLAN ordering)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "research" / "tournament" / "oc_ddanat17"


def _res():
    return json.loads((D / "results.json").read_text())


def test_files_exist():
    assert (D / "PLAN.md").exists()
    assert (D / "run_ddanat17.py").exists()
    assert (D / "results.json").exists()
    assert (D / "REPORT.md").exists()


def test_plan_predates_results():
    assert (D / "PLAN.md").stat().st_mtime <= (D / "results.json").stat().st_mtime


def test_replica_check():
    r = _res()
    assert r["variant"] == "R2B1D17BF" and r["phase"] == 0
    assert abs(r["checks"]["rel_diff"]) < 1e-9
    assert r["checks"]["n_rungs"] == 5466
    assert r["checks"]["n_attrib"] == 10944


def test_five_episodes():
    r = _res()
    eps = r["episodes"]
    assert len(eps) == 5
    for e in eps:
        assert e["dd_4h_pct"] > 0
        assert e["n_bars"] > 0
        assert set(e["per_coin"]) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
        tot = e["book_long"] + e["book_short"] + e["dip"]
        assert abs(tot - e["attrib_sum"]) < 0.01


def test_worst20_sorted():
    r = _res()
    w = r["worst20"]
    assert len(w) == 20
    losses = [x["loss_pct"] for x in w]
    assert losses == sorted(losses)
    assert all(x["loss_pct"] < 0 for x in w)
    for x in w:
        assert x["exit"] in ("rung_sl", "rung_tp", "rung_timeout")
        assert isinstance(x["n"], int) and x["n"] >= 0
