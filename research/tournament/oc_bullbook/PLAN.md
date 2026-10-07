# oc_bullbook PLAN (pre-registered BEFORE any outcome is computed)

Idea #26 (NEW): bull-regime book boost — the mirror of the audited v410
bear-book filter (book LONG targets x0.5 when the BTC 4h open < its
1200-bar mean; it cut DD at no return cost).

## Hypothesis (fixed here)

If the bear filter works because book longs bleed in downtrends, the mirror
should hold: in confirmed bull regimes the book's LONG leg earns more than
its extra drawdown costs, so scaling book LONG targets UP (x1.25) only on
bull rows should raise total book P&L without systematically worsening
book maxDD. The 180-bar (30-day) return confirmation is pre-registered to
avoid boosting dead-cat bounces that sit above a falling 1200-bar mean.

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (= `oc_bookic` formula: `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`,
  `d2 = 0.8*o1 + 0.2*(D+Dq)/2`, union index, missing -> 0.0) from
  `artifacts/research/engine_real/` member caches.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens,
  history from 2017 so every scored year has a full 1200-bar window).
- Dip stream (context only): `research/tournament/ext/fills_U_ext.parquet`
  with `y_dep` exactly as `research/tournament/ext/harness5.py::load`
  (deployed R2 table; fees + adverse funding already inside), daily sums
  exactly as `oc_idea7` scores them.
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override;
  all five years are research data; any finding needs prospective
  validation).
- LIGHT job: one process, 4h opens + book parquets + fills table only
  (no 1m data), RAM < 1 GB.

## Exact causal definitions (fixed now, before seeing numbers)

- Grid: inner join of the book index with the opens index (dropna all),
  sorted 4h grid; `T` in `[2021-09-24, 2026-09-24)` UTC; the last grid bar
  (no forward open) is dropped and every kept bar must have all 5 forward
  opens non-NaN (same boundary as oc_dvolshort). Weight `w[T,s]` is known
  at the close of bar `T` and is held over `[T, T+1)`.
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years partition the grid
  with no gaps/overlaps: `Y_k = [B_k, B_{k+1})`, `B = ANCHORS +
  [2026-09-24]` (the 2023 year holds 2196 bars, the rest 2190/2189).
- Trend (causal, mirrors v410/oc_bullshort exactly): on the FULL BTC opens
  history, `MA1200[T] = mean(BTC_open[T-1199..T])` via
  `rolling(1200, min_periods=600).mean()`; `bear[T] iff BTC_open[T] <
  MA1200[T]`, `bull[T] iff BTC_open[T] > MA1200[T]` (strict; equality or
  NaN-MA -> neither, weight unchanged). Flag at `T` uses `open[T]`
  inclusive, i.e. known at the close of bar `T` — same timing as v410's
  decision-row transform.
- Confirmation (causal, fixed): `ret180[T] = BTC_open[T] / BTC_open[T-180]
  - 1` (180 4h bars = 30 days; both opens known at the close of `T`).
  `bullboost[T] iff bull[T] and ret180[T] > 0` (strict; NaN ret180 ->
  False). `bear` and `bullboost` are mutually exclusive by construction.
- Filtered weights (single test variant vs baseline, applied to the raw
  book BEFORE any scaling — there is no vol scale in this screen):
  `BASE[T,s] = 0.5 * w[T,s] where bear[T] and w[T,s] > 0, else w[T,s]`
  (audited v410 bear-long filter; shorts/flat unchanged);
  `BOOST[T,s] = 1.25 * BASE[T,s] where bullboost[T] and BASE[T,s] > 0,
  else BASE[T,s]` (bull rows: longs x1.25; shorts/flat unchanged; bear
  rows keep the x0.5 filter). No fitted parameter anywhere.
