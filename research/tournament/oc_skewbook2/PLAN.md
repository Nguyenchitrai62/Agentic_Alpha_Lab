# oc_skewbook2 PLAN (pre-registered BEFORE any outcome is computed)

Idea #59 (NEW): options skew as a BOOK long filter. `oc_optctx` tested Deribit
skew / put-flow for DIP fills (not promising); the book is untested.

## Hypothesis (fixed here)

Elevated downside-protection demand (high BTC put-minus-call OTM implied-vol
skew relative to its own 90-day history) marks fear states where the deployed
BOT book's LONG leg is adversely exposed (leans into the falling knife / fades
the bounce that follows hedging flows). Scaling book LONG targets down when the
skew z-score is in its walk-forward top quintile should therefore not hurt book
P&L materially while not worsening (ideally cutting) drawdown. Shorts are
untouched by this filter.

Rule (fixed, from the assignment): at each standard book row `T`, with
`z = skew_z90` exactly as `oc_optctx` defines it (strictly causal, see below),
if `z >` walk-forward 80th percentile of `z` (computed on data before the
anchor of the year only) then multiply every book LONG target of that bar by
0.75 (`w_g = 0.75 * w_base` for `w_base > 0`); shorts/flats/NaN-`z` unchanged.

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (also `oc_bookic/compute_bookic.py`): `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`,
  `d2 = 0.8*o1 + 0.2*(D+Dq)/2`, union index, missing -> 0.0, from
  `artifacts/research/engine_real/`.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens).
- Options: `data/raw/deribit_opt_20260926/BTC_options_4h.parquet` only
  (columns bar, call_buy, call_sell, put_buy, put_sell, n_trades,
  iv_otm_put, iv_otm_call). `bar` is the 4h bar START (fetch script floors
  trade timestamps to 4h), so the row aggregates trades in [bar, bar+4h).
  Only bars with START < 2026-09-24 00:00 UTC are used.
- Symbols: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (BTC skew is the
  market-fear proxy for all majors; no Deribit options for SOL/BNB/XRP).
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old tournament-harness hidden-year cut; all five years are research data,
  findings still need prospective validation).

## Exact causal definitions (fixed before seeing numbers)

- Grid: inner join of the book index with the opens index (dropna), sorted 4h
  grid; `T` in `[2021-09-24, 2026-09-24)` UTC; the last grid bar (no forward
  open) is dropped. `w[T,s]` is known at the close of bar `T` and held over
  `[T, T+1)`. Forward exit `open[T+1]` must be at/before
  `CUTOFF = 2026-09-24 00:00 UTC` (same boundary as oc_dvolshort/oc_dvolbook).
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years (partition, no orphan
  bars): `Y_k = [A_k, A_{k+1})` for k = 0..3, `Y_4 = [A_4, A_4 + 365d)`.
- v410 bear filter FIRST (base book, exactly as
  `research/parallel/rounds/parallel-20260906-r2/v410/v410_bear_book.py`
  lines 67-70): on the opens `BTCUSDT` series (full history, causal),
  `bear[T] = (btc[T] < mean(btc[T-1199..T]))` with a 1200-bar simple rolling
  mean (`min_periods=600`, includes the current bar, strictly known at the
  close of `T`). Base weights: `w_base[T,s] = 0.5 * w[T,s]` where `bear[T]`
  and `w[T,s] > 0`, else `w[T,s]`. Shorts/flats unchanged. The gated variant
  below starts from `w_base` (so the comparison isolates the skew filter on
  top of the bear-filtered book).
- Skew as-of (exactly as oc_optctx): an options 4h bar (start `b`, end
  `b+4h`) is usable at `T` iff its end is strictly before `T`
  (`b+4h < T`, implemented as `end <= T - 1s` via searchsorted side='left' on
  `T-1s`). `asof(T)` = the last usable bar's `skew = iv_otm_put-iv_otm_call`.
  For 4h-aligned `T` this is the bar `[T-8h, T-4h)` (4-8h staleness; slow
  feature, strictly causal, nothing at/after `T` is used).
- `skew_z90[T]` = (`v0 - mean(W)`) / `std(W, ddof=1)`; `v0` = asof skew at `T`;
  `W` = up to 540 prior bar-level skew values (90 days of 4h bars, current
  value excluded); require >= 432 non-NaN else NaN; `std == 0` -> NaN.
  Implemented as `skew.rolling(540, min_periods=432).mean/std(ddof=1).shift(1)`
  on the bar grid then as-of lookup (algebraically identical to the loop).
  `SKEW_START = 2019-06-01` (options start 2019-01-01; ~90d+ warm-up); the
  threshold pool below starts there so every anchor year is fully warmed up.
