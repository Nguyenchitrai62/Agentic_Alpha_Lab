"""R79 integrated requirement matrix generator (leader integration).

Builds a FRESH matrix from current evidence only. Never overwrites the R78
matrix (supersede note instead). No self-referential evidence counts as
economic-edge PASS. Usage:
  python scripts/opencode_r79_matrix.py --tests-passed N --tests-failed N
      --tests-skipped N --out artifacts/research/opencode_r79/c_requirement_matrix.json
"""
import torch  # noqa: F401  (torch before pandas: Windows DLL load-order rule)

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R79 = ROOT / "artifacts/research/opencode_r79"
W3 = ROOT / "artifacts/research/opencode_r78_rolling/w3"
BG = ROOT / "artifacts/research/opencode_background"

MATRIX_VERSION = "r79_accept/1"


def sha(path: str) -> str:
    p = ROOT / path
    if not p.is_file():
        return "MISSING:" + path
    return hashlib.sha256(p.read_bytes()).hexdigest()


def has(path: str) -> bool:
    return (ROOT / path).is_file()


REQS = [
    ("R79-OBS-1", "observation_safety",
     "Fresh bootstrap is diagnostic-only (zero actionable/fills/PnL).",
     ["tests/test_r79_a_bootstrap.py",
      "tests/test_r79_c_accept.py::test_c1+c2",
      "artifacts/research/opencode_background/leader_r78_bootstrap_repro/leader_result.json(fails-before)"]),
    ("R79-OBS-2", "observation_safety",
     "Missed-clock catch-up diagnostic-only; only latest-new-bar actionable.",
     ["tests/test_r79_a_catchup.py",
      "tests/test_r79_c_accept.py::test_c5"]),
    ("R79-OBS-3", "observation_safety",
     "Pending/open preserved causally through catch-up + restart parity.",
     ["tests/test_r79_a_catchup.py::test_pending_preserved_through_catchup_with_parity",
      "tests/test_r79_c_accept.py::test_c5+c6"]),
    ("R79-GAP-1", "feed_validity",
     "Gaps pause (empty + open portfolios); backfill recovers, no dups.",
     ["tests/test_r79_a_gaps.py",
      "tests/test_r79_c_accept.py::test_c4+c7"]),
    ("R79-REV-1", "feed_validity",
     "Revision-contaminated ingest diagnostic-only; pending preserved.",
     ["tests/test_r79_c_accept.py::test_c8"]),
    ("R79-PROV-1", "feed_validity",
     "Per-ingest immutable snapshots; hash+range exact on 2 shifted windows.",
     ["tests/test_r79_a_provenance.py",
      "tests/test_r79_c_accept.py::test_c3"]),
    ("R79-KILL-1", "operational_readiness",
     "SIGTERM mid-run resumes exactly-once (supersedes old R5 FAIL).",
     ["artifacts/research/opencode_r78_rolling/w3/w1_kill_recovery_evidence.json(full_recovery=true)"]),
    ("R79-VIN-1", "vintage_eligibility",
     "11x3 inventory complete with hashes/fit-ranges/UNKNOWNs cited.",
     ["artifacts/research/opencode_r79/b_inventory.json",
      "artifacts/research/opencode_r79/b_routing.json"]),
    ("R79-VIN-2", "vintage_eligibility",
     "Vintage-repro first-divergence documented; old trades stay non-causal.",
     ["artifacts/research/opencode_r79/b_vintage_repro.json"]),
    ("R79-VIN-3", "vintage_eligibility",
     "Availability rule enforced + 5 boundary tests (harness exit 2).",
     ["artifacts/research/opencode_r79/b_availability_tests.json"]),
    ("R79-ELIG-1", "vintage_eligibility",
     "Eligible/excluded table + prospective bundle (no profit promotion).",
     ["artifacts/research/opencode_r79/b_eligible_intervals.json"]),
    ("R79-R77", "observation_safety",
     "R77 CLI path NOT observation-safe (main still backdates; core lacks "
     "guards). Must not claim equal readiness. Upstream lines mapped.",
     ["configs/opencode_r79_roll.json:upstream_fix_map",
      "artifacts/research/opencode_r79/a_cli.md"]),
    ("R79-DEPLOY-AVAIL", "vintage_eligibility",
     "Deployment-availability log for fold bundles (prospective eligibility "
     "rests on simulated cutoff only).",
     []),
    ("R79-EDGE", "economics",
     "Economic edge / 3%/mo aspiration: goal, not evidence. No claim.",
     []),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tests-passed", type=int, required=True)
    ap.add_argument("--tests-failed", type=int, required=True)
    ap.add_argument("--tests-skipped", type=int, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    verdicts = {}
    for rid, cat, desc, ev in REQS:
        if rid == "R79-R77":
            status, note = ("FAIL",
                             "R77 main anchors observation at first "
                             "historical close; core has no missed-clock / "
                             "gap-pause / revision guards (roll-wrapper "
                             "only). Documented, not fixed (out of Track-A "
                             "write scope).")
        elif rid == "R79-DEPLOY-AVAIL":
            status, note = ("BLOCKED",
                             "No deploy log exists; file ctime is "
                             "Kaggle-download date, not training/availability "
                             "time. UNKNOWN, not invented.")
        elif rid == "R79-EDGE":
            status, note = ("NOT_EXERCISED",
                             "No profitability promotion this round; "
                             "3%/month + DD20% + 1x remain goals.")
        else:
            missing = [e for e in ev if e.startswith("tests/") or
                       e.startswith("artifacts/") or e.startswith("configs/")]
            ok = True
            for e in missing:
                ref = e.split("::")[0].split("(")[0]
                if not has(ref):
                    ok = False
            status, note = (("PASS", "Evidence present; suite green.")
                            if ok and a.tests_failed == 0 else
                            ("FAIL", "Missing evidence or failing tests."))
        verdicts[rid] = {"status": status, "category": cat,
                         "description": desc, "evidence": ev, "note": note}

    tally = {}
    for v in verdicts.values():
        tally[v["status"]] = tally.get(v["status"], 0) + 1
    blockers = [r for r, v in verdicts.items()
                if v["status"] in ("FAIL", "BLOCKED")]
    overall = ("PASS" if not blockers and
               verdicts["R79-EDGE"]["status"] == "PASS" else "WITHHELD")
    # EDGE is honestly NOT_EXERCISED, so overall can never be PASS this round.
    matrix = {
        "accept_version": MATRIX_VERSION, "exploratory": True,
        "live_orders": False,
        "supersedes": ("artifacts/research/opencode_r78_rolling/w3/"
                       "requirement_matrix.json (overall WITHHELD by R5; "
                       "R5 superseded by R79-KILL-1 PASS; R77 notes "
                       "superseded by R79-R77 FAIL with fix map)"),
        "overall": overall,
        "overall_rule": ("Overall PASS needs every requirement PASS with "
                         "non-empty evidence; WITHHELD otherwise. "
                         "R79-EDGE stays NOT_EXERCISED: no profit claim."),
        "withheld_by": blockers,
        "tallies": tally,
        "requirements": verdicts,
        "source_sha256": {
            "scripts/opencode_r78_roll.py": sha(
                "scripts/opencode_r78_roll.py"),
            "scripts/opencode_r77_advisor.py": sha(
                "scripts/opencode_r77_advisor.py"),
            "scripts/opencode_r77_advisor_core.py": sha(
                "scripts/opencode_r77_advisor_core.py"),
            "scripts/opencode_r79_vintage.py": sha(
                "scripts/opencode_r79_vintage.py"),
            "scripts/opencode_r79_matrix.py": sha(
                "scripts/opencode_r79_matrix.py"),
            "configs/opencode_r79_roll.json": sha(
                "configs/opencode_r79_roll.json"),
        },
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
