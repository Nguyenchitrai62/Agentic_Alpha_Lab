"""Tests for oc_wfselect: recompute walk-forward selection from cached per-row years."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research" / "tournament" / "oc_wfselect"


def _load_run():
    spec = importlib.util.spec_from_file_location(
        "run_wfselect", HERE / "run_wfselect.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_artifacts_exist():
    for f in ("PLAN.md", "run_wfselect.py", "results.json", "REPORT.md"):
        assert (HERE / f).exists(), f


def test_selection_recomputes():
    d = json.loads((HERE / "results.json").read_text())
    run = _load_run()
    stats = d["per_row_years"]
    assert len(stats) == 31
    assert "R2B1D17BF" in stats
    for k in (1, 2, 3, 4):
        sel = list(range(k))
        pa, fba = run.pick_robust(stats, sel)
        pb, fbb = run.pick_dd18(stats, sel)
        assert d["ruleA_wf"][str(k)]["pick"] == pa
        assert d["ruleA_wf"][str(k)]["fallback"] == fba
        assert d["ruleB_wf"][str(k)]["pick"] == pb
        assert d["ruleB_wf"][str(k)]["fallback"] == fbb
        assert d["ruleA_wf"][str(k)]["R"] == stats[pa][k][0]
        assert d["ruleB_wf"][str(k)]["R"] == stats[pb][k][0]


def test_chains_and_verdict():
    d = json.loads((HERE / "results.json").read_text())
    run = _load_run()
    for key, wf in (("ruleA_chain", d["ruleA_wf"]), ("ruleB_chain", d["ruleB_wf"])):
        Rs = [wf[str(k)]["R"] for k in (1, 2, 3, 4)]
        assert d[key]["R_geo"] == round(run.geo(Rs), 3)
        assert d[key]["losing"] == sum(r < 0 for r in Rs)
    excess = [round(d["ruleA_wf"][str(k)]["R"] - d["per_row_years"]["R2B1D17BF"][k][0], 3)
              for k in (1, 2, 3, 4)]
    assert d["excess_A_minus_base"] == excess
    npos = sum(e > 0 for e in excess)
    nstable = sum(1 for k in ("2", "3", "4") if d["looA"][k]["stable"])
    assert d["nstable"] == nstable
    want = "PROMISING" if (npos >= 3 and nstable >= 3) else "NOT PROMISING"
    assert d["verdict"] == want
    assert "optimistic" in d["note"]
