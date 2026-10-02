"""Checks for the R2 robustness diagnostic (BOT R2 v321 vs deployed G2 v301, bar-open)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "research/diagnostics/r2_robustness/r2_robustness.json"


def _load():
    with open(DATA) as fh:
        return json.load(fh)


def test_g2_base_reproduces_deployed():
    doc = _load()
    g = doc["rows"]["G2_base"]
    assert abs(g["monthly_dev4"] - 6.504) < 0.01
    assert abs(g["monthly_5y"] - 6.272) < 0.005
    assert abs(g["monthly_last_year"] - 5.349) < 0.005
    assert abs(g["gate_dd"] - 17.09) < 0.05
    assert g["losing_years"] == 0
    assert len(g["yearly"]) == 5


def test_r2_base_reproduces_candidate():
    doc = _load()
    b = doc["rows"]["R2_base"]
    assert abs(b["monthly_dev4"] - 7.079) < 0.01
    assert abs(b["monthly_5y"] - 6.793) < 0.005
    assert abs(b["monthly_last_year"] - 5.655) < 0.005
    assert abs(b["gate_dd"] - 18.39) < 0.05
    assert b["losing_years"] == 0
    assert len(b["yearly"]) == 5


def test_all_paired_rows_present():
    doc = _load()
    names = ["base", "cost_stress", "latency_15", "latency_30", "latency_60", "band_lo", "band_hi",
             "cool3", "cool12", "sleeve_0.22", "sleeve_0.30", "offset_0.15", "offset_0.40",
             "outage_backstop_only", "close_1m", "sleeve_start_21", "sleeve_start_31"]
    for n in names:
        assert f"G2_{n}" in doc["rows"], n
        assert f"R2_{n}" in doc["rows"], n
        for k in ("monthly_dev4", "monthly_5y", "monthly_last_year", "gate_dd", "losing_years",
                  "yearly", "win_rate_dev", "trades_dev", "win_all_dev", "trades_all_dev"):
            assert k in doc["rows"][f"G2_{n}"], (n, k)
            assert k in doc["rows"][f"R2_{n}"], (n, k)
        assert len(doc["rows"][f"G2_{n}"]["yearly"]) == 5
        assert len(doc["rows"][f"R2_{n}"]["yearly"]) == 5


def test_cost_stress_is_worse_than_base_both():
    doc = _load()
    for prefix in ("G2", "R2"):
        base, stress = doc["rows"][f"{prefix}_base"], doc["rows"][f"{prefix}_cost_stress"]
        assert stress["monthly_dev4"] < base["monthly_dev4"]
        assert stress["monthly_5y"] < base["monthly_5y"]


def test_bootstrap_and_small_account_present():
    doc = _load()
    for k in ("bootstrap_G2", "bootstrap_R2"):
        b = doc[k]
        for f in ("monthly_p5", "monthly_p50", "monthly_p95", "p_monthly_ge5", "p_loss_year",
                  "dd_p50", "dd_p95", "p_dd_gt20"):
            assert f in b, (k, f)
    for k in ("small_account_1000_G2", "small_account_2000_G2",
              "small_account_1000_R2", "small_account_2000_R2"):
        s = doc[k]
        assert s["book_share"] is not None and s["rung_share"] is not None
