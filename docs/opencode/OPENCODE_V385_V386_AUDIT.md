# v385-v386 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Versions in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration), on the audited multi-phase BOT harness (v376 / v380).
v385 = ONE-SHOT most-recent-year test of order-book-depth dip sizing: thresholds q30 / q70 of D (bid+ask notional within 1 % / trailing 7-day
median, data/raw/bookdepth_20261004) at the fill minutes of the five majors' standard-grid fills with t_fill in 2023-01-01 .. 2025-09-16; at each
dip fill the R2 agent size is multiplied by 1.5 / 0.5 / 1.0 from D of the last snapshot strictly before the fill minute (<= 5 min old); the most
recent year mix of four sub-accounts started at the year start (as v376_final_hidden; the reference must give 3.902 %/month). Verify: the
thresholds, the as-of rule of D on 50 random fills, that no depth value at or after the fill minute is used, the process note (first run crashed on
a tz comparison; run_first_crash.log), and recompute both rows' most-recent-year and dev 2024-25 numbers and the adopt flag.
v386 = rows R2_4P / R2BK1_4P (engine sleeve_breaker 0.010) / R2BK2_4P (0.020); BOT fitness, folds k = 2, 3.
Part A (blind, before opening v385_result.json / v386_result.json / run logs / pkl caches): recompute; save replication.json FIRST. Part B: compare
(monthly > 0.01 pp, DD > 0.05 pp, F > 0.001 = mismatch); COMPARISON.md with "## Verdict" PASS/FAIL per version. At most 2 processes.
Write only under `research/parallel/rounds/parallel-20260906-r2/v385_v386_audit/` and `tests/test_v385_v386_audit.py`; relative paths without
quoting. Do not edit leader files.
