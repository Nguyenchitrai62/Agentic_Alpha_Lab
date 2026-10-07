# oc_rlbear — PLAN (pre-registered BEFORE any outcome is computed)

Hypothesis (V2-lite of oc_rlb1plan/PLAN.md): the deployed R2 dip tables were
trained in a pre-bear environment and are therefore bear-blind. Adding ONE
causal bear-regime state feature to the SAME R2 fits (size S1 + TP X4,
v296 HGB hyperparams, j%2 cross-fit halves, same seeds, same clip/mu/embargo)
lets the two halves down-weight / re-price dip rungs in bear bars, improving
the realised rung-level outcome vs the identical no-bear refit (V0) in most
walk-forward years. Null (stated upfront, per rlb1plan §a): per-unit rung
returns y are invariant to the book/bear environment, so a retrain may learn
~identical tables and show no gain; a gain requires the bear flag to carry
incremental signal about y conditional on x0..x6.

## Exact causal definitions (frozen)

- Anchors A_k = 2021-09-24 + k*365 d, k=0..4 (2021-09-24, 2022-09-24,
  2023-09-24, 2024-09-24, 2025-09-24). Test year Y(A_k) = [A_k, A_k+365 d).
  Market data used is strictly < 2026-09-24 00:00 UTC.
- Fills: rows of research/tournament/ext/fills_U_ext.parquet (72,130 rows,
  built by the verbatim v293.fills_of replica, rungs U=2.0..5.0, 35-coin
  universe). Columns j (standard-grid 4h bar index, START=2020-08-01 00:00
  UTC), r (index into U), f (fill minute), t_fill, t_exit, y0.5/y1.0/y1.5
  (exact net returns from v293.outcomes, engine_user close5+backstop,
  maker 0.0002 / taker 0.00055 / adverse long funding), x0..x6
  (sp30, k, volreg, trend, btc sp30, dd24, hour at minute f-1), sym.
  Training uses the FULL fills_U_ext universe (majors + alts), exactly as R2.
- Bear flag b(T) in {0,1} (v410 definition, causal at the bar open):
  b = 1 iff BTC 4h OPEN[T] < mean(BTC 4h opens over the last 1200 bars ending
  at T, min_periods 600), else 0. BTC 4h opens are the standard-grid opens
  O[j]=O0 from stored 1m via v293.Asset("BTCUSDT") (START=2020-08-01,
  END=2026-09-24; O[j] = 1m open at minute 240*j). Rolling mean is a trailing
  pandas rolling(1200, min_periods=600).mean() INCLUDING the current open
  (identical to v410: `btc < btc.rolling(1200, min_periods=600).mean()`).
  Early bars with <600 opens give NaN mean -> comparison False -> b=0.
  For a training fill, b = b[j] at the fill's holding-bar open (NOT at the
  fill minute). For a table row at bar open T, b = b[j(T)] on the same grid.
  No intrabar or future data enters b. Source documented here (stored 1m,
  not bar_open_ext) because bar_open_ext carries no BTC open level series.
- Features:
  * V0 (null control): X = x0..x6 exactly as stored (7 floats).
  * V2 (bear-aware lite): X = [x0..x6, b] (8 floats; b as 0.0/1.0). No B1
    n feature, no sample weighting (that is full-V1/V2 in rlb1plan; this
    task is V2-lite = bear only).
- Labels/fits (IDENTICAL to build_tables.py, copied code, original never
  edited): Y clipped to [-0.10, 0.08]; y1 = Y[:,1.0]; half = j%2;
  keep_k = (t_exit < A_k - 7 days) (v293.EMBARGO, >= horizon); mu_k = mean of
  y1[keep_k]; size models = v296.hgb(10*k+h) fit on y1 for h in {0,1};
  TP models = v296.hgb(10*k+h+3*c) fit on Y[:,c] for c in {0,1,2}
  (HGB max_depth=3, lr=0.05, max_iter=200, min_samples_leaf=200, l2=1.0).
  5 anchors x 8 fits = 40 HGB fits, single process. Per-bar model
  k(T) = max{q : T >= A_q}.
