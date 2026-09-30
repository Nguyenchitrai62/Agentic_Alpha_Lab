# v291 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v291 scales CB's book (0.2 A + 0.2 B + 0.2 Aq + 0.2 Bq + 0.1 D + 0.1 Dq, cached walk-forward members) per coin and bar by the agreement
a = |sum w m| / sum w |m| (C1: x a, C2: x a^2). Write only under `research/parallel/rounds/parallel-20260906-r2/v291_audit/` and
`tests/test_v291_audit.py`; relative paths without quoting; do NOT open v291/v291_result.json or v291/run.log before `replication.json`.
A: recompute a and the books independently, confirm a uses only same-bar member weights (no future rows), replicate CB_ref (5.864), C1,
C2 with the C4 engine arguments (close5, backstop 8, m_sleeve_sl 4, budget 0.18, v221.KW, G2 grid policy, win_start 5), the diag block,
selection (v286.dev_select, DD filter 2021-2024) and replaces_cb; the most recent year only for the selected row. B: compare with the JSON
(return > 1pp or DD > 0.5pp = mismatch); COMPARISON.md with "## Verdict" PASS/FAIL (feature timing, label windows, fit windows, fill
timing). Do not edit leader files.
