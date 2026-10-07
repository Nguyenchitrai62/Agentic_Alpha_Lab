# oc_longcap PLAN (pre-registered BEFORE any outcome is computed)

Idea #46 (NEW): total book-long cap.

## Hypothesis (fixed here)

In the deployment config's gate grind (2023-04-17..06-15,
`research/tournament/oc_ddanat_g2`) several majors are long together:
per-phase attribution shows book longs -9..-11pp per phase with shorts
offsetting (+0.45..+2.69), i.e. the book-long leg carries the grind while
diversification across five simultaneous longs vanishes. Capping the total
book-long exposure when many majors are long together should therefore cut
the book path's max drawdown at a small yearly-P&L cost, because
high-long-sum bars are a minority of bars but host the grind episodes.

Rule (fixed, from the assignment): at each standard book row `T`, AFTER the
v410 bear filter, let `L(T) = sum of positive book target weights`. If
`L(T) > 0.6` (of equity), scale all LONG targets down proportionally so
the sum = 0.6; shorts unchanged.

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (= `oc_bookic` formula: `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`,
  `d2 = 0.8*o1 + 0.2*(D+Dq)/2`, union index, missing -> 0.0) from
  `artifacts/research/engine_real/` member caches.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens,
  history from 2017 so every scored year has a full 1200-bar bear window).
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
  [2026-09-24]` (same as oc_bookcorr; the 2023 year holds the leap-day
  bars).
- Bear filter FIRST (audited v410, mirrors oc_bullshort/oc_bookcorr BASE
  exactly): on the FULL BTC opens history,
  `MA1200[T] = mean(BTC_open[T-1199..T])` via
  `rolling(1200, min_periods=600).mean()`;
  `bear[T] iff BTC_open[T] < MA1200[T]` (strict; equality or NaN-MA ->
  not bear, weight unchanged). Flag at `T` uses `open[T]` inclusive, i.e.
  known at the close of bar `T`.
  `BASE[T,s] = 0.5 * w[T,s] where bear[T] and w[T,s] > 0, else w[T,s]`
  (longs halved in bear; shorts/flat unchanged). BASE is the control path.
- Long cap (fixed threshold, no fitting): per bar `T`,
  `L(T) = sum_{s: BASE[T,s] > 0} BASE[T,s]`.
  If `L(T) > 0.6`: `scale(T) = 0.6 / L(T)`, else `scale(T) = 1.0`.
  `CAPPED[T,s] = scale(T) * BASE[T,s] where BASE[T,s] > 0, else BASE[T,s]`
  (longs scaled proportionally; shorts/flats bit-identical; sign never
  flips). The cap uses only the contemporaneous BASE row, hence only
  information known at the close of `T`.
- Returns: `R1[T,s] = open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- Costs (exactly as oc_dvolshort): maker 0.0002 per unit turnover. Per
  (T, s) in grid order: `cost[T,s] = 0.0002 * |w[T,s] - w_prev[s]|` with
  `w_prev` = the previous grid bar's weight for the same sym (first grid
  bar: prev = 0). Same formula applied to each path with its OWN prev
  (BASE prev for BASE, CAPPED prev for CAPPED). Net cell:
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
  rows (same scale as oc_dvolshort's `total_pnl`). Long-leg P&L per year:
  linear net sum over cells with `BASE[T,s] > 0` (membership fixed by the
  BASE sign so both paths compare identical rows; the cap never flips a
  sign). Compounded yearly net `prod(1+rp)-1` reported alongside.
- Long-sum distribution (reported first): on BASE weights over the full
  grid and per year: mean, quantiles (p50/p75/p90/p95/p99/max), share of
  bars with `L > 0.6` (binding share), `L > 0.8`, `L > 1.0`, mean `L`
  conditional on binding, mean scale conditional on binding.
- Gate-grind window: `W = [2023-04-17 00:00, 2023-06-15 12:00)` UTC
  (covers the oc_ddanat_g2 2023-04-17 -> 2023-06-15 episode on the 4h
  grid). Window loss BASE vs CAPPED = linear net `sum(pnl)` over grid
  bars with `T in W`, plus window long-leg sums and window binding share.
  Window bars use the same per-cell pnl as the yearly screen.

## Evaluation (fixed here — one variant only)

- Per anchor year report: binding share; book P&L BASE vs CAPPED (net
  linear sums); long-leg P&L BASE vs CAPPED; worst week BASE vs CAPPED;
  book maxDD BASE vs CAPPED (per-year reset paths). Plus the window loss
  BASE vs CAPPED and the long-sum distribution table.
- DECISION RULE (assignment-specific, replaces the default for the
  verdict): PROMISING only if (a) book maxDD not worse
  (CAPPED <= BASE, tolerance 0) in >= 4/5 years AND (b) book P&L retains
  >= 95% of BASE (CAPPED >= 0.95 * BASE, tolerance 0; if BASE <= 0 in a
  year that year counts as FAIL for leg (b)) in >= 4/5 years. NaN on
  either side counts as FAIL. One-line verdict.
- LOYO stability (descriptive side row, NOT part of the verdict — there
  is no fitted parameter to leave out; the threshold 0.6 is a fixed
  constant): for the DD-not-worse indicator and the retention indicator,
  held-out year h passes iff the held-out indicator equals the majority
  indicator of the other four years. Reported as `loyo_dd`,
  `loyo_ret = n/5`.
- Descriptive only: compounded yearly nets, full-5y path maxDD/total
  (context), short-leg sums.
- Cost context: weights average << 1, so per-cell bps overstate portfolio
  impact; the portfolio sums and equity paths above are the scale that
  matters. Vectorised open-to-open screen only (no vol target, governor,
  dip sleeve sizing, funding, SL/TP, or engine limit path).

## Causality / alignment tests (tests/test_oc_longcap.py)

- test_results_exists_and_schema: results.json has longsum/years/window/
  full_path/loyo/decision with the pre-registered fields.
- test_cap_math: CAPPED longs sum to <= 0.6 + 1e-12 on every bar; bars
  with BASE long-sum <= 0.6 are bit-identical; shorts/flats bit-identical
  everywhere; scale == 0.6/L on binding bars.
- test_bear_matches_v410: bear flags and BASE weights match the v410
  formula (longs x0.5 in bear, shorts/flat unchanged) on synthetic and on
  sampled real rows.
- test_turnover_cost: total_cost == 0.0002 * total_turnover per variant;
  costs non-negative; CAPPED turnover uses its own capped prev.
- test_year_partition_covers_grid: per-year n_bars sum to n_bars; no T
  at/after 2026-09-24 00:00 UTC; window bounds inside the grid.
- test_decision_matches_counts: dd-not-worse and retention counts
  recomputed from yearly rows equal the stored strings; promising flag
  matches the (4/5, 4/5) rule.

## Deliverables

`research/tournament/oc_longcap/`: PLAN.md (this file, written BEFORE
any outcome), `compute_longcap.py`, `panel.parquet`, `results.json`,
REPORT.md (tables + one-line verdict). `tests/test_oc_longcap.py`. No
tuning on results; any post-hoc change logged in REPORT.md. No commits.
LIGHT job: one process, 4h inputs only (no 1m), RAM < 1 GB.
