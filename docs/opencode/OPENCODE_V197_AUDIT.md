# v197 blind audit (read AGENTS.md (2026-09-27), .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v197_audit/` and `tests/test_v197_audit.py`. Use
relative paths without quoting. Do NOT open v197/ until part A is saved (`replication.json`). Base: your v193 replication.
A: v193 pipeline (books target 0.25) with rung notional rn = s g mult 0.25/4/1.657 and stop-risk budget X = 0.08 * mult,
mult = 1, 1.5, 2. Report monthly_dev4, 5y, last year, yearly nets and 1m DDs, gate DD, rungs, liquidations; selection =
best dev4 with DD <= 20 and no losing year in the first four years. Also report for the selected mult: the 10 worst
1m-marked bars (dates, book vs sleeve), stop gaps, and the liquidation-check margin at the worst minute. Save `replication.json`.
B: compare with `v197/v197_result.json` (mult 1 must equal v193 X = 0.08). Write COMPARISON.md. Do not edit leader files.
