# OpenCode task: finish the 5-fold tournament inputs and re-score the existing ideas (read AGENTS.md, OPENCODE_VF_COMMON.md, research/tournament/RULES.md)

Write ONLY under `research/tournament/ext/` (existing folder; do not delete its files) and `tests/test_tournament5.py`. At most 1 heavy
process, RAM < 2.5 GB. No commits, no edits of leader files or other tournament folders (read-only use of their code is fine).
The former hidden year 2025-09-24..2026-09-23 is research data now: you MAY read market data up to 2026-09-24 00:00 UTC (nothing later).

State: research/tournament/ext/fills_U_ext.parquet is built (rows < 2025-09-17 identical to fills_U.parquet; see fills_check.json) and
harness5.py exists (5 folds, anchors 2021-09-24..2025-09-24, deployed baseline from research/parallel/rounds/parallel-20260906-r2/v376/
tables_hidden/r2_table_s0.parquet; graduation: gain > 0 in >= 4 of 5 years AND total > 0 AND worst day not > 20 % worse). The bar-open feature
build (prep_features_ext.py -> bar_open_ext.parquet / hourly_ext.parquet) was interrupted.

1. Run prep_features_ext.py to completion (it must read fills_U_ext.parquet and produce bar_open_ext.parquet + hourly_ext.parquet with hourly
   rows < 2026-09-24). Run check_features_ext.py (or write it if incomplete): rows overlapping research/tournament/data/bar_open.parquet must be
   identical (report max abs diff); causality: 20 random rows recomputed from 1m data truncated at the bar's minute-0 close are identical.
2. Extend the market-context features to the new rows by running research/tournament/context/build_market_features.py logic on hourly_ext
   (copy it into ext/, change only the input/output paths) -> market_features_ext.parquet; overlap with research/tournament/context/
   market_features.parquet must be identical (report).
3. Re-score with harness5 (same code paths, NO parameter changes, models refit per fold exactly as their scripts do): kelly V2 meanvar
   (research/tournament/kelly/kelly_sizing.py), context V2 hgb_mono (research/tournament/context/run_variants.py), tp V2 diff
   (research/tournament/tp/tp_bandit.py, with harness5's score_tp equivalent - add it to harness5 if missing, same formula as harness.score_tp).
   Port each scorer into ext/ as a thin wrapper that swaps the data paths and the harness module; assert that on the first 4 folds the sizes
   equal the original scored sizes for rows with t_fill < 2025-09-24 (report match share).
Deliverables: scores5_<idea>.json (per-year gains for 5 years, graduation), REPORT5.md with a table (idea x year gains, total, graduates, the
2025-26 fold separately), tests/test_tournament5.py (causality + alignment tests). Final line of REPORT5.md: one sentence verdict per idea.
