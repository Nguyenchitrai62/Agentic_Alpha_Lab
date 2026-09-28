# v232 + v233 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v232_v233_audit/` and `tests/test_v232_v233_audit.py`. Use relative paths
without quoting. Do NOT open v232/v232_result.json, v233/v233_result.json or their logs until part A is saved (`replication.json`); read
`v232/v232_disciplined_rl.py`, `v233/v233_tv_all_members.py`, `rl/trader_rl.py`, `v231/tv_indicators.py`.
A: (v233) verify the cached members artifacts/research/engine_real/member_{Aq_tv,B_tv,Bq_tv}.parquet against rebuilds of at least one
quarterly anchor (Aq_tv, Bq_tv) and one annual anchor (B_tv); run the v218 D2 trade mode on v231_V1 and T1..T3; report dev4, worst
first-four monthly, gate DD; robust selection; most recent year only for the selected row. (v232) re-run the rule G2 on the V1 books
(must be 5.462) and, if compute allows, the full agent pipeline (40 behaviour runs eps 0.03 seeds 100-139, per-action MC HGB models per
year on even/odd seeds, transitions ending before Y - 7 days, deviations only when both halves agree by the margin and the upnl sign
constraint holds); otherwise at least re-fit the 2023 models and check the agent's decisions on a 2023 sample. Check the causality of the
state (TV indicators and market features at the decision row, position state known at the decision) and of the training windows. Save
`replication.json`. B: compare with the result JSONs (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with a "## Verdict" PASS/FAIL,
explicitly checking feature timing, label windows, fit windows and fill timing. Do not edit leader files.
