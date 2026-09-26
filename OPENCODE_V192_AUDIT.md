# v192 blind audit (read AGENTS.md (2026-09-27), .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v192_audit/` and `tests/test_v192_audit.py`. Use
relative paths without quoting. Do NOT open v192/ until part A is saved (`replication.json`). Base: your engine_user
replication in `v191_audit/`.
A: pipeline P2 = (A+B)/2 + sleeve with rung stop 5 sigma_4h, book SL/TP m = 4; book limit orders at open_1m(T, 0) *
(1 -/+ d) filled on a strict 1m trade-through in minutes 2 .. W-1, else expire: (d, W) = (0.001, 60), (0.001, 239),
(0.0003, 239). Report per variant monthly_dev4, 5y, last year, gate DD, fills/unfilled; selection = best dev4 with DD
<= 20 and no losing year in the first four years. Save `replication.json`.
B: compare with `v192/v192_result.json` ((0.001, 60) must equal v191 k=5). Write COMPARISON.md. Do not edit leader files.
