# v306 + v308 + v319 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Scripts / docstrings: research/parallel/rounds/parallel-20260906-r2/v306/v306_walkforward_evolution.py (BOT GA; dip-agent tables
artifacts/research/engine_real/v306_gene_tables.parquet built by v306/v306_gene_tables.py), v308/v308_manual_book_leverage_evolution.py (MANUAL GA),
v319/v319_pooled_path_flow_members.py (pooled path-label / flow members; caches member_{PP,PPq,PF,PFq}_pooled.parquet).
Write only under `research/parallel/rounds/parallel-20260906-r2/v306_v308_v319_audit/` and `tests/test_v306_v308_v319_audit.py`; relative paths
without quoting; do NOT open the three result JSONs, evolution.log or run logs before replication.json is saved.
Part A (the GAs are too expensive to re-run; audit EVALUATION + PROTOCOL as in v307_audit):
 v306: rebuild the v306 gene table for two (bar, symbol, rung) samples per fit from the pooled fills (or check its G2 slice reproduces
   artifacts/research/engine_real/v301_g2_table_m0.parquet exactly); re-simulate the 12 seeds and 8 random cached genomes (seed 7306) with your own
   genome -> engine_user call (members, lookup hooks, rung set, size / TP rules, C4 kwargs) and per-year metrics incl. book / rung win counts;
   check the fitness reads only training years and the most recent year only appears for the final E.
 v308: re-simulate the 11 seeds and 8 random cached genomes (seed 7308) incl. the gov / short / be_off / n_valid genes; same protocol checks.
 v319: refit PP for the 2023-09-24 anchor and PF for the 2024-09-24 first quarter and compare the books with the caches; check the path label
   (first touch from the next open, stop-first, same window as the return label) and that alt rows carry no flow values; replicate rows X0..X3,
   the fold choices and the final row.
Save replication.json FIRST. Part B: compare with the JSONs (monthly > 0.01 pp, DD > 0.05 pp, F > 0.001, books > 1e-9 = mismatch, report all);
COMPARISON.md with feature timing, label windows, fit windows, fill timing and "## Verdict" PASS/FAIL per version. Do not edit leader files.
