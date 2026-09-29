"""Checks for the O1 B18 robustness diagnostic (frozen deployed pipeline)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "research/diagnostics/o1_robustness/o1_robustness.json"


def _load():
    with open(DATA) as fh:
        return json.load(fh)


def test_base_reproduces_deployed_o1():
    doc = _load()
    base = doc["rows"]["base"]
    assert abs(base["monthly_dev4"] - 5.777) < 0.003
    assert abs(base["monthly_5y"] - 5.436) < 0.003
    assert abs(base["monthly_last_year"] - 4.082) < 0.003
    assert abs(base["gate_dd"] - 19.65) < 0.05
    assert base["losing_years"] == 0
    assert len(base["yearly"]) == 5


def test_cost_stress_is_worse_than_base():
    doc = _load()
    base, stress = doc["rows"]["base"], doc["rows"]["cost_stress"]
    assert stress["monthly_dev4"] < base["monthly_dev4"]
    assert stress["monthly_5y"] < base["monthly_5y"]
