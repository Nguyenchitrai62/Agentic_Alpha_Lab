"""Tests for oc_crashfreq (light: checks results.json + PLAN ordering, no simulation)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "research" / "tournament" / "oc_crashfreq"


def _res():
    return json.loads((D / "results.json").read_text(encoding="utf-8"))


def test_files_exist():
    for f in ("PLAN.md", "compute_crashfreq.py", "results.json", "REPORT.md"):
        assert (D / f).exists(), f


def test_plan_predates_results():
    assert (D / "PLAN.md").stat().st_mtime <= (D / "results.json").stat().st_mtime


def test_event_schema_and_threshold():
    r = _res()
    assert r["variant"] == "R2B1D17BF"
    assert r["n_events_ge3"] == len(r["events"]) == 82
    prev = -1e18
    for e in r["events"]:
        assert e["dip_loss"] <= -3.0
        assert e["dip_loss"] >= prev - 1e-9  # sorted worst-first (ascending numeric)
        prev = e["dip_loss"]
        assert e["phase"] in (0, 1, 2, 3)
        assert e["n_stops"] >= 0 and e["n_exits"] >= e["n_stops"]
        assert set(e["by_kind"]) >= {"rung_sl", "rung_tp", "rung_timeout"}
        assert e["btc_r4h"] is not None
        assert set(e["other_wall"]) == {f"s{p}" for p in range(4) if p != e["phase"]}
        t = pd.Timestamp(e["bar_end"])
        assert pd.Timestamp("2021-09-24", tz="UTC") < t <= pd.Timestamp("2026-09-24", tz="UTC")
        assert int(t.hour % 4) == int(e["phase"] % 4)


def test_crash_bars_reproduced():
    r = _res()
    lut = {(e["phase"], e["bar_end"][:16]): e["dip_loss"] for e in r["events"]}
    assert abs(lut[(1, "2024-01-03 13:00")] - (-17.473)) < 0.01
    assert abs(lut[(2, "2024-01-03 14:00")] - (-21.701)) < 0.01
    assert abs(lut[(3, "2024-01-03 15:00")] - (-21.012)) < 0.01


def test_yearly_and_top15_and_concentration():
    r = _res()
    tot = sum(y["ge3"] for y in r["yearly_counts"])
    assert tot == r["n_events_ge3"]
    assert [y["ge3"] for y in r["yearly_counts"]] == [22, 24, 21, 7, 8]
    assert len(r["top15"]) == 15
    assert r["top15"][0]["dip_loss"] <= r["top15"][-1]["dip_loss"]
    assert r["top15"][0]["bar_end"][:16] == "2024-01-03 14:00"
    c = r["concentration"]
    assert c["n_negative_bars"] == 840
    assert abs(c["sum_negative_pp"] - (-869.217)) < 1.0
    assert abs(c["top10_fraction"] - c["top10_sum_pp"] / c["sum_negative_pp"]) < 2e-4
    assert abs(c["top10_fraction"] - 0.1588) < 0.005
    t = r["type15"]
    assert t["threshold"] == -15.0 and t["n_bars"] == 3 and t["dates"] == ["2024-01-03"]


def test_report_has_required_sections():
    rep = (D / "REPORT.md").read_text(encoding="utf-8")
    assert "VERDICT:" in rep
    assert "2024-01-03" in rep
    assert "top-10" in rep or "top 10" in rep.lower()
    assert "2021-09-24..2022-09-24" in rep