- Rules (verbatim build_tables.py::rules, R2 genome): size 1.5 if pa,pb >
  2*mu; 0.5 if pa,pb < 0 (and not up); else 1.0 (NaN pa -> 1.0). TP 0.5/1.5
  iff both halves agree on the same non-base action with gain > 0.001,
  else 1.0.
- Table rows (phase s=0 ONLY, bar-open form EXACTLY as build_tables.py):
  for each major sym and each standard-grid holding bar T with
  A_0=2021-09-24 <= T <= 2026-09-23 12:00 and finite sig[j]:
  kk=j*240; base=[A.sp30(kk), k, A.volreg[j], A.trend[j], btc.sp30(kk),
  log(C[kk]/hmax24[kk])/sig[j], T.hour] (+b[j] for V2); one row per k in
  U, then filtered to traded R2=(2.5,3.0,3.5,4.0,5.0) with rung=0..4.
  Majors 1m loaded ONE coin at a time (BTC kept for btc.sp30 + bear; each
  other major loaded, featurised, predicted, released). Output schema
  (T, sym, rung, size, tp), same as v376/tables_hidden/r2_table_s0.parquet.
- V0 check (gate): V0 must reproduce v376/tables_hidden/r2_table_s0.parquet
  on the overlap (inner join on T,sym,rung). Report size_match and tp_match
  rates. If either < 99.9%, STOP and report why (no screening verdict).

## Screening (rung level, phase 0; frozen before computing)

- Universe: fills_U_ext rows with sym in majors, x1 (=k) in R2 traded rungs
  2.5..5.0, and holding-bar open T(j)=START+4h*j inside Y(A_k) for k=0..4.
  (T from j, not t_fill, so the year assignment is bar-open causal.)
- Realised outcome per fill under table V in {V0,V2}: look up (T,sym,rung)
  (rung = index of k in R2) in that table; outcome = size_V * y_{tp_V},
  where y_{tp} is the fill's y0.5 / y1.0 / y1.5 per the TABLE's tp choice.
  Fills with no table row (non-finite sig bars) are dropped and counted.
- Daily sums by exit date: group outcomes by t_exit date (UTC). Per year and
  per V: sum (total), fill win rate = mean(outcome>0), day win rate =
  mean(daily_sum>0) over non-zero days, worst day = min(daily_sum),
  maxDD = max drawdown of the cumulative daily-sum path starting at 0
  (peak-minus-trough / (1+peak) convention documented in script; reported
  for both V identically so the comparison is exact).
- Divergence: fraction of fills where V2 size != V0 size and where V2 tp !=
  V0 tp, split by bear (b=1) vs non-bear (b=0) bars; plus size/tp value
  counts per V.
- Decision rule (assignment default, frozen): PROMISING only if
  (i) sum(V2) > sum(V0) in >= 4 of 5 anchor years AND (ii) maxDD(V2) <=
  maxDD(V0) (not worse) in >= 4 of 5 years. Otherwise NOT PROMISING.
  One-line verdict in REPORT.md. No leave-one-year-out beyond this; no
  engine replay in this task.

## Leakage checklist (to be confirmed in REPORT)

1. b uses opens up to and including the decision bar only.
2. Fits/mu/thresholds use t_exit < A-7d only; no test-year row in any fit.
3. Table state at bar open uses minutes <= 240*j only (sp30/volreg/trend/
   sig/hmax from Asset, same as build_tables.py).
4. Seeds/clip/rules fixed from build_tables.py; no tuning on outcomes.
5. No statistic from any test year feeds any choice; V0/V2 share mu/rules.

## Deliverables in this folder

- PLAN.md (this file, written before any outcome).
- build_v0_v2.py (copied logic, never imports-edits originals in place).
- screen_rung.py (screening exactly as above).
- r2bear_table_s0.parquet (V2, s0, same schema as original).
- results.json (V0 match rates + per-year V0/V2 stats + divergence).
- REPORT.md (tables + one-line verdict).
- RAM < 3 GB, one process, no commits, no edits outside this folder.
