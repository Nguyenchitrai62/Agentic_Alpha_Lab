# OpenCode research task: dip-edge regime study (read AGENTS.md, OPENCODE_VF_COMMON.md, research/tournament/RULES.md)

Write ONLY under `research/tournament/oc_regime/` and `tests/test_oc_regime.py`; relative paths without quoting; at most 1 heavy process;
do not edit leader files, other workers' folders, the registry or docs. No orders, no credentials.

Question: the BOT's dip sleeve (limit bids k sigma_4h below each 4h bar open; R2 rungs 2.5/3/3.5/4/5) earned strongly in the 2024 test year
but little in 2021, 2022 and 2025-26 (research/diagnostics/r2_decompose5: dip-only %/month 0.59 / 0.43 / 1.30 / 3.16 / 0.34 for the years
starting 2021-09-24 .. 2025-09-24). Which slow market regimes (known at the bar open) separate good from bad dip periods - consistently?

Data: research/diagnostics/phase_agents/fills_U.parquet (every rung fill of 35 coins 2020-08..2025-09-24 with exact net returns y0.5/y1.0/
y1.5; columns documented in research/parallel/rounds/parallel-20260906-r2/v293/v293_pooled_exit_agent.py), research/tournament/data/
bar_open.parquet (same row order; bar-open features), research/tournament/context/market_features.parquet (market-wide features per row,
same order as research/tournament/harness.load(); check alignment by T/sym), research/tournament/data/hourly.parquet (hourly OHLC 35 coins).
If research/tournament/ext/fills_U_ext.parquet exists when you start, also use it for 2025-09-24..2026-09-23 (same format).

Part A (fixed BEFORE looking at outcomes - write PLAN.md first): define at most 8 SLOW regime variables computed daily from hourly.parquet
with data up to the day's start only (e.g. 30/90-day BTC trend, 30-day realized vol vs 1-year median, 30-day average cross-coin correlation,
30-day count of >3-sigma down-days in the market index, 30-day mean funding proxy is NOT available - skip it, market breadth of coins above
their 50-day mean). Part B: for the 5 majors' rungs (R2 depths), compute per calendar month the mean net y1.0 and the count; relate the
month's dip edge to the regime variables measured at the month start: Spearman per variable per year (2021..2025 anchors), and a leave-one-
year-out test of a single-threshold gate per variable (threshold = training-years median; gate = 'take dips only when variable on the good
side'): report the held-out-year mean edge with / without the gate. Report also the pooled 35-coin version. Mark a variable CONSISTENT only if
the sign is the same in >= 4 of 5 years AND the leave-one-year-out gate helps in >= 4 of 5 held-out years.
Causality: assert-based test that each regime value uses only hourly bars that ended before the day start (truncate & recompute, 20 random
days). Deliverables: PLAN.md, scripts, results.json, REPORT.md (tables + verdict), tests/test_oc_regime.py (causality + alignment tests).
