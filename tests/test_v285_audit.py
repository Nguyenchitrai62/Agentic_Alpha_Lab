"""v285 audit tests: replication matches the reported result, robustness artifacts exist."""

from __future__ import annotations

import json
from pathlib import Path

RD = Path("research/parallel/rounds/parallel-20260906-r2")
AUD = RD / "v285_audit"
ROB = Path("research/diagnostics/d2c_robustness")


def _load_json(p):
    return json.loads(Path(p).read_text())


def test_replication_matches_reported():
    rep = _load_json(AUD / "replication.json")
    res = _load_json(RD / "v285/v285_result.json")
    assert rep["selection"] == res["selected"] == "D2_d20"
    for key in ("C4", "D1_six_sets", "D2_d20"):
        r = rep["rows"][key]
        j = res["rows"][key]
        assert abs(r["monthly_dev4"] - j["monthly_dev4"]) < 0.01, key
        assert abs(r["gate_dd"] - j["gate_dd"]) < 0.05, key
        assert abs(r["worst_dev_month_pct"] - j["worst_dev_month_pct"]) < 0.01, key
    sel = rep["selection"]
    f_rep = rep["final_score_selected"]
    f_res = res["final_score_selected"]
    assert abs(f_rep["monthly_5y"] - f_res["monthly_5y"]) < 0.005
    assert abs(f_rep["monthly_last_year"] - f_res["monthly_last_year"]) < 0.005
    assert f_rep["losing_years"] == f_res["losing_years"] == 0
    assert abs(f_rep["gate_dd"] - f_res["gate_dd"]) < 0.05
    assert f_rep["gate_pass"] is True
    assert f_rep["hidden_year_trades"]["trades"] == 310
    # C4 reference reproduces the frozen foundation
    assert abs(rep["rows"]["C4"]["monthly_dev4"] - 6.026) < 0.002
    # member D caches are replayable bit-exact
    assert rep["rebuild_annual_D"]["match"] is True
    assert rep["rebuild_annual_D"]["max_abs_diff"] == 0.0
    assert rep["rebuild_quarterly_D"]["match"] is True
    assert rep["rebuild_quarterly_D"]["max_abs_diff"] == 0.0
    # robust selection used first-four-year metrics only
    assert rep["selection_rule"].startswith("v204.robust_select")
    assert rep["rows"]["D2_d20"]["worst_dev_month_pct"] > rep["rows"]["D1_six_sets"]["worst_dev_month_pct"]
    # leakage checks recorded
    for k in ("feature_timing", "label_windows", "fit_windows", "fill_timing"):
        assert rep["leakage"][k].startswith("PASS"), k


def test_comparison_verdict():
    text = (AUD / "COMPARISON.md").read_text()
    assert "## Verdict" in text
    assert text.split("## Verdict", 1)[1].strip().startswith("PASS")
    for k in ("feature timing", "label windows", "fit windows", "fill / exit timing"):
        assert k in text.lower(), k


def test_robustness_artifacts():
    rob = _load_json(ROB / "d2c_robustness.json")
    rows = rob["rows"]
    assert abs(rows["C4_base"]["monthly_dev4"] - 6.026) < 0.01
    assert abs(rows["C4_base"]["gate_dd"] - 18.27) < 0.05
    assert abs(rows["D2_base"]["monthly_dev4"] - 5.864) < 0.01
    assert abs(rows["D2_base"]["gate_dd"] - 18.39) < 0.05
    assert abs(rows["D2_base"]["monthly_last_year"] - 5.167) < 0.005
    for k, r in rows.items():
        assert r["losing_years"] == 0, k
    assert "bootstrap_C4" in rob and "bootstrap_D2" in rob
    assert "small_account_2000_C4" in rob and "small_account_2000_D2" in rob
    assert rob["small_account_2000_C4"]["book_share"] >= 0.98
    assert rob["small_account_2000_D2"]["book_share"] >= 0.98
    summary = (ROB / "SUMMARY.md").read_text()
    assert len(summary.splitlines()) <= 25
    assert "Verdict" in summary
