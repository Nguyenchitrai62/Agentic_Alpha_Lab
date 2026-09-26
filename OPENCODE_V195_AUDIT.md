# v195 blind audit (read AGENTS.md (2026-09-27), .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v195_audit/` and `tests/test_v195_audit.py`. Use
relative paths without quoting. Do NOT open v195/ until part A is saved (`replication.json`). Base: your v193 replication.
A: v193 pipeline with (books vol target, sleeve stop-risk budget X) = (0.25, 0.08), (0.20, 0.12), (0.15, 0.16); the
vol target changes s = min(target/vol, 2) everywhere (books and rung notional). Report monthly_dev4, 5y, last year,
gate DD, rungs; selection = best dev4 with DD <= 20 and no losing year in the first four years. Save `replication.json`.
B: compare with `v195/v195_result.json` ((0.25, 0.08) must equal v193 X = 0.08). Write COMPARISON.md. Do not edit leader files.
