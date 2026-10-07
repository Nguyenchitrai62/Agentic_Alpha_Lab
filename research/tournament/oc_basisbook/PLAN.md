# oc_basisbook PLAN (pre-registered BEFORE any outcome is computed)

Idea #61 (NEW): quarterly-basis MOMENTUM gate on BOOK LONGS.

## Hypothesis (fixed here)

`oc_qbasis` tested the basis LEVEL and found it wrong-way for book longs
(high basis -> BETTER long P&L, 5/5 sign); `oc_idea6` tested basis momentum
for dips (24h change throttle, closed). The remaining book question is the
CHANGE over a slower de-leveraging window: a fast 7-day collapse of the BTC
front-quarterly annualised basis = de-leveraging impulse; book longs held
through it face follow-through while shorts are unaffected. Scaling book
LONG targets down (x0.5) exactly on impulse bars should therefore cut book
drawdown at negligible P&L cost (a throttle, screened DD-first).

Rule (fixed, from the assignment): at holding bar start `T`, with
`mom(T) = basis(T) - basis(T - 7 days)` (BTC front-quarterly annualised
basis, strictly causal, see below), if `mom(T) <` walk-forward 20th
percentile of `mom` (computed on data before the anchor of the year only),
multiply every book LONG target of that bar by 0.5 (shorts unchanged,
flats unchanged, NaN-`mom` rows unchanged).

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (mirror of `oc_bookic/compute_bookic.py::research_books_d2`):
  `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`, `d2 = 0.8*o1 + 0.2*(D+Dq)/2`,
  union index, missing -> 0.0, from `artifacts/research/engine_real/`
  (`member_A_O1_orders`, `member_Aq_O1_orders`, `member_B_tv`,
  `member_Bq_tv`, `members_v154[D]`, `members_quarterly_D`).
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens).
- Basis: `artifacts/research/engine_real/qbasis_features_4h.parquet`
  (built causally from `data/raw/qbasis_20261003` by
  `scripts/fetch_quarterly_basis.py`; per coin per 4h bar: open_time,
  close_time, sym, qb_front = annualised front-delivery basis
  ln(F/perp)*365/DTE, qb_slope, qb_chg24, source). The 4h value is the
  hourly delivery close at the 4h close, so selecting rows with
  `close_time < T` is exactly "delivery 4h closes strictly < t" from the
  assignment. Raw delivery 1h files are NOT re-loaded (same object, LIGHT).
  BTC leg only (market-wide signal, as in oc_idea6).
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides
  the old RULES.md hidden-year cut; all five years are research data,
  findings still need prospective validation).
- No 1m data, one process, RAM < 1 GB (three small 4h frames only).

## Exact causal definitions (fixed before seeing numbers)

- BOUND/CUTOFF = 2026-09-24 00:00 UTC. Grid = inner join of the rebuilt
  book index with the opens index (dropna all), sorted 4h, restricted to
  `T in [2021-09-24, CUTOFF)`; bars with any coin missing a forward open
  are dropped (same as oc_dvolshort/oc_bearshort: the last grid bar has no
  forward open and is dropped). `w[T,s]` is known at the close of bar `T`
  and is held over `[T, T+1)`. Forward exit `open[T+1]` must be at/before
  CUTOFF.
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years partition, no
  orphan bars: `Y_k = [A_k, A_{k+1})` for k = 0..3,
  `Y_4 = [A_4, A_4+365d)` (== `[A_4, CUTOFF)`; same bounds construction
  as oc_dvolshort/oc_bearshort: `bounds = ANCHORS + [A_4 + 365d]`).
