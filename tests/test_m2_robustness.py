"""Checks for the M2 MANUAL robustness diagnostic (v317 / v318 reference, book-only)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "research/diagnostics/m2_robustness/m2_robustness.json"


def _load():
    with open(DATA) as fh:
        return json.load(fh)


def test_m2_base_reproduces_candidate():
    doc = _load()
    b = doc["rows"]["M2_base"]
    assert abs(b["monthly_dev4"] - 3.011) < 0.01
    assert abs(b["monthly_5y"] - 3.16) < 0.01
    assert abs(b["monthly_last_year"] - 3.759) < 0.01
    assert abs(b["gate_dd"] - 20.57) < 0.05
    assert len(b["yearly"]) == 5


def test_g2_base_reproduces_reference():
    doc = _load()
    o = doc["rows"]["G2_base"]
    assert abs(o["monthly_dev4"] - 2.502) < 0.003
    assert abs(o["monthly_5y"] - 2.772) < 0.005
    assert abs(o["monthly_last_year"] - 3.859) < 0.005
    assert abs(o["gate_dd"] - 19.61) < 0.05


def test_all_paired_rows_present():
    doc = _load()
    names = ["base", "cost_stress", "latency_15", "latency_30", "latency_60", "latency_120",
             "missed_k6", "band_lo", "band_hi", "cool_3", "cool_12"]
    for n in names:
        assert f"M2_{n}" in doc["rows"], n
        assert f"G2_{n}" in doc["rows"], n
        for k in ("monthly_dev4", "monthly_5y", "monthly_last_year", "gate_dd", "losing_years",
                  "yearly", "win_rate_dev", "trades_dev"):
            assert k in doc["rows"][f"M2_{n}"], (n, k)
        assert len(doc["rows"][f"M2_{n}"]["yearly"]) == 5


def test_cost_stress_is_worse_than_base_both():
    doc = _load()
    for prefix in ("M2", "G2"):
        base, stress = doc["rows"][f"{prefix}_base"], doc["rows"][f"{prefix}_cost_stress"]
        assert stress["monthly_dev4"] < base["monthly_dev4"]
        assert stress["monthly_5y"] < base["monthly_5y"]
