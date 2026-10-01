# v304 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v304 widens the dip ladder of the v301 G2 pipeline: engine argument `rungs` and the replica constant v293.RUNGS take the sets G2 (2.5, 3, 3.5, 4), R1 (2.0, 2.5, 3,
3.5, 4), R2 (2.5, 3, 3.5, 4, 5), R3 (2.0, 2.5, 3, 3.5, 4, 5); the pooled 35-coin experience and the S1 size / X4 take-profit agents are rebuilt for each set.
Write only under `research/parallel/rounds/parallel-20260906-r2/v304_audit/` and `tests/test_v304_audit.py`; relative paths without quoting; do NOT open
v304/v304_result.json or v304/run.log before `replication.json`.
A: reuse your v296 / v301 replicas; confirm for each set that (1) the replica fills and outcomes use the SAME rung depths as the engine run (the rung index r the
engine passes to the hooks maps to the right depth k, the state feature "rung depth" is k), (2) training rows are fills that exited before anchor - 7 days,
(3) the risk-budget check still counts every open rung's stop risk (so extra rungs share the 0.26 budget), (4) per-rung size stays rn = scale x governor x
size_mult x SIZE / 4 / S_REF x alignment x agent size (it does NOT shrink with more rungs - state the consequence). Replicate G2_ref (6.527 / 17.33), R1, R2,
R3 (dev4, worst dev year, dev DD, dev win rates, dip rung counts) and the return-first rule (nothing selected: R1 fails the DD condition). B: compare with the
JSON (return > 1pp or DD > 0.5pp = mismatch); COMPARISON.md with "## Verdict" PASS/FAIL (feature timing, label windows, fit windows, fill timing).
Do not edit leader files.
