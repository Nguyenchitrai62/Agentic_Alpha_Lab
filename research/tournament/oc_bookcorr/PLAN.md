# oc_bookcorr PLAN (pre-registered BEFORE any outcome is computed)

Idea #43 (NEW): correlation-scaled book exposure.

## Hypothesis (fixed here)

When the five majors move together, the book's five positions are
effectively one bet: diversification vanishes exactly when drawdowns
cluster. Scaling ALL book targets down when trailing cross-coin
correlation is high should therefore cut the book path's max drawdown at
a small yearly-P&L cost, because high-correlation bars are a minority of
bars but host a majority of drawdown episodes.

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (= `oc_bookic` formula: `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`,
  `d2 = 0.8*o1 + 0.2*(D+Dq)/2`, union index, missing -> 0.0) from
  `artifacts/research/engine_real/` member caches.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens,
  history from 2017 so every scored year has a full 1200-bar bear window
  and a full 180-bar correlation window).
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
  opens non-NaN with the forward open at/before
  `CUTOFF = 2026-09-24 00:00 UTC` (same boundary as oc_dvolshort).
  Weight `w[T,s]` is known at the close of bar `T` and is held over
  `[T, T+1)`.
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years partition the grid
  with no gaps/overlaps: `Y_k = [B_k, B_{k+1})`, `B = ANCHORS +
  [2026-09-24]` (the 2023 year holds 2196 bars, the rest 2190/2189).
- Bear filter FIRST (audited v410, mirrors oc_bullbook BASE exactly): on
  the FULL BTC opens history, `MA1200[T] = mean(BTC_open[T-1199..T])` via
  `rolling(1200, min_periods=600).mean()`; `bear[T] iff BTC_open[T] <
  MA1200[T]` (strict; equality or NaN-MA -> not bear, weight unchanged).
  Flag at `T` uses `open[T]` inclusive, i.e. known at the close of bar `T`.
  `BASE[T,s] = 0.5 * w[T,s] where bear[T] and w[T,s] > 0, else w[T,s]`
  (longs halved in bear; shorts/flat unchanged). BASE is the control path.
- Correlation (fixed rule from the assignment, strictly rows < t only):
  per-coin 4h log returns on the FULL opens history,
  `lr_c[j] = ln(open_c[j] / open_c[j-1])` (NaN where either open is NaN,
  e.g. pre-2020 alts). At grid bar `T` with full-history position `p`,
  the window is `W(T) = {lr[j] : j in [p-180, p-1]}` — 180 returns ending
  at the bar BEFORE `T`, so every input open is at time `< T`. For each
  of the 10 coin pairs, Pearson correlation over pairwise-complete
  overlapping points; a pair is NaN if < 120 overlapping points.
  `rho(T) = mean of the non-NaN pairs`; NaN if fewer than 8 of 10 pairs
  are valid. `rho(T)` uses ONLY information strictly before `T`.
- Scale (fixed, no fitted parameter):
  `s(T) = clip(1.5 - rho(T), 0.5, 1.0)` — no scaling below rho 0.5,
  halved at rho >= 1.0, NaN-rho -> 1.0 (unchanged). One scalar per bar,
  applied to ALL five coins: `SCALED[T,s] = s(T) * BASE[T,s]` (longs,
  shorts and flats alike; flats stay flat).
- Returns: `R1[T,s] = open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- Costs (exactly as oc_dvolshort): maker 0.0002 per unit turnover. Per
  (T, s) in grid order: `cost[T,s] = 0.0002 * |w[T,s] - w_prev[s]|` with
  `w_prev` = the previous grid bar's weight for the same sym (first grid
  bar: prev = 0). Same formula applied to each path with its OWN prev
  (BASE prev for BASE, SCALED prev for SCALED). Net cell:
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
  rows (same scale as oc_dvolshort's `total_pnl`). Compounded yearly net
  `prod(1+rp)-1` reported alongside. Average scale = `mean(s(T))` over
  the year's bars (plus rho coverage = share of bars with non-NaN rho).
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
  change and is valid context — same convention as oc_bullbook, whose
  post-hoc log showed compounding `(1+C)` on native-unit sums is invalid;
  the linear cumsum path is used). Per year, linear cumsum path from 0
  and peak-to-trough decline in native units; worst day reported
  alongside.

## Evaluation (fixed here — one variant only)

- Per anchor year report: rho coverage, mean rho, average scale; book P&L
  BASE vs SCALED (net linear sums); worst week BASE vs SCALED; book maxDD
  BASE vs SCALED (per-year reset paths); combined (book+dip) daily maxDD
  BASE vs SCALED (linear-path context).
- DECISION RULE (assignment-specific, replaces the default for the
  verdict): PROMISING only if (a) book maxDD improves (SCALED strictly <
  BASE, tolerance 0) in >= 4/5 years AND (b) book P&L retains
  >= 90% of BASE (SCALED >= 0.9 * BASE, tolerance 0; if BASE <= 0 in a
  year that year counts as FAIL for leg (b)) in >= 4/5 years. NaN on
  either side counts as FAIL. One-line verdict.
- LOYO stability (descriptive side row, NOT part of the verdict — there
  is no fitted parameter to leave out; the rule, window and clip are
  fixed constants): for the DD-improvement indicator and the retention
  indicator, held-out year h passes iff the held-out indicator equals the
  majority indicator of the other four years. Reported as `loyo_dd`,
  `loyo_ret = n/5`.
- Descriptive only: compounded yearly nets, full-5y path maxDD/total
  (context), dip daily sums per year, combined worst day.
- Cost context: weights average << 1, so per-cell bps overstate portfolio
  impact; the portfolio sums and equity paths above are the scale that
  matters. Vectorised open-to-open screen only (no vol target, governor,
  dip sleeve sizing, funding, SL/TP, or engine limit path).

## Causality / alignment tests (tests/test_oc_bookcorr.py)

- test_results_exists_and_schema: results.json has years/base/scaled/
  combined/loyo/decision with the pre-registered fields.
- test_scale_bounds: 0.5 <= s(T) <= 1.0 everywhere; s == 1.0 wherever
  rho <= 0.5 or rho is NaN; s == 0.5 wherever rho >= 1.0.
- test_corr_causal_on_truncation: rho(T) for sampled T recomputed from
  opens truncated to times < T equals the full-panel row (rows < t only).
- test_bear_matches_v410: bear flags and BASE weights match the v410
  formula (longs x0.5 in bear, shorts/flat unchanged) on synthetic and on
  sampled real rows.
- test_turnover_cost: total_cost == 0.0002 * total_turnover per variant;
  costs non-negative; SCALED turnover uses its own scaled prev.
- test_year_partition_covers_grid: per-year n_bars sum to n_bars; no T
  at/after 2026-09-24 00:00 UTC.
- test_decision_matches_counts: dd-improve and retention counts recomputed
  from yearly rows equal the stored strings; promising flag matches the
  (4/5, 4/5) rule.

## Deliverables

`research/tournament/oc_bookcorr/`: PLAN.md (this file, written BEFORE
any outcome), `compute_bookcorr.py`, `results.json`, REPORT.md (tables +
one-line verdict). `tests/test_oc_bookcorr.py`. No tuning on results; any
post-hoc change logged in REPORT.md. No commits. LIGHT job: one process,
4h + fills inputs only (no 1m), RAM < 1 GB.
