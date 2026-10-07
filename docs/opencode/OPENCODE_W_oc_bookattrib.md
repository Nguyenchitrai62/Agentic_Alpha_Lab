# OpenCode task oc_bookattrib - where does the deployed G2 BOOK's return come from? beta vs timing vs structure (attribution + placebo)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_bookattrib/` and `tests/test_oc_bookattrib.py`.
Print progress at least every 10 minutes.

## Why
research/tournament/oc_presamplebook: the TV-indicator 7-day member alone has ~0 out-of-sample IC in every year 2019-2025 (despite train IC
0.26-0.46), and oc_presample showed the dip sleeve alone earns only 0.6-3 %/month in 2021-2026 -> G2's 5.4 %/month is carried by the BOOK,
whose source of return is not established. If it is mostly long beta in the 2023-2024 bull years, live risk in a bear market is much higher
than the research says. (An older luck test, v209, found alpha t 3.5 / beta 0.08 for the 2026-09 D2 book; never redone for the deployed
book: 0.8 x O1 + 0.2 x CB members, trade mode, bear-book filter, 4 clocks.)

## Inputs
The deployed G2 engine runs: research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl (strategy R2B1D17BFG2; per phase 0..3). Find
what the pickle stores (equity, eq_min, possibly per-coin book weights / fills); if per-coin book target weights are not stored, regenerate
them read-only from the same pipeline the engine uses (research/diagnostics/phase_offset_full prep + pipe_setup as in v421's worker(); the
standard-grid book rows after the bear filter, forward-filled to each shifted clock). Prices: Binance perp 4h opens / 1m as the engine.

## Attribution (dev years 2021-09-24 .. 2025-09-23; the most recent year reported separately, labelled)
Per phase and 4-phase mean, per year, using the book's realised target weights w(c, t) and next-bar open-to-open returns r(c, t):
1. Book gross P&L B = sum w r (vectorised; check it reproduces the engine's book P&L share within a stated tolerance - if the engine
   book P&L is not separable, reproduce the book-only engine run instead: G2 with the dip sleeve OFF, 4 phases, heavy_slot).
2. BETA part = sum wbar(c, year) r (wbar = that coin's mean weight in that year); TIMING = B - BETA; also a market-beta regression of daily
   book returns on the equal-weight 5-coin return (alpha, beta, t-stats per year, Newey-West 5 days).
3. Placebo: 500 block-shuffles of w within each coin-year (block 42 bars, preserves weight distribution and persistence) -> distribution of
   sum w_perm r; report the actual timing P&L percentile per year.
4. Long-only / short-only split of B per year; bear-book filter contribution (book with vs without the x0.5 bear filter, vectorised).
Key question in bold: is the book's return mostly beta (bull years) or timing (positive in bear years, placebo pct >= 95)? Vietnamese 3-line
verdict with the honest live-risk implication.
