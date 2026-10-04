# v379-v380 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Versions in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration). Both evaluate the multi-phase BOT R2-4P exactly as v376
(audited PASS in v376_v377_audit): research/diagnostics/phase_offset_full prep_idx / pipe_setup on the standard index shifted by s = 0..3 h, books
forward-filled, agents ON with v376/tables_hidden/r2_table_s{s}.parquet, four never-rebalanced sub-accounts summed hourly, conservative intrabar DD,
BOT fitness (v306 formula), folds k = 2, 3, TRANSFER rule, final; most recent year only for a transferring final (neither transferred).
v379 rows R2_4P / R2BH_4P (dip rung sizes x0.5 via sleeve_filter while the BTC open of the holding bar < mean of the last 1200 4h opens on that
phase grid, full 1m history, min 600). v380 rows R2_4P / R2G16_4P (engine gov = (0.16, 0.08)) / R2G25_4P (gov = (0.25, 0.15)).
Check that the R2_4P reference reproduces v376 (dev4 R 5.24, DD 23.08) in both versions.
Part A (blind, before opening v379_result.json / v380_result.json / run logs / pkl caches): recompute every row, fold, transfer flag and final with
your own metric code; save replication.json FIRST. Part B: compare (monthly > 0.01 pp, DD > 0.05 pp, F > 0.001, win > 0.001 = mismatch, report
all); COMPARISON.md with "## Verdict" PASS/FAIL per version. At most 2 processes at a time (about 4-5 GB free RAM; other jobs run).
Write only under `research/parallel/rounds/parallel-20260906-r2/v379_v380_audit/` and `tests/test_v379_v380_audit.py`; relative paths without
quoting. Do not edit leader files.
