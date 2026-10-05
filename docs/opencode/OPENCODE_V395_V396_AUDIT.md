# v395 + v396 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v395 (R2CS6_4P final gate over 2021-09-24..2026-09-23: context size tables dev + hidden (research/tournament/context/tables/ctx_v2_s{s} /
ctx_v2_hidden_s{s}, hidden rows replace dev rows for T >= 2025-09-24), m_sleeve_sl 6, continuous 4-phase mix metrics) and v396 (R2 vs
book_mult 1.25 + budget 0.20 / book_mult 1.5 + budget 0.13 / book_mult 1.5 sleeve off; reference R2 runs = research/diagnostics/r2_decompose5/
runs.pkl; per-year RESET metric research/diagnostics/r2_decompose5/reset_metric.py). Docstrings = pre-registration. FIRST: check the hidden
context tables' fold model trains only on fills with t_exit < 2025-09-17 and features use data <= T (+1 min) (truncation test, 10 rows).
Part A (blind, before opening v395_result.json / v396_result.json / run logs / pkl caches): reproduce v395 phase 1 and v396 R2B150 phase 2
with your own wiring (phase_offset_full prep_idx on the FULL standard index + shift, pipe_setup("v321"), v376/tables_hidden r2 table, win_start 5)
and save replication.json (final equity, per-year net). Also recompute r2_decompose5's R2 phase 0 final equity. Part B: compare (final equity
relative > 1e-6 = mismatch), recompute v396 rows / folds from its pkl with the reset metric, check reset_metric.year_reset against an
independent implementation on 2 rows. COMPARISON.md with "## Verdict" per version.
At most 2 processes. Write only under `research/parallel/rounds/parallel-20260906-r2/v395_v396_audit/` and `tests/test_v395_v396_audit.py`;
relative paths without quoting. Do not edit leader or tournament files.
