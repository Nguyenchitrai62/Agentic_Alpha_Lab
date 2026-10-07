# oc_coinwf PLAN (pre-registered BEFORE any outcome is computed)

Idea #12: walk-forward per-coin dip weights. Coins whose dip rungs had a
better risk-adjusted history get a modestly larger rung size next year.

## Hypothesis (fixed here)

Per-coin Sharpe-like score of past dip-rung outcomes predicts next-year
relative performance well enough that Sharpe-proportional coin weights lower
drawdown without giving up return. PROMISING only under the rule below.

## Data (fixed here)

- Source: `research/tournament/ext/fills_U_ext.parquet` (35 coins,
  2020-08..2026-09). Universe MAIN = majors {BTCUSDT, ETHUSDT, SOLUSDT,
  BNBUSDT, XRPUSDT} x R2 depths `x1` in {2.5, 3.0, 3.5, 4.0, 5.0}.
- Outcome = `y1.0` only (exact net return at TP 1.0 sigma, unit rung size,
  fees + adverse funding in). `y0.5`/`y1.5` are NOT scored.
- `T = t_fill - f` minutes (bar open; verified on 4h boundaries, descriptive
  only). Year membership and history filtering are keyed by `t_fill`
  (fill time, minute-exact).
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old RULES.md hidden-year cut; all five years are research data and any
  finding needs prospective validation before real money).
- LIGHT job: one process, RAM < 1 GB (fills file ~72k rows only), no 1m data,
  no GPU.

## Anchors and pools (exact, causal)

- Anchors A_k in {2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24, 2025-09-24}
  00:00 UTC. Test year Y_k = rows with `t_fill` in [A_k, A_k + 365d).
- Training pool H_k = MAIN-universe rows with `t_fill` strictly after
  2020-08-01 00:00 UTC AND strictly before (A_k - 7 days) (embargo).
  `t_exit` is NOT part of the filter (assignment literal; exits land within
  hours so the 7-day embargo covers exit-knowledge in practice; logged as a
  caveat).
- No statistic from Y_k (or any later row) feeds the weights for Y_k.

## Weights (exact formula, one variant only)

Per anchor k and coin c (5 coins), over H_k rows of coin c, outcome v=y1.0:

- `n_c` = row count; `mu_c` = mean(v); `sd_c` = sample std (ddof=1).
- `score_c = mu_c / sd_c` if `n_c >= 30` and mu_c, sd_c finite and sd_c > 0,
  else NaN (FAIL-safe: NaN scores get weight 1.0 below).
- `mean_score = mean(score_c)` over the 5 coins using finite scores only.
  If fewer than 5 finite scores, or mean_score non-finite, or
  mean_score <= 0, fall back to `w_c = 1.0` for all 5 coins that year
  (documented in results as `fallback=true`).
- Else `w_raw_c = clip(score_c / mean_score, 0.5, 1.5)` (NaN score -> 1.0),
  then `w_c = w_raw_c / mean_5(w_raw)` so `mean_c w_c = 1` exactly
  (equal total exposure by construction; per-year coin-count imbalance is NOT
  rebalanced further).
- Apply: test row i of coin c in Y_k contributes `w_c(k) * y1.0_i`
  (weighted) vs `y1.0_i` (unweighted). Weights are per-coin constants within
  the year, applied to every R2 rung of that coin.

No other variant. No thresholds are fit on test outcomes.

## Metrics per year (exact)

Over Y_k test rows (MAIN universe, `t_fill` in year):

- `n`, per-coin `n_c`; weights `w_c(k)` (all 5, XRP highlighted).
- `S_u = sum(y1.0)`; `S_w = sum(w_c * y1.0)`; `ratio = S_w / S_u`
  (reported; rule uses the literal inequality below, robust to S_u <= 0).
- Win rate = fraction of rows with `y1.0 > 0` (identical for weighted and
  unweighted since all w_c > 0; reported once, equality asserted in tests).
- Days keyed by UTC calendar date `floor(t_fill to D)`; daily sums
  `d_u(day)`, `d_w(day)`; `worst_day` = min daily sum (each path).
- `maxDD` of the daily-sum path: days sorted ascending, `cum = cumsum(daily)`,
  `peak_t = max(0, cummax(cum)_t)` (starts flat at 0), `DD_t = peak_t - cum_t`,
  `maxDD = max_t DD_t (>= 0)`. Units: y-sum (return-notional); also shown in
  bps (x1e4). Weighted maxDD uses `d_w`, unweighted uses `d_u`.
- Cost context: y1.0 reported in bps (1 bps = 1e-4) where per-trade means are
  shown; round-trip cost ~4-8 bps.

## Decision rule (assignment literal, single variant)

PROMISING iff BOTH hold:
(a) weighted maxDD <= unweighted maxDD in >= 4 of 5 years, AND
(b) S_w >= 0.95 * S_u in >= 4 of 5 years.
Otherwise NOT PROMISING. One-line verdict in REPORT.md. (The generic
same-sign/LOYO default does not apply: there is one signed comparison pair
per year, not an IC sign; no LOYO is computed, and no second variant exists.)

## Causality / correctness tests (tests/test_oc_coinwf.py)

- test_universe_and_years: MAIN join yields expected rows; T on 4h grid;
  f in 16..238; years disjoint, keyed by t_fill; no row with
  t_fill >= 2026-09-24.
- test_weight_formula_synthetic: hand-checked scores -> clip -> renormalise
  (incl. NaN-score -> 1.0 and mean(w)==1, fallback when mean_score <= 0).
- test_history_embargo: for each k, recompute H_k from the parquet and assert
  every training row has t_fill < A_k - 7d and > 2020-08-01, no test row of
  Y_k is in H_k, and stored weights equal a from-scratch recomputation.
- test_no_peek: dropping/shifting all y1.0 at/after A_k - 7d leaves w(k)
  unchanged (truncate-and-recompute on one anchor).
- test_winrate_equality: weighted and unweighted trade win rates identical
  (all weights > 0).

## Deliverables

research/tournament/oc_coinwf/: PLAN.md (this file), compute_coinwf.py
(history scores -> weights -> per-year metrics -> results.json),
results.json, REPORT.md (tables + one-line verdict).
tests/test_oc_coinwf.py. No commits, no edits outside the two allowed paths.
Any post-hoc change logged in REPORT.md.
