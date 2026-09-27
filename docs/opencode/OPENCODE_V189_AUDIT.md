# v189 blind audit (read AGENTS.md (2026-09-27), .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v189_audit/` and `tests/test_v189_audit.py`. Use
relative paths without quoting. Do NOT open v189/ until part A is saved (`replication.json`). Base: your engine_user
replication from the v188 audit (`v188_audit/`); if it is not finished yet, implement engine_user from OPENCODE_V188_AUDIT.md.
A: members A, B, D from artifacts/research/engine_real/members_v154.parquet (check (A+B+D)/3 equals books_v154.parquet).
Pipelines P1 = A, P2 = (A+B)/2, P3 = (A+B+D)/3, each with and without the dip sleeve (sleeve SL 2 sigma_4h); book SL/TP
m = 4. Report per row monthly_dev4 (first four anchors), monthly_5y, last-year monthly, gate DD, losing years; the
selection = best monthly_dev4 among rows with DD <= 20 and no losing year in the first four years. Save `replication.json`.
B: compare with `v189/v189_result.json`; check the selection uses no last-year statistic. Write COMPARISON.md.
Do not edit leader files.
