# v199 blind audit (read AGENTS.md (2026-09-27), .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v199_audit/` and `tests/test_v199_audit.py`. Use
relative paths without quoting. Do NOT open v199/ until part A is saved (`replication.json`). Base: your v197/v198
replication, UPDATED to the two conventions adopted from the v188 audit: (1) the 1m-marked DD uses peaks over the
minute path (intrabar highs count), (2) a stop on the held position wins a same-minute tie with a new book fill (the
pending order is cancelled).
A: v197 pipeline (v151 books, sleeve rung size x1.5, stop-risk budget 0.12, rung stop 5 sigma_4h, TP 1 sigma_4h) with
ladders (2.5, 3, 3.5, 4), (2.5, 3, 3.5, 4, 5, 6), (3, 4, 5, 6) sigma_4h; per-rung notional fixed at s g 1.5 0.25/4/1.657
regardless of the number of rungs. Report dev4, 5y, last year, gate DD, rungs; selection = best dev4 with DD <= 20 and
no losing year in the first four years. Save `replication.json`.
B: compare with `v199/v199_result.json`. Write COMPARISON.md. Do not edit leader files.
