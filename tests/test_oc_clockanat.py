"""oc_clockanat tests: phase-3 2023 drawdown anatomy artifacts stay consistent."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/diagnostics/oc_clockanat"
RES = json.loads((OC / "results.json").read_text())
P3 = RES["phase3_2023"]


def test_artifacts_exist():
    assert (OC / "clockanat.py").exists()
    assert (OC / "REPORT.md").exists()
    assert (OC / "results.json").exists()


def test_gate_numbers_match_phasedisp():
    assert RES["strat"] == "R2B1D17BFG2" and RES["shift"] == 3
    assert P3["year_R"] == -2.431
    assert P3["dd_pct"] == 43.23
    assert P3["peak_eq"] == 1.3076 and P3["trough_marked"] == 0.7424
    assert pd.to_datetime(P3["peak_t"], utc=True) < pd.to_datetime(P3["trough_t"], utc=True)


def test_top10_days_complete_and_sorted():
    days = P3["top10_losing_days_p3"]
    assert len(days) == 10
    losses = [d["p3"] for d in days]
    assert losses == sorted(losses) and all(v < 0 for v in losses)
    for d in days:
        for k in ("date", "p3", "p0", "p1", "p2", "mix", "n_phases_neg"):
            assert k in d
        assert 0 <= d["n_phases_neg"] <= 4
    assert P3["mix_lost_on_n_of_10"] == sum(1 for d in days if d["mix"] < 0)


def test_book_dip_split_telescopes():
    s = RES["book_vs_dip_peak_to_trough"]
    assert abs(s["book_points"] + s["dip_points"] - s["total_points"]) < 1e-9
    w = RES["drawdown_close_window"]
    assert abs(s["total_points"] - w["close_drop_points"]) < 1e-9
    assert s["dip_points"] < s["book_points"] < 0  # dip dominates the bleed


def test_dip_losers_are_stops_with_depth_and_minutes():
    evs = RES["dip_top_losing_events"]
    assert len(evs) == 10
    for e in evs:
        assert e["exit_kind"] in ("rung_sl", "rung_tp", "rung_timeout")
        assert e["pts"] < 0 and e["ret_bps"] < 0
        assert 0 <= e["fill_minute"] < 240
        assert e["depth_sigma"] in (2.5, 3.0, 3.5, 4.0)
        assert pd.to_datetime(e["fill_t"], utc=True) < pd.to_datetime(e["exit_t"], utc=True)
    kinds = RES["dip_drawdown_exits_by_kind"]
    assert set(kinds) == {"rung_sl", "rung_tp", "rung_timeout"}
    assert sum(kinds.values()) >= RES["dip_n_losing_in_drawdown"]


def test_rerun_is_bit_identical_and_leak_free():
    assert RES["reproduction"]["max_abs_diff"] == 0.0
    assert RES["reproduction"]["n_common_bars"] > 2000
    assert pd.to_datetime(RES["trade_log_max_t"], utc=True) < pd.Timestamp("2025-09-24", tz="UTC")


def test_report_within_line_budget():
    lines = (OC / "REPORT.md").read_text().splitlines()
    assert len(lines) <= 60
    assert any("Ket luan" in ln for ln in lines)
