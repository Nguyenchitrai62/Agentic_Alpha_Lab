# v389 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Version research/parallel/rounds/parallel-20260906-r2/v389 (docstring = pre-registration) on the audited multi-phase BOT harness (v376 / v382):
rows R2_4P (standard CB books forward-filled to each clock) / R2pb_4P (phase-specific CB books research/diagnostics/phase_books/books_s{s}.parquet
for s = 1..3, standard for s = 0). FIRST audit the phase books: phase_books.py --phase 0 --native reproduces the cached members exactly (spot-check
3 members x 2 anchors); for s = 1..3 recompute 20 random 4h bars from raw 1h / 1m data on the shifted boundaries; per member and anchor the max
label end of the training rows < anchor - embargo (leakage_s*.json); repeat the truncation test on 5 random times per phase; confirm the index
convention (row t = bar opening at t, decided at t + 4h) and that the options / spot-premium inputs use only the last CLOSED standard bar.
Then recompute both rows, folds, transfer flag and final. Part A (blind, before opening v389_result.json / run logs / pkl caches): save
replication.json FIRST. Part B: compare (monthly > 0.01 pp, DD > 0.05 pp, F > 0.001 = mismatch); COMPARISON.md with "## Verdict" PASS/FAIL.
At most 2 processes. Write only under `research/parallel/rounds/parallel-20260906-r2/v389_audit/` and `tests/test_v389_audit.py`; relative paths
without quoting. Do not edit leader files.
