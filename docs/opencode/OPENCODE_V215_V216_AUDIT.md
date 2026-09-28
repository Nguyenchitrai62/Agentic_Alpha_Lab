# v215 + v216 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v215_v216_audit/` and `tests/test_v215_v216_audit.py`. Use relative
paths without quoting. Do NOT open v215/v215_result.json, v216/v216_result.json or their run logs until part A is saved
(`replication.json`); read the pre-registrations `v215/v215_policy_improvement.py`, `v216/v216_trade_grid.py`, `rl/trader_rl.py`.
A1 (v216, rule-based): re-implement the grid policy independently (flat -> open; reversed signal -> tighten + full limit exit;
signal gone -> full limit exit; otherwise at most one size adjustment per 6 bars since the last order: add |target| - w or reduce the
fraction (w - |target|)/w with a limit when the gap exceeds max(B_abs, B_rel*|target|); G1 0.02/0.25, G2 0.03/0.40, G3 0.05/0.60)
on the engine_user trade mode (you may use trade["policy"]); verify rule_S3 = 4.826 and rule_E1 = 4.216 dev4; report dev4, worst
first-four monthly, gate DD, fills, adds, reduces, limit exits; robust selection over G1..G3; last year only for the selected row.
A2 (v215, learned): leakage audit - for each year Y the models use transitions ending before Y - 7 days; features causal; Monte
Carlo returns stop when the position closes; cross-fitting by seed parity; the agent deviates only when both halves exceed the margin.
Re-run the deterministic driver (or an equivalent) and report the same metrics for P1..P3.
Save `replication.json`. B: compare with the result JSONs (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with PASS/FAIL and
any leakage finding. Do not report the most recent year of non-selected rows. Do not edit leader files.
