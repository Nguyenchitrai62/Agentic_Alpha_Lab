# oc_fomcbook PLAN (pre-registered BEFORE any outcome is computed)

Idea #66 (NEW): scheduled FOMC statements and the BOOK.

## Hypothesis (fixed here)

Scheduled FOMC-statement releases inject information-driven volatility
into the 4h holding window; a slow momentum book held across the
statement (entered before, held through the release and the immediate
post-release digestion) takes event risk it is not paid for. Halving ALL
book targets (both sides) on holding bars that start in the 24 hours
before a scheduled statement through 4 h after it should therefore leave
the book path's max drawdown not worse at a small yearly-P&L cost,
because event-window bars are a small minority of bars.
Sign/universality is read from the data; consistency across anchor years
is what matters (rule below). ONE scored rule only.

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (= `oc_bookic` formula: `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`,
  `d2 = 0.8*o1 + 0.2*(D+Dq)/2`, union index, missing -> 0.0) from
  `artifacts/research/engine_real/` member caches.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens,
  history from 2017 so every scored year has a full 1200-bar bear window).
- Calendar: HARD-CODED below (no file read, no fetch at compute time).
  All dates are scheduled FOMC meetings published months in advance on
  federalreserve.gov, hence known before each anchor year (no leakage).
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override;
  all five years are research data; any finding needs prospective
  validation).
- LIGHT job: one process, 4h opens + book parquets only (no 1m data),
  RAM < 1 GB.

## FOMC statement calendar (fixed constants, scheduled meetings only)

