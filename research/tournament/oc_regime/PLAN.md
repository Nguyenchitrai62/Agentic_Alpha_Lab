# oc_regime PLAN (pre-registered BEFORE any outcome is inspected)

Question: the BOT dip sleeve earned strongly in the 2024 anchor year but little in
2021, 2022 and 2025-26. Which SLOW market regimes known at the bar open separate
good from bad dip periods, consistently across years?

## Part A — 8 slow daily regime variables (fixed here)

Source: research/tournament/data/hourly.parquet only (columns t, open, high, low,
close, sym; 35 coins, hourly bars). Daily close C(s,D) = close of the 23:00 UTC
hourly bar of calendar day D-1 (bar covering 23:00-00:00), i.e. the last bar with
t < D 00:00 UTC. Daily log return r(s,D) = log C(s,D) / C(s,D-1).
A regime value labelled day D uses ONLY hourly bars with t < D 00:00 UTC.

1. trend30 — 30d BTC log trend: log(C_BTC(D-1 deleted) / C_BTC(D-31)), C = daily close.
   Positive = BTC up over the last 30 days.
2. trend90 — 90d BTC log trend: log(C_BTC(D-1) / C_BTC(D-91)).
3. volratio — 30d BTC realized vol vs 1y median: std(r_BTC, prior 30d) /
   median(trailing 30d stds over the prior 365d, all ending <= D-1). >1 = vol elevated.
4. corr30 — 30d mean cross-coin correlation: mean upper-triangle Pearson correlation
   of daily log returns across the 35 coins over the prior 30d (pairwise-complete days;
   NaN if <30 complete days -> regime row NaN).
5. stress30 — 30d count of >3-sigma down-days in the equal-weight index: index daily
   return R(D) = mean_s r(s,D); sigma = std(R) over the 365d ending at D-31 (strictly
   before the 30d window, causal); count of days in prior 30d with R < -3*sigma.
6. breadth50 — fraction of coins with C(s,D-1) above their 50d SMA (mean of daily
   closes over prior 50d ending D-1). 0..1, high = broad uptrend.
7. dd90 — BTC position vs 90d high: log(C_BTC(D-1) / max C_BTC over prior 90d ending
   D-1). 0 at highs, negative in drawdown.
8. vollevel — 30d mean absolute index move: mean |R| over prior 30d (level of chop).

Warm-up: regime rows start 2021-01-01 (needs 365d+90d history from 2020-08-01); earlier
days are NaN and dropped. All 8 recomputed from the truncated hourly panel in the
causality test.

## Part B — monthly dip edge vs month-start regime (fixed here)

Fills: research/diagnostics/phase_agents/fills_U.parquet (T < 2025-09-24) PLUS
research/tournament/ext/fills_U_ext.parquet for T in [2025-09-24, 2026-09-23]
(same columns; T = t_fill - f minutes; verified same schema at start).
Universe MAIN = sym in {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT} and x1
(rung depth k) in {2.5, 3.0, 3.5, 4.0, 5.0} (R2). POOLED = all 35 coins, same 5 depths.
Outcome = y1.0 (net return per fill at TP 1.0 sigma, unit rung size). No other outcome
is used for selection.

Anchor years (5): Y = [A, A+365d) for A in {2021-09-24, ..., 2025-09-24} (UTC).
Months: calendar month of T (YYYY-MM). Monthly edge = mean y1.0 of fills in that month
(fill-level mean), n = fill count. Regime at month start = daily regime row for D =
first day of the month 00:00 UTC (uses data strictly before the month).
Spearman: per variable, per anchor year, Spearman rho of (month-start regime,
monthly edge) over the ~12 months of that year (reported with n; NaN months dropped;
rho NaN if <3 valid months — counts as a fail for consistency, never imputed).
LOYO gate: for held-out year h (5 folds), training = months of the other 4 years;
threshold = median of the variable over training months; good side = side
(above-or-equal vs below threshold) with the HIGHER training mean of monthly edges
(simple mean of the monthly means); gate = in held-out year, keep only fills whose
month-start regime is on the good side. Report per held-out year: mean edge WITHOUT
gate (mean y1.0 over all held-out fills) and WITH gate (mean y1.0 over kept fills;
NaN + kept_months=0/kept_fills=0 if fewer than 2 kept months), plus kept-month share.
Helps = with > without (strictly greater, fill-mean bps).
CONSISTENT (per variable, MAIN and POOLED separately): Spearman sign identical in
>= 4 of 5 years AND LOYO gate helps in >= 4 of 5 held-out years. NaN rho fails the
sign count; NaN gated mean fails the help count.

Cost context: round-trip cost ~4-8 bps; edges reported in bps (1 bps = 1e-4).

## Causality / alignment tests (tests/test_oc_regime.py)

- test_regime_causal_truncate: 20 random days (seed 7) in 2022-01..2026-08; recompute
  regimes from hourly truncated to t < day and assert equal to the full-panel row.
- test_regime_no_future_hour: no regime row for D uses any bar with t >= D.
- test_month_regime_precedes_fills: every fill's month-start regime day <= fill T.
- test_ext_schema_and_no_overlap: ext has same columns; dev/ext split at 2025-09-24
  by T has no overlap and covers 2021-09-24..2026-09-23.

## Deliverables

research/tournament/oc_regime/: PLAN.md (this file), regime.py, analyze.py,
results.json, REPORT.md. No tuning on results; any post-hoc change logged in REPORT.md.