- Returns: `R1[T,s] = open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- Costs (from the assignment): 0.05% per unit turnover. Per (T, s) in grid
  order: `cost[T,s] = 0.0005 * |w[T,s] - w_prev[s]|` with `w_prev` = the
  previous grid bar's weight for the same sym (first grid bar: prev = 0).
  Same formula applied to each path with its OWN prev (BASE prev for BASE,
  BOOST prev for BOOST). Net cell: `pnl = w * R1 - cost` per path.
- Book path per variant: per-bar portfolio return `rp[T] = sum_s pnl[T,s]`
  over the 5 coins. Per anchor year, equity is reset to 1.0 at the year's
  first bar and compounded in grid order: `eq[i+1] = eq[i] * (1 + rp[T_i])`
  (exactly as oc_dvolshort). Full 5y path compounds the same way from the
  first bar of year 1 (context only). maxDD of a path =
  `max_{peak<trough} (1 - eq_trough / eq_peak)`. Worst week = minimum
  42-bar (7-day) compounded return inside the year:
  `min_{i>=42} (eq[i]/eq[i-42] - 1)`.
- Book P&L per year (primary): linear net sum `sum(pnl)` over all year
  rows (same scale as oc_dvolshort's `total_pnl`). Compounded yearly net
  `prod(1+rp)-1` reported alongside (same ranking at these weight
  scales). Long-leg P&L: net cells summed over rows with ORIGINAL raw
  book `w > 0` (fixed membership so BASE vs BOOST compare identical rows;
  same convention as oc_dvolshort's short-leg attribution).
- Dip stream (context only, no decision weight): `harness5.load()`,
  universe = majors rows with `size_dep` non-NaN (= BOT rungs, as
  `oc_idea7`'s `is_r2`: majors x R2 depths at the deployed TP; outcome
  `y_dep` exact net). Dip daily = `sum(size_dep * y_dep)` grouped by
  `floor(T to UTC calendar day)`. Book daily = `sum(rp)` grouped by
  `floor(T to UTC calendar day)`. Combined daily = book daily + dip daily
  (disclosed vectorised-screen approximation: book rp are fractions of a
  book sleeve and dip sums are size*y units, so the absolute combined
  level is NOT engine equity; the dip stream is IDENTICAL in both
  variants, hence the combined-DD DELTA is driven purely by the book
  change and is valid context). Per year, daily equity reset to 1.0 and
  compounded: `eq_d[j+1] = eq_d[j] * (1 + C[d_j])`; combined maxDD on the
  daily closes. Worst day reported alongside.

## Evaluation (fixed here — one variant only)

- Per anchor year report: share of bars bear / bullboost; share of long
  rows boosted; book P&L BASE vs BOOST (net linear sums); long-leg P&L
  BASE vs BOOST; worst week BASE vs BOOST; book maxDD BASE vs BOOST
  (per-year reset paths); combined (book+dip) daily maxDD BASE vs BOOST.
- DECISION RULE (assignment-specific, replaces the default for the
  verdict): PROMISING only if (a) book P&L higher (BOOST strictly >
  BASE) in >= 4/5 years AND (b) book maxDD not worse (BOOST strictly <
  BASE, tolerance 0; equality counts as FAIL) in >= 3/5 years. NaN on
  either side counts as FAIL. One-line verdict.
- LOYO stability (descriptive side row, NOT part of the verdict — there is
  no fitted parameter to leave out; thresholds are fixed constants):
  for the book-P&L effect `d_k = P&L_BOOST,k - P&L_BASE,k`, held-out year h
  passes iff `sign(d_h) == sign(mean_{k!=h} d_k)` and that training mean is
  `> 0` (NaN -> fail). Reported as `loyo_pnl = n/5`.
- Descriptive only: compounded yearly nets, full-5y path maxDD/total
  (context), dip daily sums per year, combined worst day.
- Cost context: weights average << 1, so per-cell bps overstate portfolio
  impact; the portfolio sums and equity paths above are the scale that
  matters. Vectorised open-to-open screen only (no vol target, governor,
  dip sleeve sizing, funding, SL/TP, or engine limit path).

## Causality / alignment tests (tests/test_oc_bullbook.py)

- test_results_exists_and_schema: results.json has years/base/boost/
  combined/loyo/decision with the pre-registered fields.
- test_year_partition_covers_grid: per-year n_bars sum to n_bars;
  2023 year has 2196 bars (leap-day partition).
- test_turnover_cost: total_cost == 0.0005 * total_turnover per variant;
  costs non-negative; BOOST turnover uses its own boosted prev.
- test_decision_matches_counts: pnl_higher count and dd_not_worse count
  recomputed from yearly rows equal the stored strings; promising flag
  matches the (4/5, 3/5) rule.
- test_filter_math_handchecked: synthetic books with forced bear /
  bullboost rows: bear longs x0.5, bullboost longs x1.25, shorts/flat
  unchanged, bear rows never boosted.
- test_regimes_causal_on_truncation: MA1200/bull/bear/ret180/bullboost
  recomputed from opens truncated at a cut are unchanged on the kept grid.
- test_T_and_bounds: no T at/after 2026-09-24 00:00 UTC; no fill with
  T >= 2026-09-24 in the dip stream.

## Deliverables

`research/tournament/oc_bullbook/`: PLAN.md (this file, written BEFORE any
outcome), `compute_bullbook.py`, `results.json`, REPORT.md (tables +
one-line verdict). `tests/test_oc_bullbook.py`. No tuning on results; any
post-hoc change logged in REPORT.md. No commits. LIGHT job: one process,
4h + fills inputs only (no 1m), RAM < 1 GB.
