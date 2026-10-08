# OpenCode task audit_d1 - BLIND audit of the downside-share dip tilt D1 (independent re-implementation)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/audit_d1/` and `tests/test_audit_d1.py`.
Print progress every 10 minutes. Engine via heavy_slot (one job at a time; RAM is tight). Long jobs: nohup + log under tmp/.

## Blind rule
Read research/tournament/oc_downshare/PLAN.md (the frozen spec) and the INPUT files only. Do NOT read oc_downshare's REPORT.md, results.json,
fits.json or scripts until your own numbers are written to audit_d1/replication.json (then compare in COMPARISON.md). Use
research/tournament/audit_c2 as the format template (its PLAN.md / REPORT.md structure, not its numbers).

## Tasks
1. Rebuild the D1 feature (trailing-6d downside-RV share, exactly as PLAN.md defines it) from the raw bars yourself, the per-anchor fits
   (harness rows t_exit < A - 7 d, shift-0 join, Spearman sign, q20 / q80) and the multiplier assignment; re-run REF and D1 in the 4-phase
   G2 engine for dev4 and the post-release year. Compare features (max abs diff), fits, multipliers, yearly %/month, DD, full-path DD.
2. Leakage checklist with code citations: feature timing (truncation test on 200 random rows), label windows, fit windows, fill timing; no
   statistic from a test year feeds a choice.
Verdict: PASS / PASS-WITH-NOTES / FAIL, Vietnamese 3 lines.
