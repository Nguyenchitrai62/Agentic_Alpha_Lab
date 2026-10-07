# oc_agentskip — PLAN (pre-registered BEFORE any outcome is computed)

Idea #57 (NEW): a SKIP action for the R2 dip size agent.

## Hypothesis

The deployed size rule S1 always takes every traded rung (0.5 / 1.0 / 1.5)
even when both cross-fitted HGB value models agree the rung's expected net
return at size 1.0 is a loss larger than ~round-trip cost. Adding a fixed
SKIP gate (size 0 when BOTH halves predict y1.0 < -0.002, otherwise S1
unchanged) removes negative-expectation rungs, so the rung-level realised
sum is not lower than the no-skip base in most walk-forward years without
worsening maxDD. Null (stated upfront): the gated rungs' realised mean is
~zero or positive (models miscalibrated in the left tail), so skipping
reduces or barely changes the sum.

## Exact causal definitions (frozen)

- Anchors A_k = 2021-09-24 + k*365 d, k=0..4 (2021-09-24, 2022-09-24,
  2023-09-24, 2024-09-24, 2025-09-24). Test year Y(A_k) = [A_k, A_k+365 d).
  Market data used is strictly < 2026-09-24 00:00 UTC. All five years are
  research data; any winner still needs prospective validation.
- Fills: rows of research/tournament/ext/fills_U_ext.parquet (72,130 rows,
  verbatim v293.fills_of replica, rungs U=2.0..5.0, 35-coin universe).
  Columns j (standard-grid 4h bar index, START=2020-08-01 00:00 UTC), r, f,
  t_fill, t_exit, y0.5/y1.0/y1.5 (exact net returns from v293.outcomes,
  engine_user close5+backstop, maker 0.0002 / taker 0.00055 / adverse long
  funding), x0..x6 (sp30, k, volreg, trend, btc sp30, dd24, hour), sym.
  Training uses the FULL fills_U_ext universe (majors + alts), exactly as R2.
- Features: X = x0..x6 exactly as stored (7 floats). SAME as V0 in
  research/tournament/oc_rlbear/build_v0_v2.py. No new feature.
- Labels/fits (IDENTICAL to build_tables.py / oc_rlbear V0, originals never
  edited): Y clipped to [-0.10, 0.08]; y1 = Y[:,1.0]; half = j%2;
  keep_k = (t_exit < A_k - 7 days) (v293.EMBARGO, >= horizon);
  mu_k = mean of y1[keep_k]; size models = v296.hgb(10*k+h) fit on y1 for
  h in {0,1}; TP models = v296.hgb(10*k+h+3*c) fit on Y[:,c] for c in
  {0,1,2} (HGB max_depth=3, lr=0.05, max_iter=200, min_samples_leaf=200,
  l2=1.0). 5 anchors x 8 fits = 40 HGB fits, single process.
  Per-bar model k(T) = max{q : T >= A_q}.
- Rules:
  * S1 base (verbatim build_tables.py::rules): size 1.5 if pa,pb > 2*mu;
    0.5 if pa,pb < 0 (and not up); else 1.0 (NaN pa -> 1.0). pa/pb are the
    two halves' predictions of y1.0 at the table row's bar-open state.
  * SKIP (fixed, ONE variant): if pa < -0.002 AND pb < -0.002 then
    size_skip = 0.0, else size_skip = size_S1. TP rule unchanged (both
    halves agree on same non-base action with gain > 0.001, else 1.0).
    Threshold -0.002 is fixed upfront (~round-trip cost scale); no tuning.
