# v402 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v402 (research/parallel/rounds/parallel-20260906-r2/v402; docstring = pre-registration): R2B1 (correlation-aware dip size, v400) on the 5-year 4-phase harness
rows R2B1e_130 / R2B1e_150 = flush detection at 2.0 sigma instead of 2.5 (n counts other majors with C[i,f-1,b] <= O[i,0,b](1 - 2.0 sig4)), R2B1_125 = 2.5 sigma with k 1.25, risk_mult k on the governor, sleeve_risk_budget 0.26 k;
reference R2B1_130 = v400 cache; per-year reset metric reset_metric.year_reset.
FIRST check the threshold parameter reaches the n computation (2.0 vs 2.5). Part A (blind, before opening v402_result.json / run.log /
v402_runs.pkl): reproduce R2B1e_130 on phase 1 and R2B1_125 on phase 3 with your own wiring and save replication.json (final equity, per-year net).
Part B: compare (final equity relative > 1e-6 = mismatch), recompute rows / folds / final with the v396 rank rule and the full-path DD (v388.mix) from the pkl.
COMPARISON.md with "## Verdict". At most 2 processes. Write only under `research/parallel/rounds/parallel-20260906-r2/v402_audit/` and
`tests/test_v402_audit.py`; relative paths without quoting. Do not edit leader files.
