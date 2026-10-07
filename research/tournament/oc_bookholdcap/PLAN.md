# oc_bookholdcap PLAN (pre-registered BEFORE any outcome is computed)

Idea #65 (NEW): maximum holding time for book positions.

## Hypothesis (fixed here)

Stale book positions held continuously in one direction for a full week
(42 consecutive 4h bars) contribute negatively on a net-of-turnover basis
and disproportionately to path drawdown: a slow 4h momentum book that never
refreshes sits through mean-reversion and regime shifts while its edge
decays, and the forced-hold tail overlaps the worst 7-day windows. Forcing
a one-bar flat (target 0) after 42 consecutive same-sign bars — after which
the normal targets resume — should therefore keep most of the book P&L
while not worsening maxDD (a turnover-paying insurance cut).

Rule (fixed, from the assignment): a coin's book position that has kept the
same sign for 42 consecutive 4h rows (7 days) is set to 0 for the next row
(forced exit), after which the normal targets resume.

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
  `CUTOFF = 2026-09-24 00:00 UTC` (same boundary as oc_dvolshort /
  oc_bookweekend). Weight `w[T,s]` is known at the close of bar `T` and is
  held over `[T, T+1)`.
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years partition the grid
  with no gaps/overlaps: `Y_k = [B_k, B_{k+1})`, `B = ANCHORS +
  [2026-09-24]` (the 2023 year holds the leap-day bars).
- Bear filter FIRST (audited v410, mirrors oc_bookweekend BASE exactly): on
  the FULL BTC opens history, `MA1200[T] = mean(BTC_open[T-1199..T])` via
  `rolling(1200, min_periods=600).mean()`;
  `bear[T] iff BTC_open[T] < MA1200[T]` (strict; equality or NaN-MA ->
  not bear, weight unchanged). Flag at `T` uses `open[T]` inclusive, i.e.
  known at the close of bar `T`.
  `BASE[T,s] = 0.5 * w[T,s] where bear[T] and w[T,s] > 0, else w[T,s]`
  (longs halved in bear; shorts/flat unchanged). BASE is the control path.
- Hold-cap rule (single fixed variant, no fitting): per sym independently,
  in global grid order (history carries continuously across year
  boundaries, never reset per year), let `c[j,s]` be the capped weight
  already decided for grid positions `< i`. At grid position `i` (time
  `T_i`), with `H = 42`: if `i >= H` and the previous `H` capped weights
  for the same sym are ALL strictly positive (`c[i-H..i-1,s] > 0`) or ALL
  strictly negative (`c[i-H..i-1,s] < 0`), then
  `RULE[T_i,s] = 0.0` (forced flat for exactly one row); otherwise
  `RULE[T_i,s] = BASE[T_i,s]`. Zeros (either from BASE or from a prior
  forced flat) break a run, so a forced flat always resets the streak and
  the normal targets resume on the next bar; the first 42 grid bars of each
  sym can never be forced (insufficient history). The decision at `T_i`
  uses only capped weights of bars `< i` plus `BASE[T_i,s]` (both known at
  the close of `T_i`; no forward data).
- Returns: `R1[T,s] = open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- Costs (assignment: 0.05% per unit turnover): maker `0.0005` per unit
  turnover. Per (T, s) in grid order:
  `cost[T,s] = 0.0005 * |w[T,s] - w_prev[s]|` with `w_prev` = the previous
  grid bar's weight for the same sym (first grid bar: prev = 0; history is
  global, not reset per year). Same formula applied to each path with its
  OWN prev (BASE prev for BASE, RULE prev for RULE), so the forced-close
  and the resume-reopen turnover is charged to the RULE path. Net cell:
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
  rows (same scale as oc_dvolshort's `total_pnl`), BASE vs RULE. Turnover
  cost totals per year per path. Share forced flat per year =
  `(# forced-flat (T,sym) cells in year) / (# (T,sym) cells in year)`;
  also report the raw forced count.
- Coverage: hold-cap needs no external feature, so coverage is 1.0 by
  construction (reported for schema parity).

## Evaluation (fixed here — one variant only)

- Per anchor year report: n_bars, n_cells, n_forced, forced share; book
  P&L net BASE vs RULE (and RULE/BASE ratio); costs BASE vs RULE; worst
  week BASE vs RULE; book maxDD BASE vs RULE (per-year reset paths). Plus
  full-5y path maxDD/total (context).
- DECISION RULE (assignment-specific, governs the verdict): PROMISING only
  if (a) net book P&L RULE >= 97% of BASE in >= 4/5 years AND
  (b) book maxDD not worse (RULE <= BASE, tolerance 0) in >= 4/5 years.
  Ratio detail: pass (a) iff `RULE >= 0.97 * BASE` when `BASE > 0`, iff
  `RULE >= BASE` when `BASE <= 0` (a losing/zero base year must not get
  worse), NaN on either side counts as FAIL. One-line verdict.
- LOYO stability (descriptive side row, NOT part of the verdict — there is
  no fitted parameter to leave out; H = 42 is a fixed constant): for the
  P&L->=97% indicator and the DD-not-worse indicator, held-out year h
  passes iff the held-out indicator equals the majority indicator of the
  other four years. Reported as `loyo_pnl`, `loyo_dd = n/5`.
- Cost context: weights average << 1, so per-cell sums are in
  portfolio-return units; the portfolio sums and equity paths above are the
  scale that matters. Vectorised open-to-open screen only (no vol target,
  governor, dip sleeve sizing, funding, SL/TP, or engine limit path).

## Causality / alignment tests (tests/test_oc_bookholdcap.py)

- test_results_exists_and_schema: results.json has meta/years/full_path/
  loyo/decision with the pre-registered fields.
- test_holdcap_math: RULE is 0 exactly on forced rows and bit-identical to
  BASE elsewhere; every forced row has 42 prior capped weights all same
  non-zero sign for that sym; no unforced row has 42 prior capped all same
  non-zero sign; max capped same-sign run length (excluding the forced
  break) is <= 42; first 42 grid bars per sym are never forced; forced
  share recomputes.
- test_bear_matches_v410: bear flags match the v410 formula
  (`BTC open < rolling(1200,min600) mean`, NaN -> False) on sampled real
  rows; BASE == raw book with longs x0.5 in bear (synthetic + sampled).
- test_turnover_cost: per-sym `cost == 0.0005 * |w - w_prev|` (own prev,
  first prev = 0, global order) for both paths; costs non-negative.
- test_year_partition_covers_grid: per-year n_cells sum to n_panel; no T
  at/after 2026-09-24 00:00 UTC; P&L ratio and both counts recomputed from
  yearly rows equal the stored strings; promising flag matches the
  (4/5, 4/5 with 97%) rule.

## Deliverables

`research/tournament/oc_bookholdcap/`: PLAN.md (this file, written BEFORE
any outcome), `compute_bookholdcap.py`, `panel.parquet`, `results.json`,
REPORT.md (tables + one-line verdict). `tests/test_oc_bookholdcap.py`. No
tuning on results; any post-hoc change logged in REPORT.md. No commits.
LIGHT job: one process, 4h inputs only (no 1m), RAM < 1 GB.
