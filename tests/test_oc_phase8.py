"""Tests for oc_phase8 (light: no simulation, checks results.json + REPORT + caches)."""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "research" / "diagnostics" / "oc_phase8"
SHIFTS = ("0", "0.5", "1", "1.5", "2", "2.5", "3", "3.5")
STRAT = "R2B1D17BFG2"


def _res():
    return json.loads((D / "results.json").read_text())


def test_files_exist():
    assert (D / "oc_phase8.py").exists()
    assert (D / "results.json").exists()
    assert (D / "REPORT.md").exists()
    for s in SHIFTS:
        assert (D / f"oc_phase8_run_s{s.replace('.', '')}.pkl").exists(), s


def test_result_shape():
    r = _res()
    assert r["version"] == "oc_phase8" and r["strat"] == STRAT
    assert set(r["phases"]) == set(SHIFTS)
    for s, p in r["phases"].items():
        for k in ("mean_5y", "worst", "max_yearly_dd", "losing", "full_path_dd", "win_all", "years"):
            assert k in p, (s, k)
        assert len(p["years"]) == 5
        assert all(set(d) >= {"R", "DD", "win"} for d in p["years"])
        assert 0.0 <= p["win_all"] <= 1.0
    for m in ("mix4", "mix8"):
        assert set(r[m]) >= {"mean_5y", "worst", "max_yearly_dd", "losing", "full_path_dd", "win_all", "years"}
    assert r["verdict"] in ("KEEP-CANDIDATE", "NO")


def test_step2_reproduces_v421():
    r = _res()
    v421 = json.loads((ROOT / "research" / "parallel" / "rounds" / "parallel-20260906-r2"
                       / "v421" / "v421_result.json").read_text())["rows"][STRAT]
    m4 = r["mix4"]
    assert m4["mean_5y"] == v421["R"] == 5.41
    assert m4["worst"] == v421["W"] == 2.588
    assert m4["max_yearly_dd"] == v421["DD"] == 16.91
    assert m4["losing"] == v421["losing"] == 0
    assert m4["years"] == [dict(R=y[0], DD=y[1], win=m4["years"][i]["win"]) for i, y in enumerate(v421["years"])]
    assert m4["full_path_dd"] == v421["full_path_dd"] == 16.82
    assert r["step2"]["reproduced_exactly"] is True
    assert all(v < 1e-9 for v in r["step2"]["hourly_max_rel_diff"].values())


def test_hourly_phases_match_phasedisp():
    pdisp = json.loads((ROOT / "research" / "tournament" / "oc_phasedisp" / "results.json").read_text())
    r = _res()
    for s in ("0", "1", "2", "3"):
        p, d = r["phases"][s], pdisp["phases"][s]
        assert p["mean_5y"] == d["mean_5y"], s
        assert p["worst"] == d["worst"], s
        assert p["max_yearly_dd"] == d["max_yearly_dd"], s
        assert p["full_path_dd"] == d["full_path_dd"], s
        assert [(y["R"], y["DD"]) for y in p["years"]] == [(y["R"], y["DD"]) for y in d["years"]], s


def test_caches_match_results():
    r = _res()
    for s in SHIFTS:
        run = pickle.loads((D / f"oc_phase8_run_s{s.replace('.', '')}.pkl").read_bytes())
        assert np.allclose(run["eq"], pickle.loads(
            (D / f"oc_phase8_run_s{s.replace('.', '')}.pkl").read_bytes())["eq"])
        assert r["phases"][s]["win_all"] == run["win_all"], s
        assert r["phases"][s]["nb"] == run["nb"] and r["phases"][s]["nr"] == run["nr"], s


def test_verdict_rule_consistent():
    r = _res()
    m8 = r["mix8"]
    expect = ("KEEP-CANDIDATE" if (16.82 - m8["full_path_dd"] >= 1.0
                                   and m8["mean_5y"] >= 5.30 and m8["losing"] == 0) else "NO")
    assert r["verdict"] == expect == "NO"
    assert m8["mean_5y"] < 5.30 and m8["full_path_dd"] > 16.82


def test_report_documents_causality_and_verdict():
    rep = (D / "REPORT.md").read_text()
    assert "ffill" in rep and "no look-ahead" in rep
    assert "VERDICT: NO" in rep
    assert "8-phase mix" in rep
    for s in ("0.5h", "1.5h", "2.5h", "3.5h"):
        assert s in rep
