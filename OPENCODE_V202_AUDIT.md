# v202 blind audit (read AGENTS.md (2026-09-27), .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v202_audit/` and `tests/test_v202_audit.py`. Use
relative paths without quoting. Do NOT open v202/ until part A is saved (`replication.json`). Base: your v199 replication.
A: quarterly walk-forward of the book members. Quarterly anchors = 2021-09-24 + k * 3 calendar months, k = 0..19; each
anchor's models predict only [anchor, next anchor) (last: until 2026-09-24); per-target cutoffs = anchor - embargo as
in the audited v92/v94/v103/v129 code. Re-build member A (v144 books_v142) and member B (v151 books_with_options) with
this schedule IN FULL for at least two quarterly anchors of your choice (e.g. 2022-03-24 and 2025-12-24) and compare
those rows with artifacts/research/engine_real/members_quarterly.parquet (columns (member, symbol)); then use the cache
for the full evaluation: pipelines (A+B)/2 annual (members_v154.parquet) and (Aq+Bq)/2 quarterly under engine_user with
the v197 rules. Report dev4, 5y, last year, gate DD, first-four yearly nets. Save `replication.json`.
B: compare with `v202/v202_result.json`; check that no quarterly model is trained on data at or after its anchor minus
the embargo and that predictions of a quarter come only from that quarter's model. Write COMPARISON.md.
Do not edit leader files.