- Returns: `R1[T,s]` = `open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- Basis as-of (exactly the oc_qbasis strict rule, both legs):
  `basis(T)` = `qb_front` (BTCUSDT) at max `close_time < T` (STRICTLY
  before T; the 4h bar ending exactly at T is never used). NaN if no such
  row or its `qb_front` is NaN. `mom(T) = basis(T) - basis(T - 7d)`,
  where `basis(T-7d)` is the same strict rule evaluated at `S = T - 7 days`
  (max `close_time < S`). NaN if either leg is NaN/missing. No
  interpolation, no fill-forward, no roll adjustment (a window spanning a
  front roll keeps the raw annualised difference; rolls are quarterly and
  disclosed via the source column only). One signal per bar, applied to
  all 5 coins (market-wide).
- BTC qb valid from 2020-06-11 (oc_qbasis), so `mom` is valid from
  ~2020-06-18; covers all anchor years. No imputation.
- Walk-forward threshold (strictly previous data only): for year k,
  `p20_k` = 20th percentile of `mom(T)` over the training pool = 4h bar
  times `T` on the engine 4h grid (`opens_v154` index) with
  `T in [POOL_START, A_k)` and `mom(T)` non-NaN, each bar once
  (bar-pool, same convention as oc_idea6; per-bar signal so no 5x sym
  replication). `POOL_START = 2020-08-01 00:00 UTC` (as in oc_idea6, past
  the sparse listing region). Require >= 100 training values else the
  year's gate is undefined (reported as FAIL; not expected: year 0 has
  ~2500 bars).
- v410 bear regime FIRST (audited v410 rule, BTC-only, causal at close
  of T, exactly as oc_bearshort): on the FULL `opens_v154` BTCUSDT history
  compute `MA1200[T] = mean(open_BTC[T-1199..T])`, `rolling(1200,
  min_periods=600)`; `bear[T] = (open_BTC[T] < MA1200[T])` (strict;
  NaN -> False; `open[T]` inclusive). One regime flag per bar, applied to
  all 5 coins.
- BASE (reference, = deployed book with v410): `w_base[T,s] = 0.5*w_raw[T,s]`
  if `bear[T] and w_raw[T,s] > 0`, else `w_raw[T,s]`. Shorts (`<0`), flats
  (`==0`) unchanged.
- RULE (this idea, fixed multiplier, sequential filters): for each (T, sym)
  in year k, `flagged(T) = isfinite(mom(T)) and (mom(T) < p20_k)` (strictly
  below; ties stay off); `w_rule[T,s] = 0.5 * w_base[T,s]` if `flagged(T)`
  and `w_base[T,s] > 0`, else `w_base[T,s]`. Shorts, flats, and NaN-`mom`
  rows are unchanged. Consequence (pre-registered): a long in a bar that is
  both bear and impulse-flagged is 0.25x raw (sequential halving); a long in
  exactly one regime is 0.5x raw. Long-leg membership for attribution is
  fixed by the BASE sign (`w_base > 0`) so base vs rule compare identical
  rows.
- Costs (exactly as oc_dvolshort/oc_bearshort): maker 0.0002 per unit
  turnover. Per (T,s) in global grid order: `cost_base[T,s]` =
  `0.0002*|w_base[T,s]-w_base_prev[s]|` (first grid bar prev = 0.0);
  same formula on the rule path with `w_rule` and its OWN prev chain.
  Net cell: `pnl_base = w_base*R1 - cost_base`,
  `pnl_rule = w_rule*R1 - cost_rule`. No funding, vol target, governor,
  sleeve, SL/TP, or compounding across bars in the per-cell sums; the
  equity path below compounds per-bar portfolio returns.
- Book path per variant: per-bar portfolio return `rp[T] = sum_s pnl[T,s]`
  over the 5 coins (`rp_rule` analogously). Per anchor year, equity reset
  to 1.0 at the year's first bar and compounded in grid order:
  `eq[i+1] = eq[i]*(1+rp[T_i])`. Full 5y path compounds the same way from
  the first bar of year 1 (context only). maxDD = peak-to-trough
  `max(1-eq_trough/running_peak)`. Worst week = minimum 42-bar (7-day)
  compounded return inside the year: `min_{i>=42}(eq[i]/eq[i-42]-1)`.
- Coverage: share of year bars with non-NaN `mom`; filter-on share =
  `mean(flagged)` over year bars; boosted-long share = `mean(rule long rows
  scaled)` (= flagged-row share of base long rows).

## Evaluation (fixed here)

- Per anchor year report: `p20_k`, coverage, filter-on share; long-leg P&L
  base vs rule (net, fixed BASE-sign membership); total book P&L base vs
  rule (net, all rows); worst week base vs rule; maxDD base vs rule
  (per-year reset paths). Full-path maxDD and total P&L base vs rule as
  context (not part of the rule).
- DECISION RULE (assignment-specific, replaces the default same-sign/LOYO
  rule): PROMISING only if (a) total book P&L keeps
  (`pnl_rule >= 0.97 * pnl_base`, NaN = FAIL; if `pnl_base <= 0` in some
  year — not expected, base was positive every year in oc_bearshort —
  the leg requires `pnl_rule >= pnl_base` instead, logged) in >= 4/5
  years, AND (b) maxDD not worse (`DD_rule <= DD_base`, tolerance 1e-12
  for float noise) in >= 4/5 years. NaN on either side counts as FAIL.
  One-line verdict. The default tournament LOYO rule is N/A by
  construction: thresholds are already strictly walk-forward (no
  cross-year pooling), so there is no in-year fit to leave out.
- Cost context: weights average << 1, so per-cell sums are in
  portfolio-return units; the per-year equity paths above are the scale
  that matters.

## Causality / alignment tests (tests/test_oc_basisbook.py)

- test_books_match_dvolshort: rebuilt books equal oc_dvolshort's formula
  cell by cell on the common index (same files, same math).
- test_basis_causal: sampled T recomputed from qbasis truncated to
  `close_time < T` (and `< T-7d` for the lag leg) are unchanged; no used
  row has `close_time >= T`; synthetic QB4 series maps to
  `basis(T) - basis(T-7d)` with strict-< sampling and NaN iff either leg
  NaN; NaN-`mom` rows are never flagged.
- test_cutoffs_causal: year-k `p20` uses no bar at/after `A_k` (recomputed
  from the saved panel + pool); flagged rows are exactly
  `mom < p20_k` on long-base rows.
- test_grid_bounds: no `T` at/after CUTOFF; years partition the grid
  without gaps/overlaps; non-flagged rows bit-identical base vs rule;
  flagged longs are exactly 0.5x base in the rule path and shorts/flats
  bit-identical; bear-row base longs are exactly 0.5x raw in both paths;
  pnl columns finite.
- test_no_1m: the compute script never references intraday 1m paths.

## Deliverables

`research/tournament/oc_basisbook/`: PLAN.md (this file),
`compute_basisbook.py`, `panel.parquet` (per-(T,sym) raw/base/rule
weights, bear flag, mom, forwards, net cells; small), `results.json`,
`REPORT.md` (tables + one-line verdict). `tests/test_oc_basisbook.py`.
No tuning on results; any post-hoc change logged in REPORT.md. No
commits. LIGHT job: one process, 4h inputs only (no 1m), RAM < 1 GB.

## Post-hoc log

- (none yet; filled only if definitions change after outcomes are seen)
