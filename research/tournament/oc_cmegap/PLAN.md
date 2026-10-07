# oc_cmegap PLAN (pre-registered BEFORE any outcome is computed)

Idea #69 (NEW): CME weekend-gap fill as a BOOK tilt, no new data.

## Hypothesis (fixed here)

CME BTC futures stop over the weekend while Binance trades 24/7, so the
Friday-close -> Sunday-reopen move (the "CME gap") is public weekend news.
Textbook price action says gaps fill: after a large up-gap the market is
extended and fades back toward the Friday close (longs should be trimmed),
after a large down-gap the washout snaps back (longs should be added).
A slow 4h momentum book that ignores this should therefore benefit from a
fixed gap-conditional long tilt applied only while the gap is still open:
up-gap > +2% -> longs x0.75; down-gap < -2% -> longs x1.25; small gaps
unchanged; shorts never touched. The tilt expires when the gap fills on
1m trade-throughs or 72 h after the reopen, whichever comes first.

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (= oc_bookic formula: `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`,
  `d2 = 0.8*o1 + 0.2*(D+Dq)/2`, union index, missing -> 0.0) from
  `artifacts/research/engine_real/` member caches.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens).
- Gap/fill prices: Binance BTCUSDT 1m klines
  `data/raw/btc_intraday_20260924/klines_1m_YYYY.parquet`
  (`open_time` = bar START UTC, `close`/`high`/`low`); only columns
  open_time/high/low/close are read, only rows with
  `open_time < CUTOFF` are used.
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override;
  all five years are research data; any finding needs prospective
  validation).
- LIGHT job: one process, 4h opens + book parquets + BTC 1m only,
  RAM < 1 GB.

## Exact causal definitions (fixed now, before seeing numbers)

- Grid: inner join of the book index with the opens index (dropna all),
  sorted 4h grid; `T` in `[2021-09-24, 2026-09-24)` UTC; the last grid bar
  (no forward open) is dropped and every kept bar must have all 5 forward
  opens non-NaN with the forward open at/before
  `CUTOFF = 2026-09-24 00:00 UTC` (same boundary as oc_dvolshort /
  oc_bookweekend). Weight `w[T,s]` is known at the close of bar `T` and
  is held over `[T, T+1)`.
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years partition the grid
  with no gaps/overlaps: `Y_k = [B_k, B_{k+1})`, `B = ANCHORS +
  [2026-09-24]` (the 2023 year holds the leap-day bars).
