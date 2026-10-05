# v391 + v392 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Versions research/parallel/rounds/parallel-20260906-r2/v391 and v392 (docstrings = pre-registration; prereg_sha256.txt) on the audited
multi-phase BOT harness (v376 / v388). Rows: R2_4P (= v388 cached R2), R2K (dip size = research/tournament/kelly/tables/kelly_v2_s{s}.parquet
lookup by (T = idx + 4h, sym, rung index), missing -> 1.0), R2C (research/tournament/context/tables/ctx_v2_s{s}.parquet), R2T (sleeve_tp = 1.5 for
every rung), R2K90 / R2K80 (kelly size x 0.9 / x 0.8, missing key -> mult x 1.0). FIRST audit the inputs: (a) the tournament tables
(research/tournament/kelly/build_tables.py, research/tournament/context/build_engine_tables.py) use only data before each bar open T + 1 minute
(repeat a truncation test on 10 random (phase, T, sym) per table family) and fold models trained only on rows with t_exit < anchor - 7 days
(read research/tournament/harness.py, research/tournament/kelly/kelly_sizing.py, research/tournament/context/run_variants.py); (b) no data at or
after 2025-09-24 is read anywhere. Then Part A (blind, before opening v391_result.json / v392_result.json / run logs / pkl caches): reproduce R2K
and R2T on phases 0 and 2 and R2K80 on phase 1 with your own wiring (phase_offset_full prep_idx / pipe_setup("v321"), v376/tables_hidden r2 table,
win_start 5) and save replication.json. Part B: compare (final equity relative > 1e-6, monthly > 0.01 pp, DD > 0.05 pp = mismatch), recompute
rows / folds / transfer of both versions from the pkls. COMPARISON.md with "## Verdict" PASS/FAIL per version.
At most 2 processes. Write only under `research/parallel/rounds/parallel-20260906-r2/v391_v392_audit/` and `tests/test_v391_v392_audit.py`;
relative paths without quoting. Do not edit leader or tournament files.
