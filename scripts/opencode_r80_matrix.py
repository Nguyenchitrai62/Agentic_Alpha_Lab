"""R80 Track-C requirement matrix generator (outcome-based, not existence).

Verdicts bind to ACTUAL outcomes: the fails-before evidence file
(c_fails_before.json with per-case bug_present flags + recorded source
hashes), exact test node IDs, and current source/asset hashes. Rules:

- A requirement whose evidence shows bug_present=true (or whose evidence
  file is missing/unparseable) is FAIL, even if its test file exists.
- A requirement whose recorded source hash != current source hash is FAIL
  (stale evidence: source changed since capture).
- Non-fix requirements PASS only with their evidence file present AND
  tests_failed == 0.
- R80-EDGE stays NOT_EXERCISED (no profit claim); R80-DEPLOY-AVAIL stays
  BLOCKED (no deploy log; UNKNOWN, not invented).
- Overall PASS needs every requirement PASS; otherwise WITHHELD.

Never overwrites any prior matrix file (writes only --out).
Usage:
  python scripts/opencode_r80_matrix.py --tests-passed N --tests-failed N
      --tests-skipped N --out artifacts/research/opencode_r80/c_requirement_matrix.json
"""
import torch  # noqa: F401  (torch before pandas: Windows DLL load-order rule)

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R80 = ROOT / "artifacts/research/opencode_r80"

MATRIX_VERSION = "r80_accept/1"
FAILSB_BEFORE = "artifacts/research/opencode_r80/c_fails_before/" \
    "c_fails_before.json"

PINNED_SOURCES = [
    "scripts/opencode_r78_roll.py",
    "scripts/opencode_r77_advisor.py",
    "scripts/opencode_r77_advisor_core.py",
    "scripts/opencode_r79_vintage.py",
    "scripts/opencode_r76_infer.py",
    "configs/opencode_r79_roll.json",
    "configs/opencode_r77_advisor.json",
]


def sha(path: str) -> str:
    p = ROOT / path
    if not p.is_file():
        return "MISSING:" + path
    return hashlib.sha256(p.read_bytes()).hexdigest()


def has(path: str) -> bool:
    return (ROOT / path).is_file()


def load_fails_before() -> tuple[dict | None, str]:
    p = ROOT / FAILSB_BEFORE
    if not p.is_file():
        return None, "missing evidence file"
    try:
        return json.loads(p.read_text(encoding="utf-8")), ""
    except ValueError as e:
        return None, f"unparseable evidence: {e}"


def hash_drift(recorded: dict) -> list[str]:
    drift = []
    for f in PINNED_SOURCES:
        if recorded.get(f) != sha(f):
            drift.append(f)
    return drift


