# oc_bearshort PLAN (pre-registered BEFORE any outcome is computed)

Idea #53 (NEW): bear-regime book short boost.

## Hypothesis (fixed here)

The audited v410 filter halves book LONG targets in the bear regime (BTC 4h
open < 1200-bar mean) and is already in the deployed book. Bear-regime bars
are trend-persistent down-drift bars where the book's short leg should carry
more of the book risk budget: longs are already (correctly) de-risked, so
leaving shorts at full size under-uses the regime edge. Scaling book SHORT
targets up (x1.25) exactly on v410 bear rows should raise total book P&L in
most anchor years at no systematic drawdown cost, because the extra short
size rides the same persistent drift that motivated the long cut, while in
non-bear rows nothing changes.

Rule (fixed, from the assignment): in bear rows book SHORT targets x1.25
(longs x0.5 as v410). No other change.

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (mirror of `oc_bookic/compute_bookic.py::research_books_d2`):
  `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`, `d2 = 0.8*o1 + 0.2*(D+Dq)/2`,
  union index, missing -> 0.0, from `artifacts/research/engine_real/`
  (`member_A_O1_orders`, `member_Aq_O1_orders`, `member_B_tv`,
  `member_Bq_tv`, `members_v154[D]`, `members_quarterly_D`).
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens).
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides
  the old tournament-harness hidden-year cut; all five years are research
  data, findings still need prospective validation).
- No 1m data, one process, RAM < 1 GB (two small 4h frames only).
- Shared ext/fills/dvol/options/premium inputs listed in the assignment
  header are NOT used: the assignment orders the screen with the vectorised
  BOT book exactly as research/tournament/oc_dvolshort did (base = v410
  filter).

## Exact causal definitions (fixed before seeing numbers)

- BOUND/CUTOFF = 2026-09-24 00:00 UTC. Grid = inner join of the rebuilt
  book index with the opens index (dropna all), sorted 4h, restricted to
  `T in [2021-09-24, CUTOFF)`; bars with any coin missing a forward open
  are dropped (same as oc_dvolshort: the last grid bar has no forward
  open and is dropped). `w[T,s]` is known at the close of bar `T` and is
  held over `[T, T+1)`. Forward exit `open[T+1]` must be at/before CUTOFF.
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years partition, no
  orphan bars: `Y_k = [A_k, A_{k+1})` for k = 0..3,
  `Y_4 = [A_4, A_4+365d)` (== `[A_4, CUTOFF)`; same bounds construction
  as oc_dvolshort: `bounds = ANCHORS + [A_4 + 365d]`).
- Returns: `R1[T,s]` = `open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- v410 bear regime FIRST (audited v410 rule, BTC-only, causal at close
  of T): on the FULL `opens_v154` BTCUSDT history compute
  `MA1200[T] = mean(open_BTC[T-1199..T])`, `rolling(1200, min_periods=600)`;
  `bear[T] = (open_BTC[T] < MA1200[T])` (strict; NaN -> False; `open[T]`
  inclusive, known at the close of T, exactly as v410/v410_bear_book.py
  and oc_bookcoinbrake). One regime flag per bar, applied to all 5 coins.
- BASE (reference, = deployed book with v410): `w_base[T,s] = 0.5*w_raw[T,s]`
  if `bear[T] and w_raw[T,s] > 0`, else `w_raw[T,s]`. Shorts (`<0`), flats
  (`==0`) unchanged.
- RULE (this idea, fixed multipliers): `w_rule[T,s] = 1.25*w_base[T,s]` if
  `bear[T] and w_base[T,s] < 0`, else `w_base[T,s]`. Bear-row longs stay at
  the v410 x0.5 (bit-identical to base); non-bear rows are bit-identical
  to base for every sign; flats unchanged. Short-leg membership for P&L
  attribution is fixed by the BASE sign (`w_base < 0` == raw short rows,
  since v410 never touches shorts) so base vs rule compare identical rows.
- Costs (exactly as oc_dvolshort): maker 0.0002 per unit turnover.
  Per (T,s) in global grid order: `cost_base[T,s]` =
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
- Short-leg P&L per year = summed net cells over BASE short rows
  (`w_base < 0`) within the year, base vs rule. Total book P&L = summed
  net cells over all rows within the year. Bear share per year =
  `mean(bear[T])` over year bars; boosted-short share = `mean(rule short
  rows boosted)` (= bear-row share of base short rows).

## Evaluation (fixed here)

- Per anchor year report: bear share; short-leg P&L base vs rule (net,
  fixed membership); total book P&L base vs rule (net, all rows); worst
  week base vs rule; maxDD base vs rule (per-year reset paths). Full-path
  maxDD and total P&L base vs rule as context (not part of the rule).
- DECISION RULE (assignment-specific, replaces the default same-sign/LOYO
  rule): PROMISING only if (a) total book P&L strictly higher
  (`pnl_rule > pnl_base`) in >= 4/5 years, AND (b) maxDD not worse
  (`DD_rule <= DD_base`, tolerance 1e-12 for float noise) in >= 4/5 years.
  NaN on either side counts as FAIL. One-line verdict. The default
  tournament LOYO rule is N/A by construction: the rule has no fitted
  threshold (fixed x1.25 / x0.5 multipliers, fixed 1200-bar regime), so
  there is no in-year fit to leave out.
- Cost context: weights average << 1, so per-cell sums are in
  portfolio-return units; the per-year equity paths above are the scale
  that matters.

## Causality / alignment tests (tests/test_oc_bearshort.py)

- test_books_match_dvolshort: rebuilt books equal oc_dvolshort's formula
  cell by cell on the common index (same files, same math).
- test_bear_causal: bear[T] recomputed from opens truncated to `<= T`
  is unchanged; NaN-MA rows never scaled; non-bear rows bit-identical
  base vs rule; bear-row longs are exactly 0.5x raw in both paths;
  bear-row shorts are exactly 1.25x base in the rule path and longs/flats
  bit-identical base vs rule.
- test_grid_bounds: no `T` at/after CUTOFF; years partition the grid
  without gaps/overlaps; pnl columns finite; short-leg membership fixed
  by base sign.

## Deliverables

`research/tournament/oc_bearshort/`: PLAN.md (this file),
`compute_bearshort.py`, `panel.parquet` (per-(T,sym) raw/base/rule
weights, bear flag, forwards, net cells; small), `results.json`,
`REPORT.md` (tables + one-line verdict). No tuning on results; any
post-hoc change logged in REPORT.md. No commits. LIGHT job: one process,
4h inputs only (no 1m), RAM < 1 GB.

## Post-hoc log

- (none yet; filled only if definitions change after outcomes are seen)
