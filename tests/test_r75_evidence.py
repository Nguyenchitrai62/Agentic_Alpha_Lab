"""Round 75 worker A: evidence audit + assessment contract tests (no training, no I/O outside allowed paths)."""
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT = os.path.join(REPO, "artifacts", "research", "opencode_r75_practical", "evidence", "evidence_audit.json")
ASSESS = os.path.join(REPO, "configs", "opencode_r75_assessment.json")
MANIFEST = os.path.join(REPO, "configs", "opencode_r75_evidence.json")


def load(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def test_contract_loads_and_has_required_rules():
    c = load(ASSESS)
    assert c["contract"] == "opencode_r75_assessment"
    assert c["performance_evidence"]["drawdown_max"] == 0.2
    assert c["performance_evidence"]["fills_min_each_scenario"] == 30
    assert "INSUFFICIENT_EVIDENCE" in c["verdicts"]
    assert "FAILURE" in c["verdicts"]
    assert "one_interval_rule" in c
    assert "block_uncertainty_rule" in c
    assert "full_row_fields" in c
    assert "historical_reference_5pct" in c
    assert "3" in c["performance_evidence"].get("monthly_aspiration_3pct", "3")


def test_audit_loads_and_covers_families():
    a = load(AUDIT)
    fams = {f["family"] for f in a["claim_families"]}
    for expected in ["v30-iso4 calibration", "majority/confirmed ensemble", "L3 pipeline",
                     "forward OOS evals", "paper rehearsals"]:
        assert expected in fams, "missing family " + expected
    assert len(a["claim_families"]) >= 7


def test_unknown_markings_exist_where_claimed():
    a = load(AUDIT)
    unknowns = 0
    for fam in a["claim_families"]:
        p = fam["primary"]
        for k in ("candidate_registration_time", "first_metric_exposure_time"):
            if p.get(k) == "UNKNOWN":
                unknowns += 1
        if p.get("model_fit_calibration_dates") == "UNKNOWN":
            unknowns += 1
    assert unknowns >= 1, "uncertain exposure must be marked UNKNOWN, never clean-by-default"


def test_dataset_classification_states_no_untouched_holdout():
    a = load(AUDIT)
    classes = {d["class"] for d in a["dataset_classification"]}
    assert "development" in classes
    assert "historical-OOS-already-observed" in classes
    assert "prospective-shadow" in classes
    assert "sealed" in a["sealed_window_rule"].lower() or "sealed" in a["sealed_window_rule"]


def test_manifest_matches_audit_families():
    m = load(MANIFEST)
    a = load(AUDIT)
    assert {f["family"] for f in m["claim_families"]} == {f["family"] for f in a["claim_families"]}
