# oc_bookfunding PLAN (pre-registered BEFORE any outcome is computed)

Idea #56 (NEW): funding-crowding tilt for BOOK longs.

## Hypothesis (fixed here)

Book longs pay funding (gate: 0.01% per 8h; actual settled rates are higher
when crowded) and crowded longs precede squeezes / bleed. A coin whose
average settled funding over the previous 7 days is in the top quintile of
its own walk-forward history is a crowded long; scaling that coin's book
LONG target down (x0.75) should preserve total book P&L (within 3%) while
not worsening drawdown, because the tilt is off most of the time and only
trims the most crowded long exposure. Shorts are unchanged.

Rule (fixed, from the assignment): at each standard book row t, if the
coin's average settled funding rate over the previous 7 days (settlements
strictly before t) is above its walk-forward 80th percentile (fitted on
data before the anchor year), that coin's book LONG target is x0.75;
shorts unchanged.

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (mirror of `oc_bookic/compute_bookic.py::research_books_d2`):
  `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`, `d2 = 0.8*o1 + 0.2*(D+Dq)/2`,
  union index, missing -> 0.0, from `artifacts/research/engine_real/`
  (`member_A_O1_orders`, `member_Aq_O1_orders`, `member_B_tv`,
  `member_Bq_tv`, `members_v154[D]`, `members_quarterly_D`).
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens,
  the `eu.er.v154_books()` grid).
- Funding: `data/raw/binance_premium_20260928/*_funding.parquet`
  (`calc_time` = settlement time UTC, `last_funding_rate`; 8h grid).
  Premium 1m files are NOT used. No 1m klines of any kind.
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override
  of the old tournament-harness hidden-year cut; all five years are
  research data, findings still need prospective validation).
- No 1m data, one process, RAM < 1 GB (4h + funding settlements only).

## Exact causal definitions (fixed before seeing numbers)

- BOUND/CUTOFF = 2026-09-24 00:00 UTC. Grid = inner join of the rebuilt
  book index with the opens index (dropna all), sorted 4h, restricted to
  `T in [2021-09-24, CUTOFF)`; bars with any coin missing a forward open
  are dropped (same as oc_dvolshort/oc_bookcoinbrake: the last grid bar
  has no forward open and is dropped). `w[T,s]` is known at the close of
  bar `T` and is held over `[T, T+1)`. Forward exit `open[T+1]` must be
  at/before CUTOFF.
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years partition, no
  orphan bars: `Y_k = [A_k, A_{k+1})` for k = 0..3,
  `Y_4 = [A_4, A_4+365d)` (== `[A_4, CUTOFF)`; same bounds construction
  as oc_dvolshort: `bounds = ANCHORS + [A_4 + 365d]`).
