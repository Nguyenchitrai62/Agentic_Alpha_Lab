"""Tests for oc_ddanat_g2 (light: no simulation, checks results.json + PLAN ordering)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "research" / "tournament" / "oc_ddanat_g2"


def _res():
    return json.loads((D / "results.json").read_text())


def test_files_exist():
    for f in ("PLAN.md", "run_mix.py", "run_phase.py", "make_results.py",
              "results.json", "REPORT.md", "mix_episodes.json",
              "attrib_s0.json", "attrib_s1.json",
              "attrib_s2.json", "attrib_s3.json"):
        assert (D / f).exists(), f


def test_plan_predates_results():
    assert (D / "PLAN.md").stat().st_mtime <= (D / "results.json").stat().st_mtime


def test_gate_numbers():
    r = _res()
    assert r["variant"] == "R2B1D17BFG2"
    assert r["gate"]["yearly_DD"] == [10.86, 16.91, 15.81, 8.27, 12.9]
    assert r["gate"]["full_path_DD"] == 16.82
    assert r["ep_1691"]["dd_1m_pct"] == 16.91
    assert len(r["reset_episodes"]) == 4
    assert len(r["episodes"]) == 4


def test_replica_bit_exact():
    r = _res()
    for s in range(4):
        assert abs(r["replica_checks"][f"s{s}"]["rel_diff"]) <= 1e-9
        assert r["replica_checks"][f"s{s}"]["n_events"] == \
            r["replica_checks"][f"s{s}"]["kpi_n_events"]


def test_gate_episode_attribution_schema():
    r = _res()
    ep = r["episodes"][0]
    assert ep["window"][0].startswith("2023-04-17")
    assert ep["mixed_dd_1m"] == 16.91
    # synchronous: all phases > 50% of mixed
    for p in ep["phases"]:
        assert p["dd_pct"] > 0.5 * ep["mixed_dd_1m"]
    for s in ("s0", "s1", "s2", "s3"):
        w = ep["per_phase"][s]
        assert set(w["per_coin"]) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
        assert set(w["dip_exit_kinds"]) >= {"rung_sl", "rung_tp"}
        # linear sums track the phase eq move within 2pp
        assert abs(w["attrib_sum"] - w["eq_change_pct"]) < 2.0
    # gate is book-long + dip on every phase, shorts offset (>= 0)
    for s in ("s0", "s1", "s2", "s3"):
        w = ep["per_phase"][s]
        assert w["book_long"] < -5 and w["dip"] < -5 and w["book_short"] >= 0


def test_crash_window_still_present_but_smaller():
    r = _res()
    ep = r["episodes"][2]
    assert ep["window"][0].startswith("2024-01-03")
    assert ep["mixed_dd_1m"] == 15.81
    # async: s0 sits out
    assert abs(ep["per_phase"]["s0"]["dip"]) < 1.0
    assert ep["per_phase"]["s1"]["dip"] < -15


def test_no_data_at_or_after_cut():
    cut = pd.Timestamp("2026-09-24", tz="UTC")
    mix = json.loads((D / "mix_episodes.json").read_text())
    for ep in mix["reset_episodes"] + mix["full_episodes"]:
        assert pd.Timestamp(ep["trough"]) < cut
