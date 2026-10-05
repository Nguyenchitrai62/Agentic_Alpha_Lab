# v390 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Version research/parallel/rounds/parallel-20260906-r2/v390 (docstring = pre-registration; prereg_sha256.txt) on the audited multi-phase BOT
harness (v376 / v388). Rows: R2_4P (reference = v388 cached R2 runs, identical settings), R2X1_4P (book_size = min(1, s_ex / s_hist)),
R2X2_4P (book_size = clip(s_ex / s_hist, 0.5, 1.5)). s_hist = the engine_user formula target 0.25 / trailing 360-bar std of
W_BOOKS * sum(books.shift(2) * (o / o.shift(1) - 1)) * sqrt(6 * 365), cap 2 (NaN -> 1); s_ex = min(0.25 / sqrt(6 * 365 * w' C w), 2) with
w = 0.8 * book row i and C = sample covariance (np.cov, rows with any NaN dropped) of the 4h open-to-open returns of rows i-359..i (>= 120 rows;
otherwise ratio 1; book row all zero -> ratio 1). FIRST check causality: the ratio at row i must use opens up to row i only (truncate the opens
after row i on 5 random rows per phase and confirm the same ratio) and the book row i only. Then Part A (blind, before opening
v390_result.json / run.log / v390_runs.pkl): reproduce R2X1 and R2X2 on phases s = 0 and s = 2 with your own wiring (phase_offset_full
prep_idx / pipe_setup("v321"), v376/tables_hidden r2_table_s{s}.parquet, win_start 5) and save replication.json (final equity per phase and
run, ratio live mean). Part B: compare (final equity > 1e-6 relative, monthly > 0.01 pp, DD > 0.05 pp = mismatch), recompute rows / folds /
transfer from the pkl, confirm the reference rows equal v388's R2 runs. COMPARISON.md with "## Verdict" PASS/FAIL.
At most 2 processes. Write only under `research/parallel/rounds/parallel-20260906-r2/v390_audit/` and `tests/test_v390_audit.py`; relative paths
without quoting. Do not edit leader files.
