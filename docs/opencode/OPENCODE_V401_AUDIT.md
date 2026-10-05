# v401 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v401 (research/parallel/rounds/parallel-20260906-r2/v401; docstring = pre-registration): R2B1 (correlation-aware dip size, v400) on the 5-year 4-phase harness
rows R2B1R_130 / R2B1R_110 = rungs (2.5, 3, 3.5, 4, 5) + 2.0 appended (index 5, size 1 / TP 1 x the B1 multiplier), risk_mult k on the governor, sleeve_risk_budget 0.26 k;
reference R2B1_130 = v400 cache; per-year reset metric reset_metric.year_reset.
FIRST check the 2.0 rung uses the same causal level rule as the others. Part A (blind, before opening v401_result.json / run.log /
v401_runs.pkl): reproduce R2B1R_130 on phase 1 and R2B1R_110 on phase 3 with your own wiring and save replication.json (final equity, per-year net).
Part B: compare (final equity relative > 1e-6 = mismatch), recompute rows / folds / final with the v396 rank rule and the full-path DD (v388.mix) from the pkl.
COMPARISON.md with "## Verdict". At most 2 processes. Write only under `research/parallel/rounds/parallel-20260906-r2/v401_audit/` and
`tests/test_v401_audit.py`; relative paths without quoting. Do not edit leader files.