Source: Federal Reserve Board official meeting calendars,
https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
(schedules announced ~1 year ahead, e.g. the 2025-2026 tentative schedule
press release of 2024-08-09,
https://www.federalreserve.gov/newsevents/pressreleases/monetary20240809a.htm).
The Committee releases a policy statement at 2 p.m. Eastern Time on the
second day of each regularly scheduled meeting. Unscheduled meetings /
notation votes (e.g. Mar 3 / Mar 15 2020, Aug 22 2025) are EXCLUDED.

Statement instant R = date at 14:00 ET = 18:00 UTC when US daylight saving
is in effect (EDT, second Sunday of March to first Sunday of November),
19:00 UTC otherwise (EST). Assignment shorthand "18:00 UTC +-1h by DST".

| # | statement date | R (UTC) | DST? |
|---|---|---|---|
| 2020-01 | 2020-01-29 | 19:00 | EST |
| 2020-02 | 2020-03-18 | 18:00 | EDT (DST from Mar 8) |
| 2020-03 | 2020-04-29 | 18:00 | EDT |
| 2020-04 | 2020-06-10 | 18:00 | EDT |
| 2020-05 | 2020-07-29 | 18:00 | EDT |
| 2020-06 | 2020-09-16 | 18:00 | EDT |
| 2020-07 | 2020-11-05 | 19:00 | EST (DST ended Nov 1) |
| 2020-08 | 2020-12-16 | 19:00 | EST |
| 2021-01 | 2021-01-27 | 19:00 | EST |
| 2021-02 | 2021-03-17 | 18:00 | EDT (DST from Mar 14) |
| 2021-03 | 2021-04-28 | 18:00 | EDT |
| 2021-04 | 2021-06-16 | 18:00 | EDT |
| 2021-05 | 2021-07-28 | 18:00 | EDT |
| 2021-06 | 2021-09-22 | 18:00 | EDT |
| 2021-07 | 2021-11-03 | 18:00 | EDT (DST ended Nov 7) |
| 2021-08 | 2021-12-15 | 19:00 | EST |
| 2022-01 | 2022-01-26 | 19:00 | EST |
| 2022-02 | 2022-03-16 | 18:00 | EDT (DST from Mar 13) |
| 2022-03 | 2022-05-04 | 18:00 | EDT |
| 2022-04 | 2022-06-15 | 18:00 | EDT |
| 2022-05 | 2022-07-27 | 18:00 | EDT |
| 2022-06 | 2022-09-21 | 18:00 | EDT |
| 2022-07 | 2022-11-02 | 18:00 | EDT (DST ended Nov 6) |
| 2022-08 | 2022-12-14 | 19:00 | EST |
| 2023-01 | 2023-02-01 | 19:00 | EST |
| 2023-02 | 2023-03-22 | 18:00 | EDT (DST from Mar 12) |
| 2023-03 | 2023-05-03 | 18:00 | EDT |
| 2023-04 | 2023-06-14 | 18:00 | EDT |
| 2023-05 | 2023-07-26 | 18:00 | EDT |
| 2023-06 | 2023-09-20 | 18:00 | EDT |
| 2023-07 | 2023-11-01 | 18:00 | EDT (DST ended Nov 5) |
| 2023-08 | 2023-12-13 | 19:00 | EST |
| 2024-01 | 2024-01-31 | 19:00 | EST |
| 2024-02 | 2024-03-20 | 18:00 | EDT (DST from Mar 10) |
| 2024-03 | 2024-05-01 | 18:00 | EDT |
| 2024-04 | 2024-06-12 | 18:00 | EDT |
| 2024-05 | 2024-07-31 | 18:00 | EDT |
| 2024-06 | 2024-09-18 | 18:00 | EDT |
| 2024-07 | 2024-11-07 | 19:00 | EST (DST ended Nov 3) |
| 2024-08 | 2024-12-18 | 19:00 | EST |
| 2025-01 | 2025-01-29 | 19:00 | EST |
| 2025-02 | 2025-03-19 | 18:00 | EDT (DST from Mar 9) |
| 2025-03 | 2025-05-07 | 18:00 | EDT |
| 2025-04 | 2025-06-18 | 18:00 | EDT |
| 2025-05 | 2025-07-30 | 18:00 | EDT |
| 2025-06 | 2025-09-17 | 18:00 | EDT |
| 2025-07 | 2025-10-29 | 18:00 | EDT (DST ended Nov 2) |
| 2025-08 | 2025-12-10 | 19:00 | EST |
| 2026-01 | 2026-01-28 | 19:00 | EST |
| 2026-02 | 2026-03-18 | 18:00 | EDT (DST from Mar 8) |
| 2026-03 | 2026-04-29 | 18:00 | EDT |
| 2026-04 | 2026-06-17 | 18:00 | EDT |
| 2026-05 | 2026-07-29 | 18:00 | EDT |
| 2026-06 | 2026-09-16 | 18:00 | EDT |
| 2026-07 | 2026-10-28 | 18:00 | EDT (DST ended Nov 1) |
| 2026-08 | 2026-12-09 | 19:00 | EST |

56 statement instants, 2020-2026. Only instants with
`R - 24h` before CUTOFF can flag grid bars (2026-12-09 is inert).

## Exact causal definitions (fixed now, before seeing numbers)

- Grid: inner join of the book index with the opens index (dropna all),
  sorted 4h grid; `T` in `[2021-09-24, 2026-09-24)` UTC; the last grid bar
  (no forward open) is dropped and every kept bar must have all 5 forward
  opens non-NaN with the forward open at/before
  `CUTOFF = 2026-09-24 00:00 UTC` (same boundary as oc_dvolshort /
  oc_bookevent). Weight `w[T,s]` is known at the close of bar `T` and is
  held over `[T, T+1)`.
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years partition the grid
  with no gaps/overlaps: `Y_k = [B_k, B_{k+1})`, `B = ANCHORS +
  [2026-09-24]`.
- Bear filter FIRST (audited v410, mirrors oc_bookevent BASE exactly): on
  the FULL BTC opens history, `MA1200[T] = mean(BTC_open[T-1199..T])` via
  `rolling(1200, min_periods=600).mean()`; `bear[T] iff BTC_open[T] <
  MA1200[T]` (strict; equality or NaN-MA -> not bear). Flag at `T` uses
  `open[T]` inclusive, i.e. known at the close of bar `T`.
  `BASE[T,s] = 0.5 * w[T,s] where bear[T] and w[T,s] > 0, else w[T,s]`
  (longs halved in bear; shorts/flat unchanged). BASE is the control path.
- Event window (grid time + fixed calendar only, hence causal at bid time
  T because the schedule is pre-published):
  `RULEBAR(T) = 1 iff exists statement instant R with R - 24h <= T <= R + 4h`
  (holding bars that START in the 24 hours before the statement through
  4 h after it; both endpoints inclusive). With the 4h grid this flags ~7
  bars per statement. No market data after T is used.
- Rule (fixed, from the assignment): `RULE[T,s] = 0.5 * BASE[T,s]` where
  `RULEBAR(T)`, else `BASE[T,s]` (all five coins; longs, shorts and flats
  alike; flats stay flat). No fitted parameter, no threshold to learn.
- Returns: `R1[T,s] = open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- Costs (assignment gate model): 0.0005 (0.05%) per unit turnover. Per
  (T, s) in grid order: `cost[T,s] = 0.0005 * |w[T,s] - w_prev[s]|` with
  `w_prev` = the previous grid bar's weight for the same sym (first grid
  bar: prev = 0). Same formula applied to each path with its OWN prev
  (BASE prev for BASE, RULE prev for RULE). Net cell:
  `pnl = w * R1 - cost` per path.
- Book path per variant: per-bar portfolio return `rp[T] = sum_s pnl[T,s]`
  over the 5 coins. Per anchor year, equity is reset to 1.0 at the year's
  first bar and compounded in grid order: `eq[i+1] = eq[i] * (1 + rp[T_i])`
  (exactly as oc_dvolshort / oc_bookevent). Full 5y path compounds the
  same way from the first bar of year 1 (context only). maxDD of a path =
  `max_{peak<trough} (1 - eq_trough / eq_peak)`. Worst week = minimum
  42-bar (7-day) compounded return inside the year:
  `min_{i>=42} (eq[i]/eq[i-42] - 1)`.
- Book P&L per year (primary): linear net sums `sum(pnl)` over all year
  rows (same scale as oc_bookevent's `total_pnl`), BASE vs RULE.
  Event-window attribution: linear net sums over RULEBAR rows only, BASE
  vs RULE (fixed window membership, both paths compared on identical
  rows). Coverage: share of grid bars with RULEBAR=1 per year (share of
  (T, sym) rows affected is identical since the flag is per-bar).

## Evaluation (fixed here — one variant only)

- Per anchor year report: n_bars, RULEBAR share; event-window
  (RULEBAR rows) book P&L BASE vs RULE (net linear sums); TOTAL book P&L
  BASE vs RULE (net linear sums); worst week BASE vs RULE; book maxDD
  BASE vs RULE (per-year reset paths). Full-5y path maxDD/total (context).
- DECISION RULE (assignment-specific, replaces the default for the
  verdict): PROMISING only if (a) book maxDD not worse
  (RULE maxDD strictly <= BASE maxDD, tolerance 1e-12) in >= 4/5 years
  AND (b) total book P&L retains >= 98% of BASE
  (RULE >= 0.98 * BASE, tolerance 0; if BASE <= 0 in a year that year
  counts as FAIL for leg (b); NaN on either side counts as FAIL) in
  >= 4/5 years. One-line verdict.
- LOYO stability (descriptive side row, NOT part of the verdict — there
  is no fitted parameter to leave out; the calendar and multipliers are
  fixed constants, oc_bookevent precedent): for the DD-not-worse
  indicator and the retention indicator, held-out year h passes iff the
  held-out indicator equals the majority indicator of the other four
  years. Reported as `loyo_dd`, `loyo_ret = n/5`.
- Cost context: weights average << 1; the portfolio sums and equity paths
  above are the scale that matters. Vectorised open-to-open screen only
  (no vol target, governor, dip sleeve, funding, SL/TP, or engine limit
  path).

## Causality / alignment tests (tests/test_oc_fomcbook.py)

- test_results_exists_and_schema: results.json has meta/years/full_path/
  loyo/decision with the pre-registered fields; panel has 5 rows per bar.
- test_rulebar_from_hardcoded_calendar_only: RULEBAR recomputed from grid
  times + the hard-coded FOMC list only; hand checks: bar at R-24h
  flagged, bar containing R flagged, bar at R+4h flagged, bar at R+8h NOT
  flagged, bar at R-28h NOT flagged; last-grid-bar edge handled; no T
  at/after CUTOFF.
- test_bear_matches_v410_and_halving_exact: bear flags equal the v410
  formula; BASE = raw with longs x0.5 in bear (shorts/flat unchanged);
  RULE = BASE x0.5 exactly on RULEBAR rows, identical elsewhere.
- test_turnover_cost: total_cost == 0.0005 * total_turnover per variant
  (own-path prev, first prev 0); costs non-negative.
- test_year_partition_covers_grid: per-year n_bars sum to n_bars; no T
  at/after 2026-09-24 00:00 UTC.
- test_decision_matches_counts: dd-not-worse and retention counts
  recomputed from yearly rows equal the stored strings; promising flag
  matches the (>= 4/5, >= 4/5 with 98%) rule.

## Deliverables

`research/tournament/oc_fomcbook/`: PLAN.md (this file, written BEFORE
any outcome), `compute_fomcbook.py`, `panel.parquet`, `results.json`,
REPORT.md (tables + one-line verdict). `tests/test_oc_fomcbook.py`.
No tuning on results; any post-hoc change logged in REPORT.md.
No commits. LIGHT job: one process, 4h inputs only (no 1m), RAM < 1 GB.
