"""Tests for oc_plateau (light: no simulation, checks results.json + REPORT)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "research" / "diagnostics" / "oc_plateau"
ROWS = ("R2B1D17BF", "R2B1D17BF_F20", "R2B1D17BF_F30", "R2B1D17BF_MA900",
        "R2B1D17BF_MA1500", "R2B1D17BF_BM035", "R2B1D17BF_BM065")


def _res():
    return json.loads((D / "results.json").read_text())


def test_files_exist():
    assert (D / "oc_plateau.py").exists()
    assert (D / "results.json").exists()
    assert (D / "REPORT.md").exists()


def test_rows_and_metrics():
    r = _res()
    assert r["version"] == "oc_plateau"
    assert set(r["rows"]) == set(ROWS)
    for name, m in r["rows"].items():
        for k in ("R", "W", "DD", "losing", "years", "full_path_dd"):
            assert k in m, name
        assert len(m["years"]) == 5
        assert all(len(y) == 2 for y in m["years"])
        assert isinstance(m["losing"], int) and 0 <= m["losing"] <= 5


def test_reference_matches_v411_cache():
    r = _res()["rows"]["R2B1D17BF"]
    v411 = json.loads((ROOT / "research" / "parallel" / "rounds" /
                       "parallel-20260906-r2" / "v411" / "v411_result.json").read_text())
    ref = v411["rows"]["R2B1D17BF"]
    assert r["R"] == ref["R"] and r["W"] == ref["W"] and r["DD"] == ref["DD"]
    assert r["losing"] == ref["losing"]
    assert r["years"] == [list(y) for y in ref["years"]]
    assert r["full_path_dd"] == ref["full_path_dd"]


def test_params_logged():
    r = _res()
    assert r["deployed"] == {"flush": 2.5, "bear_win": 1200, "bear_min_periods": 600, "bear_mult": 0.5}
    assert r["params"]["R2B1D17BF_F20"] == {"flush": 2.0}
    assert r["params"]["R2B1D17BF_F30"] == {"flush": 3.0}
    assert r["params"]["R2B1D17BF_MA900"] == {"bear_win": 900}
    assert r["params"]["R2B1D17BF_MA1500"] == {"bear_win": 1500}
    assert r["params"]["R2B1D17BF_BM035"] == {"bear_mult": 0.35}
    assert r["params"]["R2B1D17BF_BM065"] == {"bear_mult": 0.65}


def test_report_verdict():
    rep = (D / "REPORT.md").read_text()
    for name in ROWS:
        assert name in rep
    assert ("plateau" in rep.lower() or "spike" in rep.lower())
