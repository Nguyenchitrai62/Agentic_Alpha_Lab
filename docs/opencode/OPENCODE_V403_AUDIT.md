# v403 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v403 (research/parallel/rounds/parallel-20260906-r2/v403; docstring = pre-registration): R2B1 (correlation-aware dip size, v400) on the 5-year 4-phase harness
rows R2B1T_130 = + book policy "tighten" when in a position with the signal flat and upnl < 0, R2B1S_130 = book m_sl 3.0 / m_tp 8.0, both with the R2B1 rule k 1.3, risk_mult k on the governor, sleeve_risk_budget 0.26 k;
reference R2B1_130 = v400 cache; per-year reset metric reset_metric.year_reset.
FIRST check the policy wrapper and m_sl override reach the engine. Part A (blind, before opening v403_result.json / run.log /
v403_runs.pkl): reproduce R2B1T_130 on phase 1 and R2B1S_130 on phase 3 with your own wiring and save replication.json (final equity, per-year net).
Part B: compare (final equity relative > 1e-6 = mismatch), recompute rows / folds / final with the v396 rank rule and the full-path DD (v388.mix) from the pkl.
COMPARISON.md with "## Verdict". At most 2 processes. Write only under `research/parallel/rounds/parallel-20260906-r2/v403_audit/` and
`tests/test_v403_audit.py`; relative paths without quoting. Do not edit leader files.
