# v345-v346 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Two versions in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration):
v345 BOT: v306 seed R2 run through v306.run_genome with the trade dict's book_mult set to 1.0 / 0.75 / 0.50 (engine_user trade mode: the book
position target is scaled, the signal threshold keeps the unscaled target, dip sizes unchanged); v306 BOT fitness; folds k = 1, 2, 3; transfer if a
smaller-book row is chosen and beats R2 on the unseen dev year in >= 2 of 3 folds; final on dev4; most recent year once.
v346 MANUAL: wired exactly as the audited v343 / v344 (CB books, book_mult 0.75, bracket dip limits 3.0 / 4.0 sigma, size_mult 4.375, budget 0.26,
sleeve_start 16, R2 agents per rung depth) with the native touch stop m_sleeve_sl 8 / 6 / 10 sigma (the budget counts the same distance);
fitness = v310.fitness with the all-trade win rate; folds k = 2, 3; final on dev4; most recent year once; stress row sleeve_start 31.
Write only under `research/parallel/rounds/parallel-20260906-r2/v345_v346_audit/` and `tests/test_v345_v346_audit.py`; relative paths without quoting;
do NOT open the two result JSONs or run logs before replication.json is saved. You may set the environment variable
KPACK=artifacts/kaggle/kpack/pack347 to use the fast packed engine inputs (same engine; check that the R2 reference reproduces dev4 7.079 and the
v346 reference 6.233 either way).
Part A: replicate every row (dev4, per-year, F), fold choices, transfer flags and final rows with your own wiring; check book_mult semantics in
engine_user.py, stop / budget distance in v346, and that no most-recent-year number enters any choice. Save replication.json FIRST.
Part B: compare (monthly > 0.01 pp, DD > 0.05 pp, F > 0.001, win > 0.001 = mismatch, report all); COMPARISON.md with "## Verdict" PASS/FAIL per
version. Do not edit leader files.
