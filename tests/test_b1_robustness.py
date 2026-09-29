"""Checks for the B1 robustness diagnostic (candidate: 5m-close dip stops + 8-sigma native backstop)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "research/diagnostics/b1_robustness/b1_robustness.json"


def _load():
    with open(DATA) as fh:
        return json.load(fh)


def test_b1_base_reproduces_candidate():
    doc = _load()
    b = doc["rows"]["B1_base"]
    assert abs(b["monthly_dev4"] - 6.13) < 0.01
    assert abs(b["monthly_5y"] - 5.795) < 0.005
    assert abs(b["monthly_last_year"] - 4.464) < 0.005
    assert abs(b["gate_dd"] - 19.70) < 0.05
    assert b["losing_years"] == 0
    assert len(b["yearly"]) == 5


def test_o1_base_reproduces_deployed():
    doc = _load()
    o = doc["rows"]["O1_base"]
    assert abs(o["monthly_dev4"] - 5.777) < 0.003
    assert abs(o["monthly_5y"] - 5.436) < 0.003
    assert abs(o["monthly_last_year"] - 4.082) < 0.003
    assert abs(o["gate_dd"] - 19.65) < 0.05


def test_all_paired_rows_present():
    doc = _load()
    names = ["base", "cost_stress", "latency_15", "latency_30", "latency_60", "band_lo", "band_hi",
             "cool_3", "cool_12", "sleeve_0.16", "sleeve_0.20", "offset_0.15", "offset_0.40"]
    for n in names:
        assert f"O1_{n}" in doc["rows"], n
        assert f"B1_{n}" in doc["rows"], n
        for k in ("monthly_dev4", "monthly_5y", "monthly_last_year", "gate_dd", "losing_years",
                  "yearly", "win_rate_dev", "trades_dev"):
            assert k in doc["rows"][f"B1_{n}"], (n, k)
        assert len(doc["rows"][f"B1_{n}"]["yearly"]) == 5
    assert "B1_outage_backstop_only" in doc["rows"]
    assert "B1_close_1m" in doc["rows"]
    assert "B1_latency_close_plus5" in doc.get("skipped", {})


def test_cost_stress_is_worse_than_base_both():
    doc = _load()
    for prefix in ("O1", "B1"):
        base, stress = doc["rows"][f"{prefix}_base"], doc["rows"][f"{prefix}_cost_stress"]
        assert stress["monthly_dev4"] < base["monthly_dev4"]
        assert stress["monthly_5y"] < base["monthly_5y"]
