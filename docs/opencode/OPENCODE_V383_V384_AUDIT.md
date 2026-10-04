# v383-v384 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Versions in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration): Bitfinex-feature R2 dip agents
(research/diagnostics/phase_agents_bfx/build_bfx.py -> tables_bfx/r2_table_s{s}.parquet) evaluated on the audited phase harness:
v383 = BOT R2-4P rows R2_4P / R2bfx_4P (as v381: four never-rebalanced sub-books, conservative intrabar DD, BOT fitness, folds k = 2, 3);
v384 = MANUAL M5 rows M5 / M5bfx (as v377: single-clock phase-mean metrics, v310 goal-1 fitness, folds k = 2, 3). Neither transferred.
FIRST check the Bitfinex tables: (a) data/raw/bitfinex_20261004 panel vs 20 raw API rows (or the fetcher's stored raw pages); (b) x7..x10 joined to
training fills as of availability (stamp + 1 h) strictly before t_fill and to decision rows strictly before the shifted bar open + 1 min (50 random
rows per phase, recompute from the panel); (c) per anchor only fills with t_exit < anchor - 7 days; (d) with x7..x10 removed build_bfx reproduces
v376/tables_hidden (spot-check 500 rows). References must reproduce: R2_4P dev4 5.24 / DD 23.08; M5 4.094 / DD 24.4.
Part A (blind, before opening v383_result.json / v384_result.json / run logs / pkl caches): recompute every row, fold, transfer flag and final;
save replication.json FIRST. Part B: compare (monthly > 0.01 pp, DD > 0.05 pp, F > 0.001, win > 0.001 = mismatch); COMPARISON.md with
"## Verdict" PASS/FAIL per version. At most 2 processes (limited free RAM).
Write only under `research/parallel/rounds/parallel-20260906-r2/v383_v384_audit/` and `tests/test_v383_v384_audit.py`; relative paths without
quoting. Do not edit leader files.
