"""W3 requirement-matrix builder (r78_accept/1). PAPER ONLY, exploratory.

Reads configs/opencode_r78_accept.json (pre-spec) + evidence artifacts and
writes artifacts/research/opencode_r78_rolling/w3/requirement_matrix.json
and summary.json. Statuses: PASS/FAIL/BLOCKED/NOT_EXERCISED only.
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
VALID = ("PASS", "FAIL", "BLOCKED", "NOT_EXERCISED")
CATEGORIES = {"operational_readiness", "scenario_robustness", "economic_edge"}


def build_matrix(entries: dict, w1_present: bool,
                 pytest_summary: dict | None = None) -> dict:
    """entries: req_id -> {status, category, evidence[], note}.
    Enforces: W1-absent requirements cannot be PASS; overall PASS needs
    every required requirement PASS with non-empty evidence."""
    for rid, e in entries.items():
        assert e["status"] in VALID, f"{rid}: bad status {e['status']}"
        assert e["category"] in CATEGORIES, f"{rid}: bad category"
        if e["status"] == "PASS":
            assert e.get("evidence"), f"{rid}: PASS needs non-empty evidence"
    if not w1_present:
        for rid in ("R1", "R6"):
            if entries.get(rid, {}).get("status") == "PASS":
                raise ValueError(f"{rid} cannot PASS while W1 fix is absent")
    required = ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9",
                "R10", "R11", "R12"]
    missing = [r for r in required if r not in entries]
    assert not missing, f"matrix missing {missing}"
    incomplete = [r for r in required
                  if entries[r]["status"] != "PASS"]
    overall = "PASS" if not incomplete else "WITHHELD"
    tallies = {s: sum(1 for e in entries.values() if e["status"] == s)
               for s in VALID}
    return {"accept_version": "r78_accept/1",
            "exploratory": True, "live_orders": False,
            "w1_fix_present": bool(w1_present),
            "overall": overall,
            "overall_rule": ("Overall PASS needs R1..R12 all PASS with "
                             "non-empty evidence; withheld otherwise."),
            "withheld_by": incomplete,
            "tallies": tallies,
            "requirements": entries,
            "pytest": pytest_summary or {},
            "discipline": ("Operational readiness (R1-R7) vs scenario "
                           "robustness (R8, R10) vs economic edge (R12) are "
                           "reported separately. No execution fix is claimed "
                           "to improve returns.")}


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: opencode_r78_accept_matrix.py <entries.json>")
    entries = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    w3 = _ROOT / "artifacts" / "research" / "opencode_r78_rolling" / "w3"
    w1_present = bool(list((_ROOT / "artifacts" / "research" /
                            "opencode_r78_rolling" / "w1").glob("*")))
    matrix = build_matrix(entries, w1_present)
    w3.mkdir(parents=True, exist_ok=True)
    (w3 / "requirement_matrix.json").write_text(
        json.dumps(matrix, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"overall": matrix["overall"],
                      "tallies": matrix["tallies"],
                      "withheld_by": matrix["withheld_by"]}, indent=1))


if __name__ == "__main__":
    main()
