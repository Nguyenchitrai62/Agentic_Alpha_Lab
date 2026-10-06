"""Tests for research/diagnostics/oc_jitter (assignment OPENCODE_W_ops_jitteranalyze)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
OC = ROOT / "research" / "diagnostics" / "oc_jitter"
JOB = ROOT / "artifacts" / "kaggle_stage" / "engine_kernel" / "jobs" / "jitter_g2.json"

BASE = {"mean5y": 5.41, "worst": 2.588, "maxDD": 16.91, "losing": 0,
        "full_path_dd": 16.82, "years": [[2.588, 10.86]] * 5}
NAMES = ["R2B1D17BFG2"] + [f"R2B1D17BFG2_J{i:02d}" for i in range(1, 13)]


def _load():
    spec = importlib.util.spec_from_file_location("oc_jitter_mod", str(OC / "analyze_jitter.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _payload(base=None, jitter=None):
    rows = {"R2B1D17BFG2": dict(BASE if base is None else base)}
    good = {"mean5y": 5.3, "worst": 2.6, "maxDD": 16.5, "losing": 0,
            "full_path_dd": 16.4, "years": [[2.6, 16.5]] * 5}
    for n in NAMES[1:]:
        rows[n] = dict(good if jitter is None else jitter)
    return {"version": "engine_kernel", "job": "jitter_g2_joint", "rows": rows}


def test_job_spec_has_13_rows():
    job = json.loads(JOB.read_text())
    assert len(job["rows"]) == 13
    assert job["rows"][0]["name"] == "R2B1D17BFG2"


def test_gate_pass_robust_writes_report_and_results(tmp_path):
    m = _load()
    rp = tmp_path / "results.json"
    rp.write_text(json.dumps(_payload()))
    out, report = m.analyze(rp, JOB)
    assert out["gate"]["passed"] is True
    assert out["verdict"] == "ROBUST"
    assert out["failing"] == []
    assert len(out["rows"]) == 13
    d = out["distribution_jitter12"]
    assert d["n"] == 12
    assert d["share_all"] == 1.0
    assert d["mean5y"]["min"] == d["mean5y"]["max"] == 5.3
    # per-row table carries the joint-jitter parameters from the job spec
    j01 = out["rows"]["R2B1D17BFG2_J01"]
    assert (j01["kd"], j01["G"], j01["k"]) == (1.8058, 1.929, 1.0989)
    # main() writes REPORT.md + results.json next to the script (here: tmp outdir)
    od = tmp_path / "out"
    assert m.main(["--results", str(rp), "--job", str(JOB), "--outdir", str(od)]) == 0
    rep = (od / "REPORT.md").read_text()
    assert "VERDICT: ROBUST" in rep
    assert "| R2B1D17BFG2_J01 |" in rep
    assert json.loads((od / "results.json").read_text())["verdict"] == "ROBUST"


def test_not_robust_lists_failing_rows_and_moved_param(tmp_path):
    m = _load()
    rows = _payload()["rows"]
    rows["R2B1D17BFG2_J03"] = {"mean5y": 4.5, "worst": 1.2, "maxDD": 15.0,
                               "losing": 0, "full_path_dd": 15.1, "years": []}
    rows["R2B1D17BFG2_J07"] = {"mean5y": 5.2, "worst": 2.0, "maxDD": 21.5,
                               "losing": 1, "full_path_dd": 21.0, "years": []}
    rp = tmp_path / "results.json"
    rp.write_text(json.dumps({"version": "engine_kernel", "job": "jitter_g2_joint", "rows": rows}))
    out, report = m.analyze(rp, JOB)
    assert out["verdict"] == "NOT-ROBUST"
    failing = {f["name"]: f for f in out["failing"]}
    assert set(failing) == {"R2B1D17BFG2_J03", "R2B1D17BFG2_J07"}
    assert any("5y" in r for r in failing["R2B1D17BFG2_J03"]["reasons"])
    assert any("losing" in r for r in failing["R2B1D17BFG2_J07"]["reasons"])
    # J03 sleeve k 1.0776 (+7.8%) beats kd/G moves, so k is reported
    assert failing["R2B1D17BFG2_J03"]["moved_most"].startswith("k ")
    assert "R2B1D17BFG2_J03" in report and "VERDICT: NOT-ROBUST" in report


def test_gate_fail_stops_with_clear_message(tmp_path):
    m = _load()
    bad = dict(BASE, mean5y=4.0)
    rp = tmp_path / "results.json"
    rp.write_text(json.dumps(_payload(base=bad)))
    try:
        m.analyze(rp, JOB)
    except m.GateError as e:
        assert "GATE FAIL" in str(e) and "v421" in str(e)
    else:
        raise AssertionError("expected GateError")
    assert m.main(["--results", str(rp), "--job", str(JOB),
                   "--outdir", str(tmp_path / "o")]) == 2


def test_gate_fail_on_wrong_row_count(tmp_path):
    m = _load()
    p = _payload()
    del p["rows"]["R2B1D17BFG2_J12"]
    rp = tmp_path / "results.json"
    rp.write_text(json.dumps(p))
    try:
        m.analyze(rp, JOB)
    except m.GateError as e:
        assert "12 jitter rows" in str(e)
    else:
        raise AssertionError("expected GateError")
