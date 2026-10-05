# v393 + v394 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v393 (MANUAL M5 single-clock 4-phase mean, v377 harness; rows M5 = v377 cached M5, M5K / M5C = dip size from research/tournament/kelly/tables/
kelly_v2_s{s}.parquet / research/tournament/context/tables/ctx_v2_s{s}.parquet via key (T = idx + 4h, sym, R2 rung index = history_tm.M3_R2_RUNG[r]),
missing -> 1.0) and v394 (multi-phase BOT harness of v388; rows R2_4P = v388 cache, R2K / R2C = v391 caches, R2KS6 / R2CS6 = kelly / context
size tables + m_sleeve_sl 6.0). Docstrings = pre-registration (prereg_sha256.txt). FIRST check the context tables' inputs: research/tournament/
context/build_engine_tables.py and run_variants.py use only data before T (+1 minute) and fold models trained on rows with t_exit < anchor - 7 days
(truncation test on 10 random (phase, T, sym)). Part A (blind, before opening result JSONs / run logs / pkl caches): reproduce M5C on phase 1
(v393) and R2CS6 on phases 0 and 3 (v394) with your own wiring and save replication.json. Part B: compare (final equity relative > 1e-6,
monthly > 0.01 pp, DD > 0.05 pp = mismatch), recompute rows / folds / transfer of both versions from the pkls, and recompute the AGENTS robust
criterion choice on v394's dev4 rows (DD <= 20, no losing year, mean >= 5, highest worst year). COMPARISON.md with "## Verdict" per version.
At most 2 processes. Write only under `research/parallel/rounds/parallel-20260906-r2/v393_v394_audit/` and `tests/test_v393_v394_audit.py`;
relative paths without quoting. Do not edit leader or tournament files.
