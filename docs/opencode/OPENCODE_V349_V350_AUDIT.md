# v349-v350 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Two versions in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration) on the deployed MANUAL structure M3 (kpack inputs:
KPACK=artifacts/kaggle/kpack/pack347; reference dev4 6.233; wiring as the audited v347 run_genome with the CB seed):
v349 = hour-of-day dip size multipliers from pooled pre-anchor fills (v349_pooled_fills.py -> artifacts/research/engine_real/v349_pooled_fills_m3.parquet;
rebuild the fills for TWO coins yourself and compare), v350 = dip-agent tables refitted on M3-rule outcomes (v350_m3rule_tables.py ->
artifacts/research/engine_real/v350_m3rule_tables.parquet; refit ONE anchor of fit M34 yourself and compare predictions).
Part A (blind, before opening result JSONs / run logs): replicate every row (dev4, per-year, F), fold choices, transfer flags and final rows; check
that every hour table / agent fit uses only fills with t_exit < anchor - 7 days, that predictions use the bar-open state, and that no most-recent-year
number enters any choice. Save replication.json FIRST. Part B: compare (monthly > 0.01 pp, DD > 0.05 pp, F > 0.001, win > 0.001, predictions > 1e-9 =
mismatch, report all); COMPARISON.md with "## Verdict" PASS/FAIL per version.
Write only under `research/parallel/rounds/parallel-20260906-r2/v349_v350_audit/` and `tests/test_v349_v350_audit.py`; relative paths without quoting.
Do not edit leader files.
