# oc_coinbear PLAN (pre-registered BEFORE any outcome is computed)

Idea #44 (NEW): per-coin bear-book filter.

## Hypothesis (fixed here)

The audited v410 filter halves ALL book LONG targets when BTC's 4h open
is below its 1200-bar mean. `research/tournament/oc_ddanat_g2/REPORT.md`
found the deployment config's gate DD (16.91) is a 59-day BNB-led
book-long + dip grind (2023-04-17..06-15) during which the BTC filter did
not bind. If book-long grinds are coin-led rather than BTC-led, extending
the same x0.5 long haircut to a coin's OWN bear regime (coin 4h open <
its own 1200-bar mean) should cut book maxDD in grind years without
giving up much book P&L. Shorts are unchanged in both variants.

Rule (fixed, ONE variant): a coin's book LONG target is x0.5 when EITHER
BTC's 4h open < its 1200-bar mean (v410) OR the coin's own 4h open < its
own 1200-bar mean. Base = v410 BTC-only filter. Zero fitted parameters.

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (= `oc_bookic` formula: `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`,
  `d2 = 0.8*o1 + 0.2*(D+Dq)/2`, union index, missing -> 0.0) from
  `artifacts/research/engine_real/` member caches.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens,
  history from 2017 so every scored year has a full 1200-bar window).
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
  opens non-NaN (same boundary as oc_dvolshort). Weight `w[T,s]` is known
  at the close of bar `T` and is held over `[T, T+1)`.
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years partition the grid
  with no gaps/overlaps: `Y_k = [B_k, B_{k+1})`, `B = ANCHORS +
  [2026-09-24]` (365-day years; the 2023 year holds 2196 bars).
- Trend flags (causal, mirrors v410/oc_bullshort exactly): on the FULL
  opens history per coin `s`, `MA1200_s[T] = mean(open_s[T-1199..T])` via
  `rolling(1200, min_periods=600).mean()`; `bear_s[T] iff open_s[T] <
  MA1200_s[T]` (strict; equality or NaN-MA -> False, weight unchanged).
  Flag at `T` uses `open[T]` inclusive, i.e. known at the close of bar `T`
  — same timing as v410's decision-row transform. BTC flag is `bear_BTC`;
  each coin also has its own `bear_s` (for BTC the two coincide).
- Filtered weights (one test variant vs base, applied to the raw book
  BEFORE any scaling — there is no vol scale in this screen):
  `BASE[T,s] = 0.5 * w[T,s] where bear_BTC[T] and w[T,s] > 0, else w[T,s]`
  (audited v410 BTC-only long filter; shorts/flat unchanged);
  `RULE[T,s] = 0.5 * w[T,s] where (bear_BTC[T] or bear_s[T]) and w[T,s] > 0,
  else w[T,s]` (per-coin extension; shorts/flat unchanged; BTC rows are
  identical in BASE and RULE by construction). No fitted parameter.
