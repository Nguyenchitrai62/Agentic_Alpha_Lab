# v397 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v397 (research/parallel/rounds/parallel-20260906-r2/v397; docstring = pre-registration): R2-4P on the 5-year 4-phase harness of v396 with the
book weights transformed on the STANDARD grid before the shifted-clock forward fill: R2S = EMA(alpha = 1 - 0.5 ** (1/3), adjust=False),
R2L = clip(lower=0), R2SL = both; R2 reference = research/diagnostics/r2_decompose5/runs.pkl; per-year reset metric reset_metric.year_reset.
FIRST check the EMA is causal (row t uses rows <= t; truncation test on 10 rows). Part A (blind, before opening v397_result.json / run.log /
v397_runs.pkl): reproduce R2L on phase 1 and R2S on phase 3 with your own wiring and save replication.json (final equity, per-year net).
Part B: compare (final equity relative > 1e-6 = mismatch), recompute rows / folds / final with the v396 rank rule from the pkl.
COMPARISON.md with "## Verdict". At most 2 processes. Write only under `research/parallel/rounds/parallel-20260906-r2/v397_audit/` and
`tests/test_v397_audit.py`; relative paths without quoting. Do not edit leader files.
