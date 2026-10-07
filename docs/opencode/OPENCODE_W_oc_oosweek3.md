# OpenCode task oc_oosweek3 - clean forward evidence update (OOS scorer with new archive days + corrected prospective scorecard + paper ledgers)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/diagnostics/oc_oosweek3/` and `docs/opencode/OOS_WEEK3_20261007.md`
(the OOS scorer writes its own outputs in research/diagnostics/oc_bookoos/ by design - allowed; copy the previous results.json / REPORT.md there
to your folder as prev_* first). artifacts/bot/* and bot/ / backend/ are READ-ONLY; never start or stop processes.

## Steps
1. `research/diagnostics/oc_bookoos/score_oos.py --fetch --run` (heavy_slot). Last week it failed only because Binance had not yet archived
   2026-10-06 (docs/opencode/OOS_WEEK2_20261007.md); report the new window, daily returns, cumulative, DD, percentile vs the research band.
   If the newest day is still not archived, score what exists and say so.
2. `scripts/prospective_scorecard.py` (now with the correction window artifacts/research/advisor_shadow/paper_corrections.json and the two
   carry runners), `scripts/paper_report.py` (all seven runners: artifacts/bot/paper, paper_d17bf, paper_d13bf, paper_d17bfg2, paper_g2k20,
   paper_d17bfg2c, paper_g2k20c), `scripts/bot_health.py` on each. Save outputs.
3. Paper side ledgers: artifacts/bot/paper_carry (carry_paper), artifacts/bot/paper_straddle (straddle_paper; first entry Fri 2026-10-09),
   artifacts/research/kronos_shadow/kronos_features_live.parquet (count prospective vs late rows per (sym, shift) since start).
4. Runner continuity: list every gap > 10 minutes in each runner's hourly equity curve since 2026-10-07 12:00 UTC (restart after the dust fix)
   and any cycle_error / API error bursts.
5. Doc (Vietnamese, <= 50 lines): tables, verdict "consistent / inconsistent / too early" per pipeline, gaps.
