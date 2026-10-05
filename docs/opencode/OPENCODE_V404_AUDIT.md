# v404 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v404 (research/parallel/rounds/parallel-20260906-r2/v404; docstring = pre-registration): R2B1 (correlation-aware dip size, v400) on the 5-year 4-phase harness
rows R2B1G18_130 / R2B1G16_130 = R2B1 rule k 1.3 with engine gov (0.18, 0.10) / (0.16, 0.08), risk_mult k on the governor, sleeve_risk_budget 0.26 k;
reference R2B1_130 = v400 cache; per-year reset metric reset_metric.year_reset.
FIRST check the gov tuple reaches engine_user.simulate (governor formula g = clip((dd_zero - dd) / width, 0, 1) on the trailing 90-day peak). Part A (blind, before opening v404_result.json / run.log /
v404_runs.pkl): reproduce R2B1G18_130 on phase 1 and R2B1G16_130 on phase 3 with your own wiring and save replication.json (final equity, per-year net).
Part B: compare (final equity relative > 1e-6 = mismatch), recompute rows / folds / final with the v396 rank rule and the full-path DD (v388.mix) from the pkl.
COMPARISON.md with "## Verdict". At most 2 processes. Write only under `research/parallel/rounds/parallel-20260906-r2/v404_audit/` and
`tests/test_v404_audit.py`; relative paths without quoting. Do not edit leader files.
