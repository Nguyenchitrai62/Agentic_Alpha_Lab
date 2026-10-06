"""Tests for oc_ddanat4p (light: no simulation, checks results.json + PLAN ordering)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "research" / "tournament" / "oc_ddanat4p"


def _res():
    return json.loads((D / "results.json").read_text())


def test_files_exist():
    for f in ("PLAN.md", "run_mix.py", "run_phase.py", "results.json", "REPORT.md",
              "mix_episodes.json", "attrib_s0.json", "attrib_s1.json",
              "attrib_s2.json", "attrib_s3.json"):
        assert (D / f).exists(), f


def test_plan_predates_results():
    assert (D / "PLAN.md").stat().st_mtime <= (D / "results.json").stat().st_mtime


def test_gate_numbers():
    r = _res()
    assert r["variant"] == "R2B1D17BF"
    assert r["gate"]["yearly_DD"] == [12.42, 16.23, 18.33, 8.26, 12.81]
    assert r["gate"]["full_path_DD"] == 16.9
    assert r["ep_1833"]["dd_1m_pct"] == 18.33
    assert len(r["reset_episodes"]) == 4


def test_replica_bit_exact():
    r = _res()
    for s in range(4):
        assert abs(r["replica_checks"][f"s{s}"]["rel_diff"]) < 1e-9


def test_crash_attribution_schema():
    r = _res()
    c = r["crash_attrib"]
    assert set(c) == {"s0", "s1", "s2", "s3"}
    for s in ("s0", "s1", "s2", "s3"):
        w = c[s]
        assert w["window"] == ["2024-01-03 11:00:00+00:00", "2024-01-03 16:00:00+00:00"]
        assert w["book_short"] == 0.0
        assert set(w["per_coin"]) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
    # gate is dip-driven on s1-s3, negligible on s0
    assert c["s1"]["dip"] < -15 and c["s2"]["dip"] < -15 and c["s3"]["dip"] < -15
    assert abs(c["s0"]["dip"]) < 1.0
    # async: s0 own DD small, s1-s3 large
    ph = {p["phase"]: p["dd_pct"] for p in r["ep_1833"]["phases"]}
    assert ph[0] < 10 and min(ph[1], ph[2], ph[3]) > 15
