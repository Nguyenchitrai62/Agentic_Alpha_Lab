# oc_bookweekend PLAN (pre-registered BEFORE any outcome is computed)

Idea #50 (NEW): book flat on weekends.

## Hypothesis (fixed here)

Weekend holding bars (Saturday 00:00 UTC through Sunday close) contribute
negatively to the BOT book's net P&L and disproportionately to its path
drawdown: crypto trades 24/7 but weekend liquidity is thinner, Monday
reopens gap against stale weekend positions, and a slow 4h momentum book
held over 48h of low-signal drift pays turnover without edge. Forcing book
targets to 0 on weekend holding bars (close at the Saturday 00:00 bar open,
reopen from Monday 00:00 per the normal targets) should therefore keep or
raise net book P&L while not worsening maxDD.

Rule (fixed, from the assignment): book targets of holding bars that start
between Sat 00:00 and Mon 00:00 UTC are 0 (positions closed at the Saturday
00:00 bar open, reopened from Monday 00:00 per the normal targets).

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (= `oc_bookic` formula: `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`,
  `d2 = 0.8*o1 + 0.2*(D+Dq)/2`, union index, missing -> 0.0) from
  `artifacts/research/engine_real/` member caches.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens).
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override;
  all five years are research data; any finding needs prospective
  validation).
- LIGHT job: one process, 4h opens + book parquets only (no 1m data),
  RAM < 1 GB.

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
  [2026-09-24]` (same as oc_longcap; the 2023 year holds the leap-day
  bars).
- Bear filter FIRST (audited v410, mirrors oc_longcap/oc_bullshort BASE
  exactly): on the FULL BTC opens history,
  `MA1200[T] = mean(BTC_open[T-1199..T])` via
  `rolling(1200, min_periods=600).mean()`;
  `bear[T] iff BTC_open[T] < MA1200[T]` (strict; equality or NaN-MA ->
  not bear, weight unchanged). Flag at `T` uses `open[T]` inclusive, i.e.
  known at the close of bar `T`.
  `BASE[T,s] = 0.5 * w[T,s] where bear[T] and w[T,s] > 0, else w[T,s]`
  (longs halved in bear; shorts/flat unchanged). BASE is the control path.
- Weekend mask (fixed calendar, no fitting): `weekend[T] iff T.weekday() in
  {5, 6}` (Saturday = 5, Sunday = 6; UTC). On the 4h grid aligned at
  00/04/08/12/16/20 UTC this is exactly the holding bars with
  `Sat 00:00 <= T < Mon 00:00` (12 bars per full weekend). Monday 00:00
  (`weekday == 0`) is NOT weekend (reopen per normal targets); Friday
  20:00 (`weekday == 4`) is NOT weekend. The mask uses only the bar
  timestamp, hence only information known at the close of `T`.
- Rule: `RULE[T,s] = 0.0 where weekend[T], else BASE[T,s]` (all coins,
  longs and shorts alike; sign never flips except to flat).
- Returns: `R1[T,s] = open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- Costs (assignment: 0.05% per unit turnover): maker `0.0005` per unit
  turnover. Per (T, s) in grid order:
  `cost[T,s] = 0.0005 * |w[T,s] - w_prev[s]|` with `w_prev` = the previous
  grid bar's weight for the same sym (first grid bar: prev = 0). Same
  formula applied to each path with its OWN prev (BASE prev for BASE,
  RULE prev for RULE), so the Saturday-00:00 close and Monday-00:00
  reopen turnover is charged to the RULE path. Net cell:
  `pnl = w * R1 - cost` per path.
- Book path per variant: per-bar portfolio return `rp[T] = sum_s pnl[T,s]`
  over the 5 coins. Per anchor year, equity is reset to 1.0 at the year's
  first bar and compounded in grid order: `eq[i+1] = eq[i] * (1 + rp[T_i])`
  (exactly as oc_dvolshort). Full 5y path compounds the same way from the
  first bar of year 1 (context only). maxDD of a path =
  `max_{peak<trough} (1 - eq_trough / eq_peak)`. Worst week = minimum
  42-bar (7-day) compounded return inside the year:
  `min_{i>=42} (eq[i]/eq[i-42] - 1)`.
