# v305 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v305 keeps the v304 R1 dip ladder (2.0, 2.5, 3, 3.5, 4 sigma; S1 size + X4 take-profit agents rebuilt on that rung set exactly as v304 R1, 35-coin pooled
experience, fits on fills exited before anchor - 7 days) and moves two risk dials: the dip-sleeve risk budget `sleeve_risk_budget` and the book vol `target`.
Rows: Q1_b22 (budget 0.22, target 0.25), Q2_b18 (0.18, 0.25), Q3_t22_b26 (0.26, 0.22), Q4_t22_b22 (0.22, 0.22); references G2_ref (4 rungs 2.5..4, budget
0.26, target 0.25: dev4 6.527, dev DD 17.33) and R1_ref (5 rungs, 0.26 / 0.25: dev4 7.807, dev DD 20.25) must reproduce. Everything else = v304 (C4 rules
close5 stop 4 sigma + 8-sigma backstop, grid trade mode v221 B_ABS / B_REL, win_start 5, engine_user fees / adverse funding).
Selection (dev years only): pool = Q rows with dev DD <= 17.33 + 0.3, worst dev year >= 3.0 %/month, no losing dev year; highest dev4 (ties lower DD);
replaces G2 only if dev4 >= G2_ref + 0.3. dev DD = max yearly 1m-marked DD over the first four anchors (v286.dev_dd); worst = v204.worst_month.
Write only under `research/parallel/rounds/parallel-20260906-r2/v305_audit/` and `tests/test_v305_audit.py`; relative paths without quoting; do NOT open
v305/v305_result.json or v305/run.log before `replication.json`.
A: reuse your v304 replica (research/parallel/rounds/parallel-20260906-r2/v304_audit); confirm that the budget and target arguments reach the engine
(budget = stop-risk sum check of every open rung, target = book vol target before the cap 2 and the governor) and that nothing else changes between rows;
replicate G2_ref, R1_ref and Q1..Q4 (dev4, worst dev year, dev DD, dev yearly net / 1m DD, dev trade win rate, dip rung count and rung win rate) and the
selection rule. Save replication.json FIRST. B: compare with the JSON (dev4 or worst > 0.01 pp, DD > 0.05 pp = mismatch; report all); COMPARISON.md with
feature timing, label windows, fit windows, fill timing and "## Verdict" PASS/FAIL. Do not edit leader files.
