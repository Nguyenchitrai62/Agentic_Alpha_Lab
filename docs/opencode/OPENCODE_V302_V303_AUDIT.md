# v302 + v303 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Both extend v301 G2 (CB books, C4 rules, dip budget 0.26, pooled 35-coin dip agents) with three FLUSH-BREADTH features computed from the five majors only:
x7 b_mean = mean of the five majors' sp30 (30-minute log return / (sigma_1m sqrt 30)), x8 b_min = their min, x9 b_flush = number of majors whose 1m low since
minute 16 of the bar has crossed their own 2.5-sigma_4h bid level, all at minute f-1 of the rung's 4h bar. v302 tests H1 (size and TP agents use x0..x9) and
H2 (only the size agent); v303 repeats G2 (7 features) and H1 over five seeds (random_state base + 1000 x seed) with a median-based rule.
Write only under `research/parallel/rounds/parallel-20260906-r2/v302_v303_audit/` and `tests/test_v302_v303_audit.py`; relative paths without quoting; do NOT
open the v302 / v303 result JSONs or run logs before `replication.json`.
A: write your OWN breadth features from this description and check them against `v302/v302_flush_breadth.py::breadth_arrays` for look-ahead (a minute's
value may use only data up to that minute; the running minimum from minute 16 up to f-1, never beyond; the NaN handling), check that the pooled training
rows and the live-style hook state use the same definitions, that fits use only fills exited before anchor - 7 days, and the seed handling (seed 0 must
reproduce the v302 fits exactly). Replicate G2_ref (6.527 / DD 17.33), H1, H2 (v302 rows) and the ten v303 runs (G2_s0..4, H1_s0..4: dev4, worst dev year,
dev DD, dev win rate), the v302 drawdown-first rule (nothing selected) and the v303 median rule (nothing selected); no most-recent-year value for a
non-selected row. B: compare with the JSONs (return > 1pp or DD > 0.5pp = mismatch); COMPARISON.md with "## Verdict" PASS/FAIL per version (feature timing,
label windows, fit windows, fill timing). Do not edit leader files.
