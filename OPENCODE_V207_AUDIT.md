# v207 blind audit (read AGENTS.md (2026-09-27), .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v207_audit/` and `tests/test_v207_audit.py`. Use
relative paths without quoting. Do NOT open v207/ until part A is saved (`replication.json`). Base: your v202/v205 replications.
A: monthly anchors 2021-09-24 + k months (k = 0..59), each model predicting only its month, same per-target cutoffs as the
v202 quarterly wrapping; verify at least one full monthly anchor of members A and B against
artifacts/research/engine_real/members_monthly.parquet, then use the cache. Books = (annual + quarterly + monthly)/3 of
v151 ((A+B)/2 per schedule); v205 rules. Reference = v205 selection. Report dev4, worst first-four-year monthly, gate DD
and the selected row's final score only; selection = robust criterion. Save `replication.json`.
B: compare with `v207/v207_result.json`. Write COMPARISON.md. Do not report the most recent year of non-selected rows.
Do not edit leader files.
