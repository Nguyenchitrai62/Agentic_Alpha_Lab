# v317 + v318 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v317 builds the pooled-experience TV member (v94 horizon ensemble on v92 + 17 TradingView features + BTC cross features, trained on the 5 majors +
72 U2020 alts, annual and quarterly fits) and its majors-only control, then scores MANUAL rows (G2 manual rules and the v315 pullback rules, cap 2)
and BOT rows (G2 bar-open via the v306 machinery). v318 combines the pooled member books (M2 = (2A + 2PT + D)/5), the pullback entry (0.75 sigma_4h,
3 bars) and v309 management genes at cap 2. Scripts + docstrings: research/parallel/rounds/parallel-20260906-r2/v317/v317_pooled_tv_member.py and
v318/v318_manual_combo.py; member caches artifacts/research/engine_real/member_{PT,PTq,CT,CTq}_pooledtv.parquet.
Write only under `research/parallel/rounds/parallel-20260906-r2/v317_v318_audit/` and `tests/test_v317_v318_audit.py`; relative paths without
quoting; do NOT open v317/ or v318/ result JSONs or logs before replication.json is saved.
Part A: (1) re-fit the PT member for TWO anchors (2023-09-24 annual and the 2024-09-24 first-quarter refit) with your own code from the same panel
recipe and compare the books with the cache (max abs diff per bar); check the quarterly cutoffs (quarter start - (84 + 60) bars, labels end before);
(2) check leakage explicitly: TV features use bars up to the bar close; alt rows never enter the majors' predictions except through training;
the universe list is the Dec-2020 file; (3) replicate every MANUAL / BOT row of v317 and the full v318 grid, the fold choices, the transfer deltas
and the final rows from the cached member books (your own fitness / trade extraction; engine_user.simulate allowed). Save replication.json FIRST.
Part B: compare (monthly > 0.01 pp, DD > 0.05 pp, F > 0.001, book diff > 1e-9 = mismatch, report all); COMPARISON.md with "## Verdict" PASS/FAIL.
Do not edit leader files.