REQS = [
    ("R80-GAP-1", "feed_validity",
     "Full backfill settles identically to uninterrupted execution: stable "
     "economic clock, no double-consumed expiry indices (Codex case 1).",
     ["tests/test_r80_c_gap.py::test_full_backfill_matches_uninterrupted",
      "artifacts/research/opencode_r80/c_fails_before/c_fails_before.json"
      ":case1_gap_backfill_divergence"],
     "case1_gap_backfill_divergence"),
    ("R80-GAP-2", "feed_validity",
     "Partial backfill keeps the gap unresolved until EVERY expected valid "
     "close is available (Codex case 2).",
     ["tests/test_r80_c_gap.py::test_partial_backfill_preserves_pause",
      "artifacts/research/opencode_r80/c_fails_before/c_fails_before.json"
      ":case2_partial_backfill_validity"],
     "case2_partial_backfill_validity"),
    ("R80-AVAIL-1", "vintage_eligibility",
     "None/NaT/UNKNOWN decision+asset timestamps are REJECTED; --claim "
     "causal with missing args refuses (Codex case 3).",
     ["tests/test_r80_c_availability.py::"
      "test_availability_none_metadata_rejected",
      "tests/test_r80_c_availability.py::"
      "test_availability_nat_metadata_rejected",
      "tests/test_r80_c_availability.py::test_claim_cli_missing_args_fail_closed",
      "tests/test_r80_c_availability.py::test_availability_positive_control_eligible",
      "tests/test_r80_c_availability.py::test_availability_boundary_equality_rejected",
      "tests/test_r80_c_availability.py::test_availability_future_calibrator_rejected",
      "artifacts/research/opencode_r80/c_fails_before/c_fails_before.json"
      ":case3_availability_fail_open"],
     "case3_availability_fail_open"),
    ("R80-CLI-1", "operational_readiness",
     "CLI smoke + --resume share the ACTUAL serving path (r76 infer + roll "
     "CLI, mock only at the inference-input edge); no forked logic.",
     ["tests/test_r80_c_cli.py::test_cli_smoke_and_restart_share_serving_path",
      "tests/test_r80_c_cli.py::test_cli_provenance_shifted_windows_exact",
      "tests/test_r80_c_cli.py::test_stale_decision_is_diagnostic_only"],
     None),
    ("R80-CLI-2", "operational_readiness",
     "ONE supported advisory entry point declared (r79/r80 roll CLI); R77 "
     "CLI research-only with exact routing (no second implementation).",
     ["artifacts/research/opencode_r80/c_supported_cli.md",
      "tests/test_r80_c_cli.py::test_r77_scope_corrected_fresh_ok_replay_research_only"],
     None),
    ("R80-R77", "observation_safety",
     "R77 scope corrected: fresh already uses observed_at (:151/:154); the "
     "real issues are REPLAY backdate (:162-164) + missing wrapper "
     "safeguards; stale R79 claim corrected in evidence.",
     ["artifacts/research/opencode_r80/c_supported_cli.md",
      "tests/test_r80_c_cli.py::test_r77_scope_corrected_fresh_ok_replay_research_only"],
     None),
    ("R80-PROV-1", "feed_validity",
     "Per-ingest immutable snapshots; hash+range exact on 2 shifted "
     "windows; lineage via prev_sha.",
     ["tests/test_r80_c_cli.py::test_cli_provenance_shifted_windows_exact"],
     None),
    ("R80-SMOKE-1", "operational_readiness",
     "One finite fresh public-klines smoke through the supported CLI with "
     "immutable provenance (public GET only, no orders/scheduler).",
     ["artifacts/research/opencode_r80/c_smoke_fresh/smoke.log"],
     None),
    ("R80-DEPLOY-AVAIL", "vintage_eligibility",
     "Deployment-availability log for fold bundles (prospective eligibility "
     "rests on simulated cutoff only).",
     [],
     None),
    ("R80-EDGE", "economics",
     "Economic edge / 3%/mo aspiration: goal, not evidence. No claim.",
     [],
     None),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tests-passed", type=int, required=True)
    ap.add_argument("--tests-failed", type=int, required=True)
    ap.add_argument("--tests-skipped", type=int, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    fb, fb_err = load_fails_before()
    recorded = (fb or {}).get("source_sha256", {})
    drift = hash_drift(recorded) if fb else ["evidence-missing"]

    verdicts = {}
    for rid, cat, desc, ev, fb_key in REQS:
        if rid == "R80-EDGE":
            status, note = ("NOT_EXERCISED",
                            "No profitability promotion this round; "
                            "3%/month + DD20% + 1x remain goals.")
        elif rid == "R80-DEPLOY-AVAIL":
            status, note = ("BLOCKED",
                            "No deploy log exists; file ctime is "
                            "Kaggle-download date, not training/availability "
                            "time. UNKNOWN, not invented.")
        elif fb is None:
            status, note = ("FAIL", f"No outcome evidence: {fb_err}.")
        elif drift and rid in ("R80-GAP-1", "R80-GAP-2", "R80-AVAIL-1"):
            status, note = ("FAIL",
                            f"Stale evidence: source changed since capture "
                            f"({', '.join(drift)}); re-capture before "
                            f"verdict.")
        elif fb_key is not None:
            case = fb.get(fb_key, {})
            bug = case.get("bug_present")
            if bug is None and isinstance(case.get("cases"), list):
                # Multi-subcase evidence (e.g. availability T1..Tn): absent
                # iff every sub-case is flag-clear and actual==expected.
                subs = case["cases"]
                bad = [s for s in subs
                       if s.get("bug_present") is not False or (
                           "expected" in s
                           and s.get("actual") != s.get("expected"))]
                bug = False if subs and not bad else None
                if bug is False:
                    note_extra = (f"{len(subs)} sub-cases flag-clear, "
                                  "actual==expected.")
                else:
                    note_extra = ""
            else:
                note_extra = ""
            if bug is True:
                status, note = ("FAIL",
                                "Outcome evidence shows the bug PRESENT on "
                                "captured code (fails-before); fix + "
                                "re-capture required.")
            elif bug is False:
                if a.tests_failed == 0:
                    status, note = ("PASS",
                                    "Outcome evidence shows bug absent on "
                                    "matching source hashes; suite green."
                                    + (f" {note_extra}" if note_extra
                                       else ""))
                else:
                    status, note = ("FAIL",
                                    "Evidence clear but suite has failures.")
            else:
                status, note = ("FAIL",
                                "Evidence case missing bug_present flag.")
        else:
            missing = [e for e in ev
                       if not (has(e.split("::")[0]))]
            if missing:
                status, note = ("FAIL",
                                f"Missing evidence: {missing}.")
            elif a.tests_failed > 0:
                status, note = ("FAIL", "Suite has failures.")
            elif rid == "R80-SMOKE-1" and not has(ev[0]):
                status, note = ("FAIL", "Fresh-smoke log not yet captured.")
            else:
                status, note = ("PASS",
                                "Evidence present; suite green; hashes "
                                "match capture." if not drift else
                                "Evidence present; suite green (non-fix "
                                "requirement; source drift noted).")
        verdicts[rid] = {"status": status, "category": cat,
                         "description": desc, "evidence": ev, "note": note}

    tally = {}
    for v in verdicts.values():
        tally[v["status"]] = tally.get(v["status"], 0) + 1
    blockers = [r for r, v in verdicts.items()
                if v["status"] in ("FAIL", "BLOCKED")]
    overall = "WITHHELD"  # EDGE is honestly NOT_EXERCISED this round.
    matrix = {
        "accept_version": MATRIX_VERSION, "exploratory": True,
        "live_orders": False,
        "supersedes_nothing": ("R79 matrix untouched at "
                               "artifacts/research/opencode_r79/"
                               "c_requirement_matrix.json (if present); "
                               "this file is a NEW R80 artifact."),
        "overall": overall,
        "overall_rule": ("Overall PASS needs every requirement PASS with "
                         "outcome evidence (exact node IDs + matching "
                         "source/asset hashes). File existence + suite "
                         "totals are insufficient. R80-EDGE stays "
                         "NOT_EXERCISED: no profit claim."),
        "withheld_by": blockers,
        "tallies": tally,
        "requirements": verdicts,
        "fails_before_evidence": FAILSB_BEFORE,
        "source_sha256": {f: sha(f) for f in PINNED_SOURCES},
        "evidence_recorded_sha256": recorded,
        "source_drift_since_capture": drift,
        "test_counts": {"passed": a.tests_passed, "failed": a.tests_failed,
                        "skipped": a.tests_skipped},
    }
    out = ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(matrix, indent=1), encoding="utf-8")
    print(json.dumps({"matrix": str(a.out), "overall": overall,
                      "tallies": tally, "withheld_by": blockers}, indent=1))


if __name__ == "__main__":
    main()
