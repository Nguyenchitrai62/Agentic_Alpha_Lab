# v235 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v235_audit/` and `tests/test_v235_audit.py`. Use relative paths without
quoting. Do NOT open v235/v235_result.json or its logs until part A is saved (`replication.json`); read `v235/v235_sleeve_bandit_tv.py`,
`v220/v220_sleeve_bandit.py`, `v232/v232_disciplined_rl.py` (tv_frames) and `rl/trader_rl.py` (market_features).
A: on the T3 books (cached members artifacts/research/engine_real/member_{A_tv_annual,Aq_tv,B_tv,Bq_tv}.parquet) with the v218 D2 settings,
reproduce the unfiltered run (dev4 5.485), the filled-bid dataset (decision row, coin, rung, exit time, clipped net return), the per-year
HGB models (bids exited before Y - 7 days; report training sizes and the 25/75th percentiles of the in-sample predictions) and the
three filters S1 (skip predicted < 0), S2 (skip < q25), S3 (S2 + x1.25 above q75); report dev4, worst first-four monthly, gate DD, the
dev sleeve win rate and average per bid; robust selection; the most recent year only for the selected row. Check the causality of the
state (market features and TV indicators at the decision row; the bid is placed for the following holding bar) and of the fit windows.
Save `replication.json`. B: compare with the result JSON (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with a "## Verdict"
PASS/FAIL, explicitly checking feature timing, label windows, fit windows and fill timing. Do not edit leader files.
