# v296 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v296 combines the v295 size agent (sleeve_fill_size) with the v294 X4 take-profit agent (sleeve_tp) and tests a 5-action size set
(skip / x0.5 / x1 / x1.5 / x2) on the pooled 35-coin dip experience (majors + causal U2020 alts, training only). Write only under
`research/parallel/rounds/parallel-20260906-r2/v296_audit/` and `tests/test_v296_audit.py`; relative paths without quoting; do NOT open
v296/v296_result.json or v296/run.log before `replication.json`.
A: reuse your v294 / v295 audit replicas where possible; confirm the size and TP models of each anchor use only fills that exited before
anchor - 7 days (mu included), the state features use data up to minute f-1, the hooks change only the majors' dip rungs (size before the
budget check, TP at the fill), x0 skips the rung; replicate CB_ref (5.864), S1_ref (6.275), J1, J2, J3 (agent counts, dev trade and dip-rung
win rates), selection (v286.dev_select among J1-J3, DD filter 2021-2024), replaces_s1, and the most recent year only for the selected row.
B: compare with the JSON (return > 1pp or DD > 0.5pp = mismatch); COMPARISON.md with "## Verdict" PASS/FAIL (feature timing, label
windows, fit windows, fill timing). Do not edit leader files.
