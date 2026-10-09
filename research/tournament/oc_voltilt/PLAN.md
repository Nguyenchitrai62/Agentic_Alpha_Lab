# oc_voltilt — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_voltilt.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md read). Write ONLY `research/tournament/oc_voltilt/`
+ `tests/test_oc_voltilt.py`. No GPU, no new packages (no `arch` -> GARCH MLE in
numpy/scipy, scipy is in .venv). CPU-only. Heartbeat print every 600 s in long
jobs. Scratch only under `research/tournament/oc_voltilt/tmp/`.
Engine via heavy_slot (RAM is tight: one engine job at a time).

## Why (from assignment)

Kronos K2, Chronos C2, Toto T3 (different pretraining) all give the same tilt
direction (+1: bigger rungs when the forecast lower quantile is far below the
price) and significant timing on 2023-2026 but none in 2021-2022. Kronos
forecasts |move| (vol1 IC 0.18) but not sign. Hypothesis: the shared content is
plain short-term volatility timing. If a trivial causal vol forecast with the
IDENTICAL rule gives the same gain, the FMs are unnecessary.

## Frozen inputs (read-only, never edited)

- `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet` (5 majors x shifts
  0..3 4h OHLCV from raw Binance USD-M 1m; 1m ends 2026-09-23 23:59; T range
  2020-08-01 .. 2026-09-23 20:00).
- `research/tournament/oc_kronoshidden/kronos_features_4shift.parquet` (K2 low1;
  reference only) + `fits.json` (K2 per-anchor fits; reference only).
- `research/tournament/oc_chronos/chronos_features_4shift.parquet` (ch_q10) +
  `fits.json` (C2 fits; reference + multiplier-agreement leg).
- `research/tournament/oc_toto/toto_features_4shift.parquet` (f_q10) + `fits.json`
  (T3 fits; reference only).
