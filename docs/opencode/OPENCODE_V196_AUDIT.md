# v196 blind audit (read AGENTS.md (2026-09-27), .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v196_audit/` and `tests/test_v196_audit.py`. Use
relative paths without quoting. Do NOT open v196/ until part A is saved (`replication.json`). Base: your v193 replication.
A: v193 pipeline but the rung notional rn = 1.497 * g * 0.25/4/1.657 (independent of the books' scale s); variants
(books vol target, stop-risk budget X) = (0.25, 0.08), (0.20, 0.12), (0.15, 0.16). Report monthly_dev4, 5y, last year,
gate DD, rungs; selection = best dev4 with DD <= 20 and no losing year in the first four years. Save `replication.json`.
B: compare with `v196/v196_result.json`. Write COMPARISON.md. Do not edit leader files.