- Book P&L per year (primary): linear net sum `sum(pnl)` over all year
  rows (same scale as oc_dvolshort's `total_pnl`), BASE vs RULE.
  Weekend/weekday split of the BASE (descriptive): linear net sums over
  year rows with `weekend[T]` True/False using the BASE per-cell pnl
  (cost of bar T is attributed to bar T, so the Saturday-00:00 close cost
  sits in the weekend leg and the Monday-00:00 reopen cost sits in the
  weekday leg; documented, not re-allocated).
- Coverage: share of grid bars with `weekend[T]` True per year (expect
  12/42 ~= 2/7 of bars up to grid alignment).

## Evaluation (fixed here — one variant only)

- Per anchor year report: n_bars, weekend share; BASE book P&L net with
  weekend-leg / weekday-leg split; costs BASE vs RULE (totals); book P&L
  net BASE vs RULE; worst week BASE vs RULE; book maxDD BASE vs RULE
  (per-year reset paths). Plus full-5y path maxDD/total (context).
- DECISION RULE (assignment-specific, governs the verdict): PROMISING only
  if (a) net book P&L RULE >= BASE (tolerance 0) in >= 4/5 years AND
  (b) book maxDD not worse (RULE <= BASE, tolerance 0) in >= 4/5 years.
  NaN on either side counts as FAIL. One-line verdict.
- LOYO stability (descriptive side row, NOT part of the verdict — there is
  no fitted parameter to leave out; the weekend mask is a fixed calendar
  constant): for the P&L-not-lower indicator and the DD-not-worse
  indicator, held-out year h passes iff the held-out indicator equals the
  majority indicator of the other four years. Reported as `loyo_pnl`,
  `loyo_dd = n/5`.
- Cost context: weights average << 1, so per-cell bps overstate portfolio
  impact; the portfolio sums and equity paths above are the scale that
  matters. Vectorised open-to-open screen only (no vol target, governor,
  dip sleeve sizing, funding, SL/TP, or engine limit path).

## Causality / alignment tests (tests/test_oc_bookweekend.py)

- test_results_exists_and_schema: results.json has meta/years/full_path/
  loyo/decision with the pre-registered fields.
- test_weekend_math: RULE weights are exactly 0 on weekend bars and
  bit-identical to BASE on weekday bars (all coins); weekend mask ==
  (T.weekday >= 5) and matches [Sat 00:00, Mon 00:00) bounds; sampled
  weekends have 12 flat bars; Monday-00:00 bars are not flat-by-rule.
- test_bear_matches_v410: bear flags match the v410 formula
  (`BTC open < rolling(1200,min600) mean`, NaN -> False) on sampled real
  rows; BASE == raw book with longs x0.5 in bear (synthetic + sampled).
- test_turnover_cost: per-sym `cost == 0.0005 * |w - w_prev|` (own prev,
  first prev = 0) for both paths; costs non-negative.
- test_year_partition_covers_grid: per-year n_bars sum to n_bars; no T
  at/after 2026-09-24 00:00 UTC; weekend/weekday legs sum to the BASE
  total each year.
- test_decision_matches_counts: pnl-not-lower and dd-not-worse counts
  recomputed from yearly rows equal the stored strings; promising flag
  matches the (4/5, 4/5) rule.

## Deliverables

`research/tournament/oc_bookweekend/`: PLAN.md (this file, written BEFORE
any outcome), `compute_bookweekend.py`, `panel.parquet`, `results.json`,
REPORT.md (tables + one-line verdict). `tests/test_oc_bookweekend.py`. No
tuning on results; any post-hoc change logged in REPORT.md. No commits.
LIGHT job: one process, 4h inputs only (no 1m), RAM < 1 GB.
