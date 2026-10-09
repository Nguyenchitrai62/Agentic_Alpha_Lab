# audit_d1 — PLAN (pre-registered BEFORE any outcome, 2026-10-08)

Blind replication of the downside-share dip tilt D1 on G2 (engine part; feature rebuilt from raw bars).
Reads ONLY: docs/opencode/OPENCODE_W_audit_d1.md,
docs/opencode/OPENCODE_W_COMMON_20261007.md, AGENTS.md, OPENCODE_VF_COMMON.md,
research/tournament/oc_downshare/PLAN.md (frozen spec) plus INPUT files below.
GIVEN data (not re-run at full scale beyond the D1 rebuild): research/tournament/oc_kronoshidden/
bars_4h_4shift.parquet (for the D1 rebuild + the 200-row truncation check).
Do NOT read oc_downshare REPORT.md, results.json, fits.json or its scripts
(build_downshare.py, make_fits.py, tilt_rule.py, compute_replica_gate.py,
run_engine.py, analyze.py) until replication.json is saved.
Format modelled on research/tournament/audit_c2 (its PLAN.md/REPORT.md only, not its numbers).

## Variants (ONLY these two, fixed)
- REF = G2 unchanged: v421 RUNS rule inv k=1.0 kd=1.7 bear=True G=2.0
  (strat R2B1D17BFG2). Loaded bit-exact from v421/v421_runs.pkl for scoring;
  engine re-run must reproduce 5.41 %/mo / max-yearly-DD 16.91 / full-path DD
  16.82 else STOP.
- D1 = REF + downside-share tilt: risk = trailing-6d downside-RV share
  (definition below, exactly as oc_downshare PLAN.md). Per anchor A in
  (2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24, 2025-09-24) fit on TRAINING
  rows = majors rows of research/tournament/harness.py load() with
  t_exit < A - 7d joined to shift-0 risk_D1 on (sym, T):
  direction = sign of Spearman(risk, y_dep) (+1 if rho > 0 else -1);
  edges q20/q80 of risk (linear interpolation, default pandas quantile).
  Multiplier 1.25 in the favourable outer quintile, 0.75 in the unfavourable
  outer quintile, 1 else; missing/NaN feature -> 1. The anchor-A fit applies
  to all four shifts in year A [A, A+365d), each shift using its own (sym, T)
  rows. No other parameter. hi/lo fixed at 1.25/0.75. No D2 variant here.

## D1 feature (frozen, causal, existing 4h closes only — no new data)
- Source (read-only): `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet`
  (5 majors x shifts 0..3 4h OHLCV; per (sym, shift) series sorted by T = bar open).
- Close-to-close log returns: r[i] = log(C[i]) - log(C[i-1)], r[0] = NaN (float64).
- Window helper (pure, unit-tested): share(rs) = sum(min(r,0)^2) / sum(r^2)
  over a finite window rs; NaN if any element non-finite, if len == 0,
  or if total <= 0 / non-finite. share in [0,1] by construction
  (0 = all upside, 1 = all downside, 0.5 ~ symmetric).
- D1 (6d share): at bar index E (bar open T[E]), window = r[E-36 .. E-1]
  (36 returns = 6d x 6 bars/day, all of bars closing <= T[E]); requires E >= 37
  and all 36 finite, else NaN -> causal by construction (only closes of bars
  closing <= T).
- Output: `research/tournament/audit_d1/downshare_D1_4shift.parquet`
  (sym, shift, T, risk_D1). T range = all T with E >= 37 (superset fine;
  engine join is missing -> 1).
- No statistic from any test year feeds the definition (returns <= T only;
  no thresholds/weights fit here).

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
- Feature comparison: our risk_D1 vs the frozen oc_downshare parquet
  (compared ONLY after replication.json is saved): max abs diff + coverage;
  threshold max abs diff <= 1e-9 (float64 pure rebuild).
- Multiplier-vector check: same-input determinism check (re-run assign on
  2000 sampled (sym, shift, H) keys twice -> identical) plus the post-unblind
  vector comparison in COMPARISON.md.
- replication.json (Part A, saved BEFORE opening any oc_downshare output):
  per-anchor {direction, q20, q80, n_train, n_joined, spearman_rho},
  per-year {R, DD} for REF and D1, dev4 {R,W,DD,losing}, Y4 {R,DD},
  5y {R,W,DD,losing}, full_path_dd, feature build notes, run hashes.
- Comparison (Part B, only after replication.json is saved): thresholds
  R diff > 0.10 pp, DD diff > 0.5 pp, fit params relative diff > 1e-6,
  feature max abs diff > 1e-9.
  Code audit for look-ahead: (1) feature timing per shift (36 closes <= T;
  200-row recompute from bars truncated at T must match), (2) training-row
  cut (t_exit < A-7d), (3) shift/phase mapping, (4) multiplier application
  point (sleeve_fill_size, holding-bar key). Each with a test. COMPARISON.md:
  PASS / PASS-WITH-NOTES / FAIL + 3-line Vietnamese verdict.

## Leakage checks (to state in REPORT)
- Feature timing: D1 share at bar open T uses ONLY the 36 closes of bars
  closing <= T on that shift's grid (truncation recompute on 200 random rows).
- Label windows: harness t_exit < A-7d only.
- Fit windows: shift-0 join only; 2025 fit uses rows t_exit < 2025-09-17; no
  test-year statistic feeds any fit.
- Fill timing: engine win_start=5, 1m trade-through, stop-first (inherited).
- No statistic from any test year feeds any fit; most-recent-year fit uses only
  rows with t_exit < 2025-09-17.

## Post-hoc log
- (empty; any change after an outcome is logged here with date + reason; the
  original row stays and the change is a disclosed extra row.)