- `research/tournament/harness.py` (per-anchor fits).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` +
  `v421_result.json` row R2B1D17BFG2 (G2 baseline).
- `research/tournament/oc_k2placebo/tmp/ledger.npz` + `bt_all.npy` (D0+B1 replica
  ledger for the placebo leg, read-only reuse; gate n == 22312, base sum5y ==
  7.718304 +- 0.002).
- `research/tournament/oc_chronos/run_engine.py` + `tilt_rule.py` (mechanism +
  `assign_mult` copied verbatim; only the feature lookup changes).

## Part A — vol features (fixed; CPU-only)

Per (sym, shift) series sorted by T (bar open). Let C = close, O = open.
Close-to-close log returns: r[i] = log(C[i]) - log(C[i-1)] (r[0] = NaN).
sigma360 (EXACT replica of oc_chronos/run_chronos_4shift.py): lo = log(O),
sig[E] = rolling(360).std(ddof=1) of diff(lo) at index E (pandas default;
includes O[E], known at bar open T[E] -> causal).

- RV6: RV6[E] = std(ddof=1) of r[E-6 .. E-1] (6 close-to-close returns of bars
  closing <= T[E]; requires E >= 7 and all 6 finite, else NaN -> causal by
  construction: only closes of bars closing <= T).
  risk_RV6[E] = RV6[E] / sig[E] (NaN if sig missing/nonpositive/nonfinite).
- GARCH(1,1): zero-mean normal model var[t] = omega + alpha*r[t-1]^2 +
  beta*var[t-1] on the close-to-close r of the SHIFT-0 grid.
  Fit per (anchor A, sym): sample = shift-0 bars of that sym with bar close
  time <= A - 7d (i.e. T + 4h <= A - 7d), r finite (first r dropped). MLE via
  scipy.optimize.minimize (L-BFGS-B) on unconstrained transform
  (log-omega, logit-alpha, logit-beta with alpha+beta<1 enforced by penalty);
  init var = sample variance; init (alpha,beta) = (0.08,0.88). 25 fits
  (5 anchors x 5 syms), recorded in `garch_params.json` (omega/alpha/beta +
  n_obs + negloglik). No `arch` package, no outcome data: fit sample uses only
  bars (prices), never harness labels or engine results.
  Filter (causal): for year y (T in [A_y, A_y+365d) on that shift's grid) use
  params of anchor A_y (same sym). Iterate from series start with
  var[0] = unconditional omega/(1-alpha-beta) (fallback: sample variance of
  the fit sample), updating with observed r only (r[E-1] known at T[E]);
  one-step forecast var_T[E] -> sigma_GARCH[E] = sqrt(var_T[E]).
  risk_GARCH[E] = sigma_GARCH[E] / sig[E] (NaN if sig missing/nonpositive or
  E < 360 burn-in, else always finite-positive by construction).
- Output: `vol_features_4shift.parquet` (sym, shift, T, sigma, risk_RV6,
  risk_GARCH). T range: all T with sig available (E >= 360), superset of the
  Kronos T range at the early end (shorter context), same end 2026-09-23 20:00
  and same grids. Engine join is missing -> 1, so extra early rows are inert.
- Causality: truncation test (recompute features from bars truncated at a cut
  date -> identical on the kept prefix; GARCH params refit on truncated sample
  are NOT required to match — only the filter with FROZEN params must match —
  so the test truncates bars but reuses frozen params; plus a fit-window test
  that fit samples exclude bars closing after A - 7d).

## Part B — tilt (fixed; IDENTICAL rule to K2/C2/T3 except the risk)

- V_RV6: risk = risk_RV6; V_GARCH: risk = risk_GARCH. Per-anchor fit on harness
  training rows EXACTLY like oc_chronos/make_fits.py: majors rows of
  harness.load() with t_exit < A - 7d AND shift-0 feature present (join on
  (sym, T)): direction = sign of Spearman(risk, y_dep) (+1 if rho > 0 else -1),
  edges q20/q80 of risk. Mult hi = 1.25 favourable outer quintile /
  lo = 0.75 unfavourable / 1 else; missing/NaN risk -> 1. Fits of anchor A
  applied to all four shifts in year A. Most-recent-year fits use all harness
  rows with t_exit < 2025-09-17. Output `fits.json` with `V_RV6` and `V_GARCH`
  sections (direction/q20/q80/rho/n). Exactly TWO variants, no ensemble.
- Engine: exact copy of oc_chronos/run_engine.py (= v414 pipe v321, corr-aware
  inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0,
  win_start=5, gate costs inside the engine). Rows (ONLY these three):
  REF = G2 unchanged; V_RV6; V_GARCH.
- Stages: stage dev runs [DEV0=2021-09-24, DEV1=2025-09-24) for all three rows
  (REF first; must reproduce v421 G2 years 0..3 R/DD (2.588/10.86, 3.282/16.91,
  6.045/15.81, 10.677/8.27) AND 5y 5.410 / full-path DD 16.82 to the digit,
  else STOP). Stage last runs [DEV0, Y1=2026-09-23) for all three rows ONCE
  (every Y4 number labelled scored-once). Dev4 is FULLY CLEAN here (no
  pretraining) — still compare/choose ONLY on dev4. No re-runs after outcomes;
  any change becomes a disclosed extra row.

## Metrics / gates (fixed)

- Gate costs: maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts 0. Limits
  fill only on 1m trade-through, nothing in the first 5 min after a 4h close
  (win_start=5); stop-first in shared 1m bar (engine handles).
- Per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4 geo mean,
  W (worst-year R), max yearly DD, losing count; 5y geo mean; full-path DD via
  `v388.mix` equal-1/4 mix from 2021-09-24; pooled book/rung/all win rates +
  fills/year + sized mean multiplier (same collection as oc_chronos).
- Robust pick among REF / V_RV6 / V_GARCH on dev4 ONLY: DD <= 20, no losing dev
  year; prefer dev4 mean >= 5 %/mo, then highest dev4 WORST-year monthly return,
  ties -> higher mean.
- Timing placebo per year EXACTLY like oc_k2placebo (1000 within-year
  permutations of the V multipliers over decision bars, normalised by the
  actual realised mean; timing seed 20261007+y, block-42 seed 20261008+y;
  percentile = 100*(1+#{perm<=actual})/1001; significant iff >= 95) for V_RV6
  and V_GARCH (D0-replica leg, light numpy, reusing k2placebo ledger).
- Overlap analysis (no selection input): per year y (all 4 shifts pooled):
  Spearman(risk_RV6, risk_C2/K2/T3) and Spearman(risk_GARCH, risk_C2/K2/T3)
  where FM risks are -ch_q10 / -low1 / -f_q10 on the intersection of rows with
  both features present; plus the share of (sym, shift, T) decision rows in
  year y where V_RV6's multiplier (anchor-y fits) equals C2's multiplier
  (anchor-y C2 fits, missing -> 1 on both legs).
- Reference rows C2 / T3 / K2 COPIED from their REPORTs/results.json (dev R,
  last-year R, placebo pcts) as reference, NOT re-run. Expected (frozen):
  K2 dev [2.469,3.478,6.679,10.653] last 4.801 timing-Y4 97.20 block 98.70;
  C2 dev [2.711,3.460,6.250,10.721] last 4.754 timing-Y4 99.20 block 98.90;
  T3 dev [2.486,3.254,5.996,10.684] last 4.811 timing-Y4 100.00 block 100.00;
  REF dev [2.588,3.282,6.045,10.677] last 4.648.

## Leakage / checks (stated in REPORT)

- Feature timing (RV6: 6 closes <= T; GARCH filter: r[E-1] and earlier only;
  sigma: opens <= T; truncation test), label windows (harness t_exit < A - 7d
  inherited), fit windows (shift-0 only + 7d embargo; anchor-y fit for year y;
  GARCH params from bars closing before A - 7d, no labels), fill timing
  (win_start=5 + 1m trade-through + stop-first, engine). No statistic from any
  test year feeds any choice. Dev4 fully clean (no pretraining anywhere in
  this study).

## Compute plan (heavy_slot, resume-safe)

- `tilt_rule.py`: `assign_mult` + `anchor_of` copy (unit-tested).
- `build_vol_features.py`: CPU-only RV6 + sigma + GARCH MLE/filter ->
  `vol_features_4shift.parquet` + `garch_params.json` (resume-safe checkpoint
  per (sym, shift) for the filter; fits cached). Heartbeat every 600 s.
- `make_fits.py`: CPU-only harness join -> `fits.json`.
- `run_engine.py`: sequential shifts per stage, heartbeat every 600 s, caches
  `tmp/runs_dev.pkl` / `tmp/runs_last.pkl` (resume-safe). Via heavy_slot.
- `analyze.py`: CPU-only scoring -> `tmp/dev_table.json` + `tmp/last_table.json`.
- `compute_placebo.py`: CPU-only 1000-perm timing/block placebo for V_RV6 +
  V_GARCH on the D0 replica (reuses k2placebo ledger read-only).
- `compute_overlap.py`: CPU-only Spearman vs FM risks + multiplier agreement.
- Deliverables: PLAN.md (this file), tilt_rule.py, build_vol_features.py,
  make_fits.py, run_engine.py, analyze.py, compute_placebo.py,
  compute_overlap.py, vol_features_4shift.parquet, garch_params.json,
  fits.json, results.json, REPORT.md,
  tests/test_oc_voltilt.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_voltilt.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the
  original row stays and the change is a disclosed extra row.)
