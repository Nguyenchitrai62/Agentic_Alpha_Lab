# v248 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v248_audit/` and `tests/test_v248_audit.py`. Use relative paths without
quoting. Do NOT open v248/v248_result.json or its logs until part A is saved (`replication.json`); read `v248/v248_dip_exit_agent.py` and the
`sleeve_tp` hook in `engine_user/engine_user.py` (the take-profit multiple is chosen at the fill; None must reproduce the old results).
A: confirm the hook default reproduces v247 B18 (5.777); run the four fixed-TP engines (0.5 / 1.0 / 1.5 / 2.0 sigma) and match the fills on
(time, coin, rung); rebuild the fill state (pre-fill speed from the 1m closes up to the minute BEFORE the fill, rung, vol regime, SuperTrend
and order-level fl_big_imb6 at the decision row, hour) and check its causality; refit the per-action cross-fitted HGB models per anchor on
fills that exited before Y - 7 days; run T1 (margin 0), T2 (margin 0.0005), T3 (fixed 1.5). Report dev4, worst first-four monthly, gate DD,
the action counts; robust selection; most recent year only for the selected row. Save `replication.json`. B: compare with the result JSON
(return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with a "## Verdict" PASS/FAIL, explicitly checking feature timing, label windows, fit
windows and fill timing. Do not edit leader files.