- Threshold (walk-forward, strictly previous data only): for year k,
  `q80_k` = 80th percentile of `skew_z90` over the training pool = per-`T`
  as-of `z` values with `T` on the 4h opens grid, `T` in
  `[SKEW_START, A_k)`, `z` non-NaN (single market-wide series; pooling per
  `(T,sym)` would replicate the same value 5x with an identical quantile, so
  the per-`T` pool is used). Require >= 100 training values else the year's
  gate is undefined (reported as FAIL; not expected: year 1 has ~4.8k values
  back to 2019-06-01).
- Gate (per-row, fixed): for each (T, sym) in year k,
  `gated = (w_base[T,s] > 0) and isfinite(z[T]) and (z[T] > q80_k)`;
  `w_g[T,s] = 0.75 * w_base[T,s]` if gated else `w_base[T,s]`. Shorts
  (`w_base < 0`, bear-filtered shorts equal raw shorts), flats (`== 0`), and
  NaN-`z` rows are unchanged.
- Returns: `R1[T,s]` = `open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- Costs (gate model, exactly as oc_dvolshort): maker 0.0002 per unit turnover.
  Per (T, s) in grid order: `cost = 0.0002 * |w_base - w_base_prev|`,
  `cost_g = 0.0002 * |w_g - w_g_prev|` with per-sym previous-grid-bar weight
  (first grid bar: prev = 0; gated path uses its own gated prev). Net cell:
  `pnl = w_base * R1 - cost`, `pnl_g = w_g * R1 - cost_g`. No funding, vol
  target, governor, sleeve, SL/TP, or compounding across bars in the per-cell
  sums; the equity path below compounds per-bar portfolio returns.
- Book path per variant: per-bar portfolio return `rp[T] = sum_s pnl[T,s]`
  over the 5 coins (base) and `rp_g[T]` (gated). Per anchor year, equity is
  reset to 1.0 at the year's first bar and compounded in grid order:
  `eq[i+1] = eq[i] * (1 + rp[T_i])`. Full 5y path compounds the same way from
  the first bar of year 1 (context only). maxDD of a path =
  `max_{peak<trough} (1 - eq_trough / eq_peak)` (peak running maximum strictly
  before the trough). Worst week = minimum 42-bar (7-day) compounded return
  inside the year: `min_{i>=42} (eq[i]/eq[i-42] - 1)`.
- Coverage: share of (T, sym) rows with non-NaN `z`; filter-on share = share
  of base-long rows gated per year (plus share of all rows, reported).

## Evaluation (fixed here)

- Per anchor year report: `q80_k`, coverage, filter-on share (longs + all);
  total book P&L base vs gated (net, all rows, portfolio-return units);
  worst week base vs gated; maxDD base vs gated (per-year reset paths).
  Full-path maxDD/P&L base vs gated as context (not part of the rule).
- DECISION RULE (from the assignment, replaces the default tournament rule):
  PROMISING only if (a) book P&L gated >= 97% of base in >= 4/5 years, AND
  (b) maxDD not worse (gated DD <= base DD) in >= 4/5 years. Otherwise NOT
  PROMISING. One-line verdict. The default sign-consistency / LOYO rule is N/A
  here by construction: thresholds are already strictly walk-forward (no
  cross-year pooling), so there is no in-year fit to leave out; the 97%-P&L +
  no-worse-DD bar is the test.
- Cost context: weights average << 1, so per-cell bps overstate portfolio
  impact; the portfolio sums and equity paths above are the scale that matters.

## Causality / alignment tests (tests/test_oc_skewbook2.py)

- test_asof_strictly_before_T: sampled (T) `z` values recomputed from options
  panels truncated to bars with end < T are unchanged; no used bar has
  end >= T; `bar` lies on the 4h grid.
- test_cutoffs_causal: year-k `q80` uses no `T >= A_k` (recomputed from the
  saved panel + grid); NaN-`z` rows are never gated; gated longs are exactly
  0.75x base and shorts/flats are bit-identical.
- test_books_match_dvolshort: rebuilt raw books equal
  oc_dvolshort's `research_books_d2` cell by cell on the common index; bear
  mask equals `btc < rolling(1200, min_periods=600).mean()` on opens.
- test_grid_bounds: no `T` at/after 2026-09-24 00:00 UTC; no options bar with
  START >= CUTOFF is used; anchors partition the grid without gaps/overlaps.

## Deliverables

`research/tournament/oc_skewbook2/`: PLAN.md (this file),
`compute_skewbook2.py`, `panel.parquet` (per-(T,sym) base/gated weights, `z`,
forwards, net cells; small), `results.json`, `REPORT.md` (tables + one-line
verdict). No tuning on results; any post-hoc change logged in REPORT.md. No
commits. LIGHT job: one process, 4h + options-4h inputs only (no 1m),
RAM < 1 GB.
