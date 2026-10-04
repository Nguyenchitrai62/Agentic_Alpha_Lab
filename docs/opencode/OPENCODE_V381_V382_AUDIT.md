# v381-v382 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Versions in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration), both on the audited multi-phase BOT harness of v376 /
v379 (phase_offset_full prep_idx / pipe_setup, four never-rebalanced sub-books on clocks shifted 0..3 h, conservative intrabar DD on the hourly mix,
BOT fitness, folds k = 2, 3; neither transferred, so no most-recent-year step ran). The R2_4P reference must reproduce v376 (dev4 R 5.24, DD 23.08).
v381 rows R2_4P (v376/tables_hidden) / R2aug_4P (research/diagnostics/phase_agents_aug/tables_aug). FIRST check the augmented tables: fills_phase.py
s = 0 fills equal research/diagnostics/phase_agents/fills_U.parquet; build_aug.py per anchor uses only fills with t_exit < anchor - 7 days from all
four phases (verify max t_exit per anchor); 50 random table rows per phase: state at the shifted bar open (minute-0 close) and the anchor model choice.
v382 rows R2_4P (research_books_d2) / R2O1_4P (research_books_o1) / R2T3_4P (research_books_t3) from scripts/forward_v205.py, forward-filled to the
shifted decision times (latest standard row <= t_s).
Part A (blind, before opening v381_result.json / v382_result.json / run logs / pkl caches): recompute every row, fold, transfer flag and final with
your own metric code; save replication.json FIRST. Part B: compare (monthly > 0.01 pp, DD > 0.05 pp, F > 0.001, win > 0.001 = mismatch, report
all); COMPARISON.md with "## Verdict" PASS/FAIL per version. At most 2 processes at a time (limited free RAM).
Write only under `research/parallel/rounds/parallel-20260906-r2/v381_v382_audit/` and `tests/test_v381_v382_audit.py`; relative paths without
quoting. Do not edit leader files.
