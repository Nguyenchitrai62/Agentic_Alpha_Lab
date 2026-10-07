# oc_bookevent PLAN (pre-registered BEFORE any outcome is computed)

Idea #51 (NEW): book exposure around scheduled US macro events.

## Hypothesis (fixed here)

Scheduled FOMC-statement / US CPI releases inject information-driven
volatility into the 4h holding window; a slow momentum book held across
the release bar (or entered the bar before, hence held across the
release) takes event risk it is not paid for. Halving ALL book targets
on the 4h holding bar that contains a scheduled release instant and on
the bar before it should therefore leave the book path's max drawdown
not worse at a small yearly-P&L cost, because event bars are a small
minority of bars. Sign/universality is read from the data; consistency
across anchor years is what matters (rule below). ONE scored rule only.

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (= `oc_bookic` formula: `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`,
  `d2 = 0.8*o1 + 0.2*(D+Dq)/2`, union index, missing -> 0.0) from
  `artifacts/research/engine_real/` member caches.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens,
  history from 2017 so every scored year has a full 1200-bar bear window).
- Calendar: `research/tournament/oc_eventblk/event_calendar.csv`
  (FOMC statements 14:00 ET + CPI releases 08:30 ET, UTC instants; built
  by oc_eventblk from official Fed/BLS pages; all release dates are
  scheduled far in advance, hence known before each anchor year). No
  copy: read in place, never edited.
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override;
  all five years are research data; any finding needs prospective
  validation).
- LIGHT job: one process, 4h opens + book parquets + calendar only
  (no 1m data), RAM < 1 GB.

## Exact causal definitions (fixed now, before seeing numbers)

- Grid: inner join of the book index with the opens index (dropna all),
  sorted 4h grid; `T` in `[2021-09-24, 2026-09-24)` UTC; the last grid bar
  (no forward open) is dropped and every kept bar must have all 5 forward
  opens non-NaN with the forward open at/before
  `CUTOFF = 2026-09-24 00:00 UTC` (same boundary as oc_dvolshort).
  Weight `w[T,s]` is known at the close of bar `T` and is held over
  `[T, T+1)`.
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years partition the grid
  with no gaps/overlaps: `Y_k = [B_k, B_{k+1})`, `B = ANCHORS +
  [2026-09-24]`.
- Bear filter FIRST (audited v410, mirrors oc_bullbook/oc_bookcoinbrake
  BASE exactly): on the FULL BTC opens history,
  `MA1200[T] = mean(BTC_open[T-1199..T])` via
  `rolling(1200, min_periods=600).mean()`; `bear[T] iff BTC_open[T] <
  MA1200[T]` (strict; equality or NaN-MA -> not bear). Flag at `T` uses
  `open[T]` inclusive, i.e. known at the close of bar `T`.
  `BASE[T,s] = 0.5 * w[T,s] where bear[T] and w[T,s] > 0, else w[T,s]`
  (longs halved in bear; shorts/flat unchanged). BASE is the control path.
- Event flags (calendar + T only, hence causal at bid time T because the
  schedule is pre-published; mirrors oc_eventblk's instant-in-bar
  predicate):
  `EVENTBAR(T) = 1 iff [T, T+4h)` CONTAINS a release instant R
  (`T <= R < T+4h`, FOMC or CPI pooled).
  `RULEBAR(T) = EVENTBAR(T) OR EVENTBAR(T+4h)` (the containing bar AND the
  bar before it; the bar before still holds its position across the
  release). The `T+4h` lookup uses only the grid time plus the fixed
  calendar, no market data after T. If `T+4h` is not a grid bar (year/grid
  edge), only `EVENTBAR(T)` applies.
- Rule (fixed, from the assignment): `RULE[T,s] = 0.5 * BASE[T,s]` where
  `RULEBAR(T)`, else `BASE[T,s]` (all five coins; longs, shorts and flats
  alike; flats stay flat). No fitted parameter, no threshold to learn.
