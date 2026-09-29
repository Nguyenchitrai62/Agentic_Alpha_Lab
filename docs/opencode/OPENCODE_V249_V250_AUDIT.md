# v249 + v250 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v249_v250_audit/` and `tests/test_v249_v250_audit.py`. Use relative paths
without quoting. Do NOT open v249/v249_result.json, v250/v250_result.json or their logs until part A is saved (`replication.json`); read
`v249/v249_ladder_depth_agent.py`, `v250/v250_pyramid_ladder.py` and the `sleeve_filter` hook in `engine_user/engine_user.py` (a size multiplier
per (bar, coin, rung index), cached per bar, applied before the risk-budget check; a multiplier 0 skips the bid).
A1 (v249): six-rung ladder (2.0 .. 4.5 sigma_4h, same per-rung size, divisor 4 fixed). The standard window {2.5..4.0} via sleeve_filter must
reproduce v247 B18 (dev4 5.777, DD 19.65). Rebuild the per-(bar, coin, rung) counterfactual net returns from one unbudgeted run
(sleeve_risk_budget 10, every fill is immediately followed by its exit event), clipped to [-0.10, 0.05]; the state at the decision row (sigma
regime, 6/42-bar returns in sigma units from the next-bar opens = decision-bar close, TV SuperTrend dir / market-structure trend / WVF z,
order-level fl_big_imb6, the O1 book, hour of the holding bar); per anchor Y (2022..2025) fit per rung HGB on even / odd decision rows whose
holding bar ended before Y - 7 days; policy = window with the highest predicted 4-rung sum, deviate from standard only if both halves agree
and both beat standard by > margin (D1 0, D2 0.001); D3 always deep. Report dev4, worst first-four monthly, gate DD, window counts; robust
selection (v204.robust_select); most recent year only for the selected row.
A2 (v250): rung weights via sleeve_filter P1 (0.7, 0.9, 1.1, 1.3), P2 (0.4, 0.8, 1.2, 1.6), P3 (1.3, 1.1, 0.9, 0.7); equal weights must
reproduce 5.777. Same report and selection.
Save `replication.json`. B: compare with both result JSONs (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with a "## Verdict" PASS/FAIL,
explicitly checking feature timing, label windows, fit windows and fill timing. Do not edit leader files.