- Returns: `R1[T,s]` = `open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- v410 bear filter FIRST (BASE = control, audited v410 rule, BTC-only,
  causal at close of T): on the FULL `opens_v154` BTCUSDT history compute
  `MA1200[T] = mean(open_BTC[T-1199..T])`, `rolling(1200, min_periods=600)`;
  `bear[T] = (open_BTC[T] < MA1200[T])` (strict; NaN -> False; `open[T]`
  inclusive, known at the close of T, exactly as v410/v410_bear_book.py
  and oc_bookcoinbrake). `w_base[T,s] = 0.5*w_raw[T,s]` if
  `bear[T] and w_raw[T,s] > 0`, else `w_raw[T,s]`. Shorts (`<0`), flats
  (`==0`) unchanged. The tilt below is judged against this BASE (the
  deployed book already carries this filter).
- Funding feature (strictly before T): per coin s, settlements are rows
  `(c, f)` with settlement time `c = calc_time`, rate `f`.
  `F7[T,s]` = mean of `f` over settlements with
  `T-7d <= c < T` (left-inclusive, right-exclusive; "settlements strictly
  before t", millisecond-exact comparison on actual timestamps, so a
  settlement stamped 08:00:00.001 is NOT usable at T = 08:00:00).
  Require >= 14 settlements in the window else `F7 = NaN` (7d at 8h cadence
  expects 21; the 14 floor keeps the tail usable after funding data ends
  2026-08-31 while failing safe; NaN rows are never tilted).
- Feature history / training pool (walk-forward, strictly previous data
  only): `FEAT_START = 2021-06-30` (same warm-up convention as the dvol
  studies; funding history starts 2020, so the window is full by then).
  `T_all` = sorted union of the pre-anchor 4h grid
  (`opens_v154` index restricted to `[FEAT_START, A_0)`) and the book grid.
  `F7` is computed for every `T in T_all` per coin with the same
  `[T-7d, T)` rule. For year k, `q80_k[s]` = 80th percentile of `F7[.,s]`
  over training rows `{T in T_all : FEAT_START <= T < A_k}` with finite
  `F7` (per-coin threshold; "its" percentile). Require >= 100 finite
  training values per (k, s) else that year's gate for that coin is
  undefined (reported as FAIL; not expected: year 0 has ~500 values/coin).
- Tilt gate (per-row, fixed): for each (T, sym) in year k,
  `tilt_on[T,s] = isfinite(F7[T,s]) and (F7[T,s] > q80_k[s])`;
  `w_rule[T,s] = 0.75 * w_base[T,s]` if `tilt_on[T,s] and w_base[T,s] > 0`,
  else `w_base[T,s]`. Longs only; shorts (`<0`), flats (`==0`), and
  NaN-`F7` rows are bit-identical to base. Long-leg membership for P&L
  attribution is fixed by `w_base > 0` so base vs rule compare the same
  rows.
- Costs (exactly as oc_dvolshort/oc_bookcoinbrake): maker 0.0002 per unit
  turnover. Per (T,s) in global grid order: `cost_base[T,s]` =
  `0.0002*|w_base[T,s]-w_base_prev[s]|` (first grid bar prev = 0.0);
  same formula on the rule path with `w_rule` and its OWN prev chain.
  Net cell: `pnl_base = w_base*R1 - cost_base`,
  `pnl_rule = w_rule*R1 - cost_rule`. No funding deduction, vol target,
  governor, sleeve, SL/TP, or compounding across bars in the per-cell
  sums; the equity path below compounds per-bar portfolio returns.
- Book path per variant: per-bar portfolio return `rp[T] = sum_s pnl[T,s]`
  over the 5 coins (`rp_rule` analogously). Per anchor year, equity reset
  to 1.0 at the year's first bar and compounded in grid order:
  `eq[i+1] = eq[i]*(1+rp[T_i])`. Full 5y path compounds the same way from
  the first bar of year 1 (context only). maxDD = peak-to-trough
  `max(1-eq_trough/running_peak)`. Worst week = minimum 42-bar (7-day)
  compounded return inside the year: `min_{i>=42}(eq[i]/eq[i-42]-1)`.
- Coverage / tilt-on share: share of (T, sym) rows with finite `F7` per
  year; tilt-on share = `mean(tilt_on)` over base-long rows
  (`w_base > 0`) per year (plus per-coin detail in results.json).

## Evaluation (fixed here)

- Per anchor year report: `q80_k` per coin (5 numbers), coverage, tilt-on
  share (overall on base longs + per coin); long-leg P&L base vs rule
  (net, summed over fixed `w_base > 0` rows); total book P&L base vs rule
  (net, all rows); worst week base vs rule; maxDD base vs rule (per-year
  reset paths). Full-path maxDD and total P&L base vs rule as context
  (not part of the rule).
- DECISION RULE (assignment-specific, replaces the default same-sign/LOYO
  rule): PROMISING only if (a) total book P&L >= 97% of base in >= 4/5
  years, AND (b) book maxDD not worse (`DD_rule <= DD_base`, tolerance
  1e-12 for float noise) in >= 4/5 years. For (a): if `pnl_base >= 0`
  then `pnl_rule >= 0.97*pnl_base`, else (losing base year)
  `pnl_rule >= pnl_base/0.97` (symmetric 3% magnitude tolerance, same
  convention as oc_bookcoinbrake's 5% rule). NaN on either side counts as
  FAIL. One-line verdict. LOYO is N/A by construction: thresholds are
  already strictly walk-forward per (year, coin) (no pooled in-year fit
  to leave out).
- Cost context: weights average << 1, so per-cell sums are in
  portfolio-return units; the per-year equity paths above are the scale
  that matters.

## Causality / alignment tests (tests/test_oc_bookfunding.py)

- test_books_match_dvolshort: rebuilt books equal oc_dvolshort's formula
  cell by cell on the common index (same files, same math).
- test_bear_causal: bear[T] recomputed from opens truncated to `<= T`
  is unchanged; NaN-MA rows never halved; shorts/flats bit-identical
  under the bear filter.
- test_funding_causal: sampled (T,s) `F7` recomputed from funding panels
  truncated to settlements with `c < T` are unchanged; `F7` uses no
  settlement with `c >= T`; windows with < 14 settlements are NaN and
  never tilted; longs tilted are exactly 0.75x base, shorts bit-identical.
- test_cutoffs_causal: year-k `q80` uses no row with `T >= A_k`
  (recomputed from the saved panel); NaN-`F7` rows are never tilted.
- test_grid_bounds: no `T` at/after CUTOFF; years partition the grid
  without gaps/overlaps.

## Deliverables

`research/tournament/oc_bookfunding/`: PLAN.md (this file),
`compute_bookfunding.py`, `panel.parquet` (per-(T,sym) base/rule
weights, tilt flags, F7, forwards, net cells; small),
`results.json`, `REPORT.md` (tables + one-line verdict). No tuning on
results; any post-hoc change logged in REPORT.md. No commits. LIGHT job:
one process, 4h + funding inputs only (no 1m), RAM < 1 GB.

## Post-hoc log

- (none yet; filled only if definitions change after outcomes are seen)
