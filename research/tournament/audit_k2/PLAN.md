# audit_k2 — PLAN (pre-registered BEFORE any outcome, 2026-10-07)

Blind replication of the Kronos K2 dip tilt on G2 (engine part; features given).
Reads ONLY: docs/opencode/OPENCODE_W_oc_kronoshidden.md,
research/tournament/kronos/PLAN.md, research/tournament/oc_kronoshidden/PLAN.md
plus AGENTS.md / OPENCODE_VF_COMMON.md / OPENCODE_W_COMMON_20261007.md.
GIVEN data (not re-run): research/tournament/oc_kronoshidden/kronos_features_4shift.parquet.

## Variants (ONLY these two, fixed)
- REF = G2 unchanged: v421 RUNS rule inv k=1.0 kd=1.7 bear=True G=2.0
  (strat R2B1D17BFG2). Loaded bit-exact from v421/v421_runs.pkl for scoring;
  engine re-run must reproduce 5.41 %/mo / max-yearly-DD 16.91 / full-path DD 16.82 else STOP.
- K2 = REF + Kronos tilt: risk = -low1. Per anchor A in
  (2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24, 2025-09-24) fit on TRAINING
  rows = majors rows of research/tournament/harness.py load() with
  t_exit < A - 7d joined to shift-0 low1 on (sym, T):
  direction = sign of Spearman(risk, y_dep); edges q20/q80 of risk
  (linear interpolation, default pandas quantile). Multiplier 1.25 in the
  favourable outer quintile, 0.75 in the unfavourable outer quintile, 1 else;
  missing feature -> 1. The anchor-A fit applies to all four shifts in year A
  [A, A+365d), each shift using its own (sym, T) rows. No other parameter.

## Engine (fixed, 4-phase, heavy_slot)
- Mechanism: copy of v414/v414_dvol_tilt.py per-(coin, holding bar) dip-size
  multiplier on top of corr-aware dip sizes (rule inv, kd 1.7, bear halving of
  positive books, sleeve_gross_cap G=2.0, budget 0.26*1.0*1.7); budget unchanged.
  Holding-bar open H = idx[i]+4h; tilt lookup (sym=cols[a], shift=s, T=H).
  Books/bear/minutes/prep/pipe_setup identical to v421 (pipe v321, agents ON,
  win_start=5, trade-through only, nothing in first 5 min, stop-first in engine).
- Period: 2021-09-24 .. 2026-09-23 on all 4 shifts (dev4 + most-recent year
  in one run; live0=DEV0+sh, live1=Y1+sh with Y1=2026-09-23).
- Costs (gate): maker 0.0002, taker 0.00055, longs pay 0.0001/8h settlement
  (00/08/16 UTC inside holding bar), shorts 0.

## Metrics (fixed)
- Per-year 4-phase reset %/mo + yearly DD via reset_metric.year_reset;
  dev4 = geometric mean of the 4 dev years; Y4 = most-recent year
  (2025-09-24..2026-09-23) scored ONCE; 5y = geometric mean of all 5 years;
  full-path DD = v388.mix continuous from 2021-09-24 (max of marked/close).
- replication.json (Part A, saved BEFORE opening any oc_kronoshidden output):
  per-anchor {direction, q20, q80, n_train, spearman_rho}, per-year {R, DD}
  for REF and K2, dev4 {R,W,DD,losing}, Y4 {R,DD}, 5y {R,W,DD,losing},
  full_path_dd, code/mapping notes, run hashes.
- Comparison (Part B, only after replication.json is saved): thresholds
  R diff > 0.10 pp, DD diff > 0.5 pp, fit params relative diff > 1e-6.
  Code audit for look-ahead: (1) feature timing per shift (400 bars <= T),
  (2) training-row cut (t_exit < A-7d), (3) shift/phase mapping, (4) multiplier
  application point (sleeve_fill_size, holding-bar key). Each with a test.
  COMPARISON.md: PASS / FAIL / PASS-WITH-NOTES + 3-line Vietnamese verdict.

## Leakage checks (to state in REPORT)
- Feature timing: Kronos T is bar open, forecast uses only 400 bars closing <= T
  (taken as GIVEN; engine lookup uses H = idx+4h known at decision time).
- Label windows: harness t_exit < A-7d only.
- Fit windows: shift-0 only for fits; applied to all shifts in that year.
- Fill timing: engine win_start=5, 1m trade-through, stop-first (inherited).
- No statistic from any test year feeds any fit; most-recent-year fit uses only
  rows with t_exit < 2025-09-17.