- Table rows (phase s=0 ONLY, bar-open form EXACTLY as build_tables.py /
  oc_rlbear V0): for each major sym and each standard-grid holding bar T
  with A_0=2021-09-24 <= T <= 2026-09-23 12:00 and finite sig[j]:
  kk=j*240; base=[A.sp30(kk), k, A.volreg[j], A.trend[j], btc.sp30(kk),
  log(C[kk]/hmax24[kk])/sig[j], T.hour]; one row per k in U, then filtered
  to traded R2=(2.5,3.0,3.5,4.0,5.0) with rung=0..4. Majors 1m loaded ONE
  coin at a time (BTC kept for btc.sp30; each other major loaded,
  featurised, predicted, released). Output schema (T, sym, rung, size, tp)
  for base (V0 path) and skip (same + gate). TP identical in both files.
  Deliverable: skip_table_s0.parquet (+ base_table_s0.parquet for audit).
- V0 check (gate): base must reproduce v376/tables_hidden/r2_table_s0.parquet
  (or equivalently oc_rlbear/v0_table_s0.parquet) on the overlap (inner join
  on T,sym,rung). Report size_match and tp_match. If either < 99.9%, STOP
  and report why (no screening verdict).

## Screening (rung level, phase 0; frozen before computing, exactly like oc_rlbear)

- Universe: fills_U_ext rows with sym in majors, x1 (=k) in R2 traded rungs
  2.5..5.0, and holding-bar open T(j)=START+4h*j inside Y(A_k) for k=0..4.
  (T from j, not t_fill, so the year assignment is bar-open causal.)
- Realised outcome per fill under table V in {base,skip}: look up
  (T,sym,rung) (rung = index of k in R2) in that table;
  outcome = size_V * y_{tp_V}, where y_{tp} is the fill's y0.5 / y1.0 / y1.5
  per the TABLE's tp choice (TP identical base vs skip, so only size 0
  differs). Fills with no table row (non-finite sig bars) are dropped and
  counted.
- Daily sums by exit date: group outcomes by t_exit date (UTC). Per year and
  per V: sum (total), fill win rate = mean(outcome>0), day win rate =
  mean(daily_sum>0) over exit days, worst day = min(daily_sum),
  maxDD = max drawdown of the cumulative daily-sum path starting at 0
  (peak-minus-trough absolute units, identical code for base/skip).
- Skip diagnostics per year: skipped-rung share = fraction of kept fills
  with size_skip==0; skipped rungs' realised mean = mean(outcome_base) over
  skipped fills (what the base would have earned on them); plus size value
  counts per V.
- Decision rule (frozen, from assignment): PROMISING only if
  (i) sum(skip) >= sum(base) (not lower) in >= 4 of 5 anchor years AND
  (ii) maxDD(skip) <= maxDD(base) (not worse) in >= 4 of 5 years.
  Otherwise NOT PROMISING. One-line verdict in REPORT.md. No
  leave-one-year-out beyond this; no engine replay in this task.

## Leakage checklist (to be confirmed in REPORT)

1. Table state at bar open uses minutes <= 240*j only (sp30/volreg/trend/
   sig/hmax from Asset, same as build_tables.py); pa/pb are predictions
   from models fit on t_exit < A-7d only.
2. Skip gate uses ONLY pa/pb at the decision bar (no fill-minute or future
   data, no test-year statistic).
3. Fits/mu/thresholds use t_exit < A-7d only; no test-year row in any fit.
4. Seeds/clip/rules fixed from build_tables.py; threshold -0.002 fixed
   upfront; no tuning on outcomes.
5. No statistic from any test year feeds any choice; base/skip share
   fits/mu/TP.

## Deliverables in this folder

- PLAN.md (this file, written before any outcome).
- build_skip.py (V0 code path + skip gate, never edits originals).
- screen_skip.py (screening exactly as above).
- skip_table_s0.parquet (skip, s0, schema T/sym/rung/size/tp).
- base_table_s0.parquet (V0-path audit copy).
- results.json (V0 match rates + per-year base/skip stats + skip diagnostics).
- REPORT.md (tables + one-line verdict).
- RAM < 3 GB, one process, no commits, no edits outside this folder
  (+ tests/test_oc_agentskip.py).
