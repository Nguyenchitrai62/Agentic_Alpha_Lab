# v241 + v242 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v241_v242_audit/` and `tests/test_v241_v242_audit.py`. Use relative paths
without quoting. Do NOT open v241/v241_result.json, v242/v242_result.json or their logs until part A is saved (`replication.json`); read
`v241/v241_sizing_policy.py` and `v242/v242_locked_sizing.py`.
A: reproduce the unscaled O1 run (dev4 5.690) and its per-coin attribution; rebuild the state (agree, strength, order-level flow, SuperTrend,
vol) and check it is known at the decision row; refit theta per anchor on bars ending before Y - 7 days with training-window
standardisation (report theta and training rows); build the multipliers (v241: per bar; v242: locked at the first row of each signal run with
|book| >= 0.05 and the same sign) and run the engine for P1..P3 and L1, L2; report dev4, worst first-four monthly, gate DD; robust selection
per version; most recent year only for each selected row. Save `replication.json`. B: compare with the result JSONs (return > 0.01pp/month,
DD > 0.05pp, theta > 0.01). COMPARISON.md with a "## Verdict" PASS/FAIL, explicitly checking feature timing, label (reward) windows, fit
windows and fill timing. Do not edit leader files.