- DST rule (fixed here; stated as required): US daylight saving runs from
  the second Sunday of March to the first Sunday of November (each year).
  A weekend's season is fixed by its Friday (close day): if that Friday's
  calendar date is in `[2nd-Sun-Mar, 1st-Sun-Nov)` it uses summer times,
  else winter times. Times (UTC):
  winter: Friday CLOSE 21:00, Sunday REOPEN 22:00;
  summer (US DST): Friday CLOSE 20:00, Sunday REOPEN 21:00.
  (Summer is 1 h earlier in UTC because US clocks spring forward; the main
  clause's 21:00/22:00 pair is the winter case.) A weekend is the Friday
  with calendar date F and the immediately following Sunday; close minute
  = F 21:00 (winter) or 20:00 (summer) UTC, reopen minute = (F+2 days)
  21:00 (summer) or 22:00 (winter) UTC, as 1m bar START times.
- Gap (strictly causal proxy, no CME data): `P_fri` = close of the 1m bar
  with `open_time == close minute`; `P_sun` = close of the 1m bar with
  `open_time == reopen minute`; `gap = P_sun / P_fri - 1`. The gap is
  known at the close of the reopen 1m bar (reopen + 1 min). If either 1m
  bar is missing, the gap is NaN and that weekend has no window (weights
  unchanged; counted as missing).
- Fill (strictly before T): for a weekend with finite non-zero gap, the
  fill minute is the first 1m bar with `open_time > reopen` and
  `open_time < reopen + 72h` such that for `gap > 0` its `low <= P_fri`,
  for `gap < 0` its `high >= P_fri` (1m trade-through of the Friday
  close; the reopen bar itself is excluded). For `gap == 0` no fill scan
  is needed (no tilt either way). A row T may only use 1m bars with
  `open_time < T` (fill known strictly before T).
- Active window: standard book rows `T` with `T > reopen` (strictly after
  the reopen minute, so the first candidate is the next 4h grid bar; the
  gap is already known), `T <= reopen + 72h`, and no fill minute with
  `open_time < T`. At most one weekend is active per T (72 h < 7 days).
  Weekends whose reopen is at/after CUTOFF have no grid rows and are
  ignored. Small-gap (`|gap| <= 2%`) windows are defined the same way but
  apply no scaling (weights identical either way, so their fill scan is
  an implementation no-op reported as unchanged).
- Bear filter FIRST (audited v410, mirrors oc_bookweekend BASE exactly):
  on the FULL BTC opens history,
  `MA1200[T] = mean(BTC_open[T-1199..T])` via
  `rolling(1200, min_periods=600).mean()`;
  `bear[T] iff BTC_open[T] < MA1200[T]` (strict; equality or NaN-MA ->
  not bear). Flag at `T` uses `open[T]` inclusive, known at the close of
  `T`. `BASE[T,s] = 0.5 * w[T,s] where bear[T] and w[T,s] > 0, else
  w[T,s]` (longs halved in bear; shorts/flat unchanged). BASE is the
  control path.
- Rule (fixed): on an active large-gap row T with gap `g`:
  if `g > +0.02` and `BASE[T,s] > 0` then `RULE[T,s] = 0.75 * BASE[T,s]`
  (all 5 coins); if `g < -0.02` and `BASE[T,s] > 0` then
  `RULE[T,s] = 1.25 * BASE[T,s]`; else `RULE[T,s] = BASE[T,s]`.
  Shorts (`BASE <= 0`), flats, NaN-gap weekends, small-gap windows and
  rows outside any window are bit-identical to BASE. The tilt multiplies
  the bear-filtered long (bear first, then gap tilt).
- Returns: `R1[T,s] = open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- Costs (assignment: 0.05% per unit turnover): `0.0005` per unit turnover.
  Per (T, s) in grid order: `cost = 0.0005 * |w - w_prev|` with `w_prev`
  = the previous grid bar's weight for the same sym (first grid bar:
  prev = 0). Same formula per path with its OWN prev (BASE prev for
  BASE, RULE prev for RULE). Net cell: `pnl = w * R1 - cost` per path.
- Book path per variant: per-bar portfolio return `rp[T] = sum_s pnl[T,s]`
  over the 5 coins. Per anchor year, equity reset to 1.0 at the year's
  first bar and compounded in grid order: `eq[i+1] = eq[i] * (1+rp[T_i])`
  (exactly as oc_dvolshort / oc_bookweekend). Full 5y path compounds the
  same way from the first bar of year 1 (context only). maxDD =
  peak-to-trough on that path. Worst week = minimum 42-bar (7-day)
  compounded return inside the year: `min_{i>=42} (eq[i]/eq[i-42]-1)`.
- Book P&L per year (primary): linear net sum `sum(pnl)` over year rows,
  BASE vs RULE; affected-rows split: linear net sums over (T,sym) rows
  with T in a LARGE-gap active window (all 5 syms; membership by T only,
  fixed identically for both paths) using each path's own per-cell pnl.
- Coverage: weekends enumerated, weekends with finite gap, weekends with
  `|gap| > 2%` (large), share of large gaps filled within 72 h
  (fill minute exists and `<= reopen+72h`), share of grid bars affected
  (T in a large-gap active window) per year.

## Evaluation (fixed here - one variant only)

- Per anchor year report: n_weekends, n_gap (finite), n_large (`|gap|>2%`),
  fill rate of large gaps within 72 h; affected bars / affected share;
  affected-rows book P&L net BASE vs RULE; TOTAL book P&L net BASE vs
  RULE; worst week BASE vs RULE; book maxDD BASE vs RULE (per-year reset
  paths). Plus full-5y path maxDD/total (context only).
- DECISION RULE (assignment-specific, governs the verdict): PROMISING only
  if (a) TOTAL net book P&L RULE >= BASE (tolerance 0) in >= 4/5 years
  AND (b) book maxDD not worse (RULE <= BASE, tolerance 0) in >= 4/5
  years. NaN on either side counts as FAIL. One-line verdict.
- LOYO stability (descriptive side row, NOT part of the verdict - there is
  no fitted parameter to leave out; gaps/thresholds/fills are fixed
  calendar/price constants): for the P&L indicator and the DD indicator,
  held-out year h passes iff the held-out indicator equals the majority
  indicator of the other four years. Reported as `loyo_pnl`,
  `loyo_dd = n/5`.
- Cost context: weights average << 1, so per-cell bps overstate portfolio
  impact; the portfolio sums and equity paths above are the scale that
  matters. Vectorised open-to-open screen only (no vol target, governor,
  dip sleeve, funding, SL/TP, or engine limit path).

## Causality / alignment tests (tests/test_oc_cmegap.py)

- test_results_exists_and_schema: results.json has meta/years/full_path/
  loyo/decision with the pre-registered fields.
- test_gap_causality_and_dst: sampled weekend gaps recomputed from 1m
  panels truncated to bars with open_time <= reopen are unchanged; close/
  reopen minutes match the winter/summer rule for sampled winter and
  summer weekends; DST Sundays (2nd-Sun-Mar / 1st-Sun-Nov) boundaries hold.
- test_fill_strictly_before_T_and_first_row: no affected T is <= its
  reopen; fill minute (if any) is < first unaffected T and > reopen; rows
  after fill or after reopen+72h are not affected; the 4h bar containing
  the reopen (when grid-misaligned) is never affected.
- test_rule_math: RULE shorts/flats bit-identical to BASE everywhere;
  RULE longs == BASE on non-affected rows; on affected rows longs are
  exactly x0.75 (up-gap) or x1.25 (down-gap); small-gap windows leave all
  weights identical.
- test_bear_matches_v410: bear flags match the v410 formula on sampled
  real rows; BASE == raw book with longs x0.5 in bear.
- test_turnover_cost: per-sym `cost == 0.0005 * |w - w_prev|` (own prev,
  first prev = 0) for both paths; costs non-negative.
- test_year_partition_covers_grid: per-year n_bars sum to n_bars; no T
  at/after CUTOFF; affected + unaffected rows sum to the panel each year.
- test_decision_matches_counts: total-P&L and DD counts recomputed from
  yearly rows equal the stored strings; promising flag matches the
  (4/5, 4/5) rule.

## Deliverables

`research/tournament/oc_cmegap/`: PLAN.md (this file, written BEFORE any
outcome), `compute_cmegap.py`, `panel.parquet`, `gaps.parquet`,
`results.json`, REPORT.md (tables + one-line verdict).
`tests/test_oc_cmegap.py`. No tuning on results; any post-hoc change
logged in REPORT.md. No commits. LIGHT job: one process, 4h + BTC 1m
inputs only (1m use stated in the assignment), RAM < 1 GB.
