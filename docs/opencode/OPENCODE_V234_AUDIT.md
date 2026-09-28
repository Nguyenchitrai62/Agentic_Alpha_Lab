# v234 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v234_audit/` and `tests/test_v234_audit.py`. Use relative paths without
quoting. Do NOT open v234/v234_result.json or its logs until part A is saved (`replication.json`); read `v234/v234_htf_indicators.py`
and `v231/tv_indicators.py`.
A: (1) check the causality of the higher-timeframe features: for >= 10 random 4h rows per symbol (BTC, XRP), recompute the daily and
weekly indicator values only from daily / weekly bars CLOSED by the 4h bar close (daily open + 1 day, Monday-week start + 7 days) and
compare with htf_frame; confirm weekly bars require 7 daily bars. (2) Verify the 8 cached members
artifacts/research/engine_real/member_{A,Aq,B,Bq}_{H1_daily,H2_daily_weekly}.parquet against rebuilds of at least one anchor each for
A_H1 and Aq_H1. (3) Run the v218 D2 trade mode on v233_T3 (must be 5.485), H1, H2; report dev4, worst first-four monthly, gate DD;
robust selection among H1/H2; most recent year only for the selected row. Save `replication.json`. B: compare with the result JSON
(return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with a "## Verdict" PASS/FAIL, explicitly checking feature timing, label windows, fit
windows and fill timing. Do not edit leader files.
