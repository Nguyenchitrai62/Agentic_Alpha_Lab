# v376-v377 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Versions in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration). Both use the audited phase harness
(research/diagnostics/phase_offset_full/phase_offset_full.py prep_idx / pipe_setup, audited in v374_v375_audit) with the dip agents ON, keyed by
per-phase decision tables: research/diagnostics/phase_agents/tables/r2_table_s{s}.parquet (v376 dev) and v376/tables_hidden/r2_table_s{s}.parquet
(v377; dev rows identical + anchor-2025 rows). FIRST verify the per-phase tables: research/diagnostics/phase_agents/build_tables.py rebuilds the
deployed R2 table at s = 0 exactly (check 500 random rows vs artifacts/research/engine_real/v321_r2_table_m0.parquet) and, for s > 0, recompute 50
random rows' bar-open state features from raw 1m klines (state at the close of minute 0 of the SHIFTED bar only) and the anchor model choice (anchor
<= T, fills exited before anchor - 7 days).
v376 = multi-phase BOT: rows R2_1P (reference, phase-mean metrics), R2_4P, M5_4P, M5_4P_k12 (engine risk_mult 1.2); four never-rebalanced
sub-accounts summed on an hourly grid, conservative intrabar DD (bar minimum held over the bar's hours); BOT fitness (v306 formula); folds k = 2, 3;
TRANSFER; final; then v376_final_hidden.py: the most recent year ONCE for R2_4P (anchor-2025 table rows per phase; s = 0 must reproduce history_tm
v321 most recent year 5.655). Process note to verify: the first v376 run had a base-normalisation bug (run_first_bug.log, every equity ending at
1.0); confirm the fix (base = eq[first-1] if first > 0 else 1.0) and that nothing else changed (v376_runs.pkl is the cached second run).
v377 = MANUAL rows M5 / M5_B20 (dip budget 0.20) / M5_B20_BM10 (+ book_mult 1.0), phase-mean metrics, v310 goal-1 fitness, folds k = 2, 3.
Part A (blind, before opening v376_result.json / v376_final_hidden.json / v377_result.json / run logs / the pkl caches): recompute every row,
fold choice, transfer flag and final (and v376's most-recent-year step) with your own metric code; save replication.json FIRST. Part B: compare
(monthly > 0.01 pp, DD > 0.05 pp, F > 0.001, win > 0.001 = mismatch, report all); COMPARISON.md with "## Verdict" PASS/FAIL per version.
Long runs: <= 4 processes (16 GB RAM). Write only under `research/parallel/rounds/parallel-20260906-r2/v376_v377_audit/` and
`tests/test_v376_v377_audit.py`; relative paths without quoting. Do not edit leader files.
