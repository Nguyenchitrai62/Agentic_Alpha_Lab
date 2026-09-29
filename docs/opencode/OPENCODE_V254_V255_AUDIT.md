# v254 + v255 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v254_v255_audit/` and `tests/test_v254_v255_audit.py`. Use relative paths
without quoting. Do NOT open v254/v254_result.json, v255/v255_result.json or their logs until part A is saved (`replication.json`); read
`v254/v254_adaptive_ladder.py`, `v255/v255_sleeve_start.py` and in `engine_user/engine_user.py` the options prep["sig4_sleeve"] (sigma of
the 4h dip ladder only: rung levels, TP 1 sigma, stop 5 sigma, budget risk) and the argument sleeve_start (first holding-bar minute a
ladder bid may fill; default 16).
A1 (v254): confirm the defaults reproduce v247 B18 (dev4 5.777, DD 19.65). Re-implement rv_ratios independently: per holding bar the sum
of squared 1m log returns (the first minute of every cube row dropped, rescaled to 240 minutes, NaN if < 120 valid minutes), bars placed
on the full 4h time grid by start time (idx + 4h); row i reads the rolling means ending with the bar that STARTS at idx[i] (its decision
bar, closed at the decision); ratio_h = mean of the last h/4 bars / mean of the last 360 bars (min 180), clipped [0.25, 4]; check that
row i never uses the holding bar of row i. Run S1 (24h, power 0.5), S2 (24h, 1.0), S3 (4h, 0.5).
A2 (v255): run sleeve_start 5 and 10.
Report dev4, worst first-four monthly, gate DD; robust selection per version; most recent year only for each selected row. Save
`replication.json`. B: compare with both result JSONs (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with a "## Verdict" PASS/FAIL,
explicitly checking feature timing, fit windows (nothing fitted) and fill timing (no ladder fill before minute 5). Do not edit leader files.
