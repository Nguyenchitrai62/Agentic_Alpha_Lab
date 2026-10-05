# v398 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v398 (research/parallel/rounds/parallel-20260906-r2/v398; docstring = pre-registration): R2-4P on the 5-year 4-phase harness of v396 (book = standard majors book, alts columns 0):
R2X11 = dip sleeve also on ADA AVAX DOGE LINK LTC TRX (alts 1m from data/raw/alts_intraday_20260926, books 0 for alts, alt rung size 1.0),
R2X11N = alt rung size 2.0; R2 reference = research/diagnostics/r2_decompose5/runs.pkl; per-year reset metric reset_metric.year_reset.
FIRST check that alts get no book weight and no data after 2026-09-24 is read. Part A (blind, before opening v398_result.json / run.log /
v398_runs.pkl): reproduce R2X11 on phase 1 and R2X11N on phase 3 with your own wiring and save replication.json (final equity, per-year net).
Part B: compare (final equity relative > 1e-6 = mismatch), recompute rows / folds / final with the v396 rank rule from the pkl.
COMPARISON.md with "## Verdict". At most 2 processes. Write only under `research/parallel/rounds/parallel-20260906-r2/v398_audit/` and
`tests/test_v398_audit.py`; relative paths without quoting. Do not edit leader files.
