# v187 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v187_audit/` and `tests/test_v187_audit.py`. Use
relative paths without quoting. Do NOT open v187/ until part A is saved (`replication.json`). Base: your v183 replication.
A: members A (v144 books_v142), B (v151 books_with_options), D (v154 books_coinbase) on the union index (missing -> 0);
you may read the leader cache artifacts/research/engine_real/members_v154.parquet (columns (member, symbol)) after
checking that (A+B+D)/3 equals artifacts/research/engine_real/books_v154.parquet. agree_t = sum_j |W_j| 1[sign A_j =
sign B_j = sign D_j != 0] / sum_j |W_j| (0 if sum 0); cap_t = 2 / 3 / 4 for agree < 0.6 / < 0.8 / >= 0.8;
s_t = min(0.25/vol_t, cap_t). Engine budget with perp gross / 10 (10x leverage setting) instead of / 5. Liquidation
check each live bar: futures equity = eq_min[i] - prev_eq * c * expo / 1.2; breach if < 0.01 * prev_eq * (sum|w| +
c * expo / 1.2 + rn * number of rungs taken in the bar). Rows: confidence cap, flat cap 4, cap 2 (all with the 10x
setting), normal and stress: monthly, 4h DD, 1m DD, liquidation count, cap distribution. Save `replication.json`.
B: compare with `v187/v187_result.json` (leader patches three lines of the v183 source; check nothing else changed).
Write COMPARISON.md. Do not edit leader files.
