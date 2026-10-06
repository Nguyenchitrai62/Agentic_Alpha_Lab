"""oc_d13robust tests (light: no engine run; validates the diagnostic outputs)."""
from __future__ import annotations

import json
import pickle
from pathlib import Path

AUD = Path("research/diagnostics/oc_d13robust")
SRC = AUD / "robust_d13.py"
RES = AUD / "results.json"
REP = AUD / "ROBUST.md"


def _results():
    return json.loads(RES.read_text())


def test_outputs_exist():
    assert SRC.exists()
    assert RES.exists()
    assert REP.exists()
    for cfg in ("base", "S1", "S2", "S3", "S4", "S5"):
        p = AUD / ("runs_D13BF_%s.pkl" % cfg)
        assert p.exists(), p
        runs = pickle.loads(p.read_bytes())
        assert set(runs) == {0, 1, 2, 3}
        for s in range(4):
            assert len(runs[s]["eq"]) == len(runs[s]["eq_min"]) == len(runs[s]["t"])
            assert "per" in runs[s]


def test_row_spec_is_d13bf():
    src = SRC.read_text()
    assert 'kd=1.3' in src or '"kd": 1.3' in src or "kd\", 1.3" in src
    assert "R2B1D13BF" in src
    d = _results()
    assert d["row"] == "R2B1D13BF"
    assert d["spec"]["kd"] == 1.3 and d["spec"]["bear"] is True
    assert d["spec"]["G"] is None and d["spec"]["F"] == 2.5
    # budget wiring 0.26 * k * kd must be present (as in v424/robust_v421)
    assert "0.26" in src and "sleeve_risk_budget" in src


def test_friction_set_matches_robust_v421():
    src = SRC.read_text()
    # S1 cost stress
    assert "0.0004" in src and "0.0007 + 0.0005" in src
    # S2/S3 latency
    assert "win_start=15" in src and "sleeve_start=16" in src
    assert "win_start=30" in src and "sleeve_start=31" in src
    # S4 stop slip
    assert "stop_slip=0.5" in src
    # S5 Bybit from 2021-11-15
    assert "2021-11-15" in src and "bybit" in src.lower()
    # one process at a time + 2 GB RAM gate
    assert "wait_for_ram(2.0)" in src
    assert "sequential" in src


def test_baseline_matches_official_v424():
    d = _results()
    b = d["baseline"]
    assert abs(b["mean5y"] - 4.971) < 1e-6
    assert abs(b["maxDD"] - 14.98) < 1e-6
    assert abs(b["fullDD"] - 14.86) < 1e-6
    assert d["base_vs_v424pkl_dEQ"] == 0.0
    off = d["official_v424"]
    assert abs(off["R"] - 4.971) < 1e-9 and abs(off["DD"] - 14.98) < 1e-9


def test_friction_metrics_present():
    d = _results()
    for s in ("S1", "S2", "S3", "S4", "S5"):
        m = d["configs"][s]
        assert len(m["years"]) == 5
        assert m["mean5y"] > 0 and m["maxDD"] > 0 and m["fullDD"] > 0
        assert all(y["R"] > 0 for y in m["years"]), s  # no losing year
    assert d["configs"]["S5"]["year2021_short_window"] is True
    assert "s5_window" in d["configs"]["S5"] and "baseline_same_window" in d["configs"]["S5"]


def test_win_rates_consistent():
    d = _results()
    for scope, w in d["wins"].items():
        assert len(w["years"]) == 5, scope
        p = w["pooled"]
        tn_b = sum(y["nb"] for y in w["years"])
        tw_b = sum(y["wb"] for y in w["years"])
        tn_r = sum(y["nr"] for y in w["years"])
        tw_r = sum(y["wr"] for y in w["years"])
        assert (tn_b, tw_b, tn_r, tw_r) == (p["nb"], p["wb"], p["nr"], p["wr"]), scope
        for y in w["years"]:
            assert abs(y["book_win"] - y["wb"] / y["nb"]) < 5e-5, (scope, y)
            assert abs(y["rung_win"] - y["wr"] / y["nr"]) < 5e-5, (scope, y)
            assert abs(y["win_all"] - (y["wb"] + y["wr"]) / (y["nb"] + y["nr"])) < 5e-5, (scope, y)
        assert abs(p["book_win"] - p["wb"] / p["nb"]) < 5e-5, scope
        assert abs(p["win_all"] - (p["wb"] + p["wr"]) / (p["nb"] + p["nr"])) < 5e-5, scope
    # references next to D13BF
    assert d["reference_R2B1D17BF"]["baseline"]["mean5y"] == 5.425
    assert d["reference_R2B1D17BFG2"]["baseline"]["mean5y"] == 5.41


def test_report_has_comparison_and_verdict():
    rep = REP.read_text()
    assert "R2B1D17BF" in rep and "R2B1D17BFG2" in rep
    assert "does the DD < 15 profile keep DD < 15" in rep.lower() or "DD < 15 profile" in rep
    assert "Diagnostic only: no selection" in rep
    assert "dEQ" in rep