- Returns: `R1[T,s] = open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- Costs (exactly as oc_dvolshort): maker 0.0002 per unit turnover. Per
  (T, s) in grid order: `cost[T,s] = 0.0002 * |w[T,s] - w_prev[s]|` with
  `w_prev` = the previous grid bar's weight for the same sym (first grid
  bar: prev = 0). Same formula applied to each path with its OWN prev
  (BASE prev for BASE, RULE prev for RULE). Net cell: `pnl = w * R1 - cost`
  per path. No funding, vol target, governor, sleeve, SL/TP, or
  compounding across bars in the per-cell sums.
- Book path per variant: per-bar portfolio return `rp[T] = sum_s pnl[T,s]`
  over the 5 coins. Per anchor year, equity is reset to 1.0 at the year's
  first bar and compounded in grid order: `eq[i+1] = eq[i] * (1 + rp[T_i])`
  (exactly as oc_dvolshort). Full 5y path compounds the same way from the
  first bar of year 1 (context only). maxDD of a path =
  `max_{peak<trough} (1 - eq_trough / eq_peak)`. Worst week = minimum
  42-bar (7-day) compounded return inside the year:
  `min_{i>=42} (eq[i]/eq[i-42] - 1)`.
- Book P&L per year (primary): linear net sum `sum(pnl)` over all year
  rows. Long-leg P&L: net cells summed over rows with ORIGINAL raw book
  `w > 0` (fixed membership so BASE vs RULE compare identical rows; same
  convention as oc_dvolshort's leg attribution).
- Newly-halved share per year: `newly[T,s] = (RULE halves) and not (BASE
  halves)` = `bear_s and not bear_BTC and w > 0`; reported as fraction of
  all year (T,sym) rows, plus fraction of year long rows as context.
- Gate window (from oc_ddanat_g2): `W = [2023-04-17, 2023-06-15)` UTC
  (same as oc_bookic `W2_2023-04-17__2023-06-14` end-exclusive+1d).
  Window book loss BASE vs RULE = linear net `sum(pnl)` over grid bars
  with `T` in W, plus the long-leg slice. Descriptive, not in the rule.

## Evaluation (fixed here — one variant only)

- Per anchor year report: book P&L BASE vs RULE (net linear sums);
  long-leg P&L BASE vs RULE; worst week BASE vs RULE; book maxDD BASE vs
  RULE (per-year reset paths); share of coin-bars newly halved; window W
  book loss BASE vs RULE (single row, year 2022-09-24).
- DECISION RULE (assignment-specific, replaces the default for the
  verdict): PROMISING only if (a) book maxDD not worse (RULE DD <= BASE DD
  + 1e-12; equality counts as PASS) in >= 4/5 years, AND (b) book P&L >=
  95% of base (RULE >= 0.95 * BASE when BASE >= 0, else RULE >= 1.05 *
  BASE, i.e. no more than 5% worse in magnitude; NaN on either side counts
  as FAIL) in >= 4/5 years. Otherwise NOT PROMISING. One-line verdict. If
  PROMISING, the leader registers an engine version.
- LOYO (descriptive side row, NOT part of the verdict — there is no fitted
  parameter to leave out; the rule is identical in every fold, same as
  oc_dvolshort): for the book-P&L effect `d_k = P&L_RULE,k - P&L_BASE,k`,
  held-out year h passes iff `sign(d_h) == sign(mean_{k!=h} d_k)`; for the
  DD effect `e_k = DD_BASE,k - DD_RULE,k` (positive = improves), held-out h
  passes iff `sign(e_h) == sign(mean_{k!=h} e_k)` and that training mean is
  `> 0`. Reported as `loyo_pnl = n/5`, `loyo_dd = n/5`.
- Cost context: weights average << 1, so per-cell bps overstate portfolio
  impact; the portfolio sums and equity paths above are the scale that
  matters. Vectorised open-to-open screen only (no vol target, governor,
  dip sleeve sizing, funding, SL/TP, or engine limit path).

## Causality / alignment tests (tests/test_oc_coinbear.py)

- test_results_exists_and_schema: results.json has years/base/rule/window/
  loyo/decision with the pre-registered fields.
- test_year_partition_covers_grid: per-year n_bars sum to n_bars; no T at
  or after 2026-09-24 00:00 UTC.
- test_turnover_cost: total_cost == 0.0002 * total_turnover per variant;
  costs non-negative; RULE turnover uses its own prev.
- test_decision_matches_counts: dd-not-worse count and pnl-95% count
  recomputed from yearly rows equal the stored strings; promising flag
  matches the (4/5, 4/5) rule.
- test_filter_math_handchecked: synthetic books with forced BTC-bear /
  own-bear rows: BTC-bear longs x0.5 in both; own-bear-only longs x0.5 in
  RULE only; shorts/flat unchanged; BTC rows identical in BASE and RULE.
- test_regimes_causal_on_truncation: per-coin MA1200/bear flags recomputed
  from opens truncated at a cut are unchanged on the kept grid.
- test_books_match_oc_bookic: rebuilt books equal oc_bookic's formula cell
  by cell on the common index.

## Deliverables

`research/tournament/oc_coinbear/`: PLAN.md (this file, written BEFORE any
outcome), `compute_coinbear.py`, `panel.parquet` (per-(T,sym) weights,
flags, forwards, net cells; small), `results.json`, REPORT.md (tables +
one-line verdict). `tests/test_oc_coinbear.py`. No tuning on results; any
post-hoc change logged in REPORT.md. No commits. LIGHT job: one process,
4h inputs only (no 1m), RAM < 1 GB.
