# OpenCode task oc_bookichorizon - at which horizon does the DEPLOYED book's skill live? (cached member predictions, per year)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_bookichorizon/` and `tests/test_oc_bookichorizon.py`.
Print progress at least every 10 minutes. Descriptive only.

## Puzzle
oc_bookattrib: the deployed G2 book's realised weights earn by TIMING (block-shuffle placebo pct 96.8-100 every year 2021-2025).
oc_presamplebook / oc_presampleflow: TV-only, SPOT-flow and premium member rebuilds have ~0 OOS IC vs the 7-day label in every year, INCLUDING
2021-2024. oc_staleness (perp members, native labels) found quarter-to-quarter IC sign flips. Where is the skill?

## Method
Use the CACHED research predictions of the deployed members (the caches research_books_d2 reads: member_A_O1_orders, member_Aq_O1_orders,
member_B_tv, member_Bq_tv, members_v154[D], members_quarterly_D - see research/tournament/oc_memberdrop/run_memberdrop.py and
scripts/forward_v205.py) and the final blended book weights (after the bear filter) on the standard grid, 2021-09-24 .. 2025-09-23 (dev) plus
the most recent year labelled. Per year and per member and for the final book:
- Spearman IC of the prediction / weight vs the forward open-to-open return over h = 1, 2, 6, 18, 42 bars (vol-normalised by trailing 360-bar
  sigma), pooled over coins and per coin, with block bootstrap CIs (block = h, min 6);
- the cross-sectional IC (ranks across the 5 coins at each bar, averaged) vs the time-series IC (per coin over time) - which one carries it?
- the same for the sign only (hit rate).
Key question in bold: which horizon(s) and which dimension (cross-sectional vs time-series) hold the positive, stable IC that explains the
timing P&L? Vietnamese 3-line verdict.
