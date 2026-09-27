# v194 blind audit (read AGENTS.md (2026-09-27), .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v194_audit/` and `tests/test_v194_audit.py`. Use
relative paths without quoting. Do NOT open v194/ until part A is saved (`replication.json`). Base: your v193 replication
(`v193_audit/`) or engine_user replication in `v192_audit/` plus the v193 spec in OPENCODE_V193_AUDIT.md.
A: v193 with X = 0.08, varying only the rung take-profit TP = L (1 + k sigma_4h), k = 1, 1.5, 2. Report per k:
monthly_dev4, 5y, last year, gate DD, rungs, stops/TPs; selection = best dev4 with DD <= 20 and no losing year in the
first four years. Save `replication.json`.
B: compare with `v194/v194_result.json` (k = 1 must equal the v193 X = 0.08 row). Write COMPARISON.md. Do not edit leader files.
