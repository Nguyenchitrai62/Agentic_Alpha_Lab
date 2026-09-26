# v185 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v185_audit/` and `tests/test_v185_audit.py`. Use
relative paths without quoting. Do NOT open v185/ until part A is saved (`replication.json`). Base: your v183
replication in `v182_v183_audit/`.
A: identical to v183 except the rung notional is rn = s[i] * 0.25/4 / 1.657 (the governor g is NOT applied to the
sleeve; it still scales books and carry and is computed from total equity). Normal and stress rows: monthly, 4h DD,
1m-marked DD, worst bar, taken/TP/cancelled. Save `replication.json`.
B: compare with `v185/v185_result.json` (the leader builds it by patching the v183 source text; check that exactly
that one line changed). Write COMPARISON.md. Do not edit leader files.