- Returns: `R1[T,s] = open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- Costs (exactly as oc_dvolshort): maker 0.0002 per unit turnover. Per
  (T, s) in grid order: `cost[T,s] = 0.0002 * |w[T,s] - w_prev[s]|` with
  `w_prev` = the previous grid bar's weight for the same sym (first grid
  bar: prev = 0). Same formula applied to each path with its OWN prev
  (BASE prev for BASE, RULE prev for RULE). Net cell:
  `pnl = w * R1 - cost` per path.
- Book path per variant: per-bar portfolio return `rp[T] = sum_s pnl[T,s]`
  over the 5 coins. Per anchor year, equity is reset to 1.0 at the year's
  first bar and compounded in grid order: `eq[i+1] = eq[i] * (1 + rp[T_i])`
  (exactly as oc_dvolshort). Full 5y path compounds the same way from the
  first bar of year 1 (context only). maxDD of a path =
  `max_{peak<trough} (1 - eq_trough / eq_peak)`. Worst week = minimum
  42-bar (7-day) compounded return inside the year:
  `min_{i>=42} (eq[i]/eq[i-42] - 1)`.
- Book P&L per year (primary): linear net sums `sum(pnl)` over all year
  rows (same scale as oc_dvolshort's `total_pnl`), BASE vs RULE. Event-bar
  attribution: linear net sums over RULEBAR rows only, BASE vs RULE
  (fixed rulebar membership, both paths compared on identical rows).
  Coverage: share of grid bars with RULEBAR=1 per year (plus EVENTBAR=1
  share for reference).

## Evaluation (fixed here — one variant only)

- Per anchor year report: n_bars, RULEBAR/EVENTBAR share; event-bar
  (RULEBAR rows) book P&L BASE vs RULE (net linear sums); TOTAL book P&L
  BASE vs RULE (net linear sums); worst week BASE vs RULE; book maxDD
  BASE vs RULE (per-year reset paths). Full-5y path maxDD/total (context).
- DECISION RULE (assignment-specific, replaces the default for the
  verdict): PROMISING only if (a) book maxDD not worse
  (RULE maxDD strictly <= BASE maxDD, tolerance 1e-12) in >= 4/5 years
  AND (b) total book P&L retains >= 97% of BASE
  (RULE >= 0.97 * BASE, tolerance 0; if BASE <= 0 in a year that year
  counts as FAIL for leg (b); NaN on either side counts as FAIL) in
  >= 4/5 years. One-line verdict.
- LOYO stability (descriptive side row, NOT part of the verdict — there
  is no fitted parameter to leave out; the calendar and multipliers are
  fixed constants, oc_dvolshort precedent): for the DD-not-worse
  indicator and the retention indicator, held-out year h passes iff the
  held-out indicator equals the majority indicator of the other four
  years. Reported as `loyo_dd`, `loyo_ret = n/5`.
- Cost context: weights average << 1; the portfolio sums and equity paths
  above are the scale that matters. Vectorised open-to-open screen only
  (no vol target, governor, dip sleeve, funding, SL/TP, or engine limit
  path).

## Causality / alignment tests (tests/test_oc_bookevent.py)

- test_results_exists_and_schema: results.json has meta/years/full_path/
  loyo/decision with the pre-registered fields; panel has 5 rows per bar.
- test_rulebar_causal_calendar_only: RULEBAR recomputed from grid times +
  calendar only (market/book columns droppable without change); hand
  checks: bar containing R flagged, bar before flagged, bar starting at/after
  R+0 not flagged via the before-leg unless it contains another event;
  last-grid-bar edge (no T+4h lookup) handled.
- test_bear_matches_v410_and_halving_exact: bear flags equal the v410
  formula; BASE = raw with longs x0.5 in bear (shorts/flat unchanged);
  RULE = BASE x0.5 exactly on RULEBAR rows, identical elsewhere.
- test_turnover_cost: total_cost == 0.0002 * total_turnover per variant
  (own-path prev, first prev 0); costs non-negative.
- test_year_partition_covers_grid: per-year n_bars sum to n_bars; no T
  at/after 2026-09-24 00:00 UTC.
- test_decision_matches_counts: dd-not-worse and retention counts
  recomputed from yearly rows equal the stored strings; promising flag
  matches the (>= 4/5, >= 4/5 with 97%) rule.

## Deliverables

`research/tournament/oc_bookevent/`: PLAN.md (this file, written BEFORE
any outcome), `compute_bookevent.py`, `panel.parquet`, `results.json`,
REPORT.md (tables + one-line verdict). `tests/test_oc_bookevent.py`.
No tuning on results; any post-hoc change logged in REPORT.md.
No commits. LIGHT job: one process, 4h + calendar inputs only (no 1m),
RAM < 1 GB.
