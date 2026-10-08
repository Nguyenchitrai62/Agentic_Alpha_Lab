# OpenCode task audit_cboost - BLIND audit of the B7 cascade-boost result
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/audit_cboost/` and `tests/test_audit_cboost.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) BEFORE any outcome. Engine via scripts/heavy_slot.py (RAM tight: one engine job at a
time). Long jobs: nohup + log under tmp/, poll the log; never inspect /proc or folders outside the workspace.

## Context
research/tournament/oc_cascadeboost: B7 = dip budget x1.5 for 7 days after a cascade bar (> 4 sigma 4h close-to-close move, definition of
oc_cascadedelay) is the dev4 robust pick (mean 6.74 / WORST 2.96 / DD 17.92 vs G2 5.60 / 2.59 / 16.91; 5y 6.36). CONTAMINATION: the idea was
formed after oc_cascadedelay's replica had covered all five years incl. the post-release year, so post-release numbers are labelled
diagnostics and new evidence must come from controls, unseen years, frictions and prospective paper.

## Blind rule
Read research/tournament/oc_cascadeboost/PLAN.md and oc_cascadedelay/PLAN.md (frozen specs) and the input files only; do NOT read
oc_cascadeboost's REPORT.md, results.json or scripts until your own numbers are saved to audit_cboost/replication.json, then compare in
COMPARISON.md (format of research/tournament/audit_c2).
## Tasks
Rebuild the cascade-bar flags yourself from the 4h closes (causal: the flag of a bar is known at its close; the boost applies only to dip
rungs whose holding bar opens AFTER that close), re-implement the x1.5 window and re-run REF and B7 in the 4-phase engine (dev4 + post-release
year). Leakage checklist with code citations (feature timing incl. a truncation test, window timing, fit windows, fill timing), and check that
the dip gross cap 2.0 and every G2 limit still bind under B7 (report how often the cap binds in boosted vs normal windows). Verdict PASS /
PASS-WITH-NOTES / FAIL, Vietnamese 3 lines.
