# oc_d1c2 — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_d1c2.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md read). Write ONLY `research/tournament/oc_d1c2/`
+ `tests/test_oc_d1c2.py`. Scratch only under `research/tournament/oc_d1c2/tmp/`.
GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge.
Engine via `scripts/heavy_slot.py` (one engine job at a time; RAM tight). Heartbeat
print every 600 s in long jobs. Progress print every 10 minutes.

## Why (quoted from assignment, not refit)

oc_downshare D1 lifts the worst dev year (2021: 2.921 vs 2.588) but not the
post-release year (4.591 vs 4.648, -0.057); oc_chronos C2 lifts the post-release
year (+0.106 to 4.754) and 2021 less (2.711). If the two signals are different,
an ensemble may keep both. LABEL (pre-registered): both components were already
scored once on the post-release year, so every ensemble post-release number here
is a labelled diagnostic, not clean evidence (prospective paper decides).

## Variants (exactly two + reference; multipliers frozen from the two source studies)

- REF = G2 unchanged (tilt 1), reproduction row (v421 R2B1D17BFG2).
- D1 = oc_downshare D1 tilt (risk = trailing-6d downside-RV share; frozen
  `research/tournament/oc_downshare/fits.json` D1 section, hi/lo 1.25/0.75).
  COPIED row, never re-run (dev [2.921,3.604,6.541,10.191] DD
  [12.59,16.09,15.74,8.19], last 4.591/13.38, 5y 5.538, full-path 15.98).
- C2 = oc_chronos C2 tilt (risk = -ch_q10; frozen
  `research/tournament/oc_chronos/fits.json`, hi/lo 1.25/0.75). COPIED row,
  never re-run (dev [2.711,3.460,6.250,10.721] DD [11.52,15.48,15.07,8.29],
  last 4.754/12.86, 5y 5.621, full-path 15.42).
- AVG = rung multiplier = mean of the D1 and C2 multipliers:
  m_AVG = (m_D1 + m_C2) / 2. Missing leg counts as 1.0 (assign_mult returns 1.0
  on NaN, so the mean handles it automatically). Values in {0.75, 0.875, 1.0, 1.125, 1.25}.
- AGREE = 1.25 only if both legs are 1.25, 0.75 only if both legs are 0.75,
  else 1.0. Missing leg (-> 1.0) can never agree, so AGREE = 1.0 there.
- Per-leg multipliers use the FROZEN fits (anchor-y fit for year y, all four
  shifts) and hi/lo 1.25/0.75. No other variant, no threshold/weight tuning,
  no re-fit. If a feature file does not cover an anchor year: disclose and skip
  that year (never impute); none expected (both parquets cover 2020-10..2026-09-23).

## Frozen inputs (read-only, never edited, never refit)

- `research/tournament/oc_downshare/downshare_features_4shift.parquet`
  (sym, shift, T, risk_D1).
- `research/tournament/oc_chronos/chronos_features_4shift.parquet`
  (sym, shift, T, ch_q10; risk_C2 = -ch_q10).
- `research/tournament/oc_downshare/fits.json` D1 section (5 anchors).
- `research/tournament/oc_chronos/fits.json` (5 anchors).
- `research/tournament/harness.py` NOT re-run (fits inherited frozen).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` +
  `v421_result.json` row R2B1D17BFG2 (G2: dev
  [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)], Y4 (4.648/12.90),
  5y 5.410, full-path DD 16.82).
- `research/tournament/oc_k2placebo/tmp/ledger.npz` + `bt_all.npy` (replica
  ledger read-only for the timing placebo; base sum5y == 7.718304 +- 0.002, n == 22312).
- Engine mechanism = exact copy of `oc_chronos/run_engine.py` (= v414 pipe v321,
  corr-aware inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7,
  sleeve_gross_cap G=2.0, win_start=5, gate costs inside the engine).

## Correlation / agreement (CPU-only, before the engine; no outcome used)

- Universe: inner-joined feature rows (sym, shift, T) present in BOTH parquets,
  per anchor year y (year = [A_y + shift, min(+365d, 2026-09-23 + shift))).
- Per year: Spearman(m_D1, m_C2) over the joined rows (discrete {0.75,1,1.25};
  ties handled by rank-averaging; report n and the 3x3 agreement table counts
  of (m_D1 x m_C2)); plus pooled Spearman over all 5 years. Missing-either-side
  rows counted and disclosed (they contribute m=1.0 in the engine via assign_mult).
- Script `compute_overlap.py` -> `tmp/overlap.json`. No returns, no fits, no
  selection input — descriptive only.

## Engine (REF + the two ensembles; D1/C2 stay COPIED)

- Mechanism: copy of oc_chronos/run_engine.py with `leg_mult` replaced by the
  D1+C2 ensemble (`tilt_rule.ensemble_avg / ensemble_agree`); budget, books,
  corr sizes, win_start=5, gate costs unchanged (maker 0.0002, taker 0.00055,
  longs pay 0.0001/8h, shorts 0; limit fill only on 1m trade-through; nothing
  in first 5 min after a 4h close; stop-first in shared 1m bar — engine handles).
- Rows run through the engine (ONLY): REF, AVG, AGREE. D1/C2 numbers are COPIED
  from their REPORTs/results.json (labelled copied, not re-run).
- Stages: stage dev runs [DEV0=2021-09-24, DEV1=2025-09-24) (REF first; must
  reproduce v421 G2 years 0..3 R/DD to the digit, else STOP). Stage last runs
  [DEV0, Y1=2026-09-23) ONCE for REF + AVG + AGREE (each ensemble post-release
  number is a labelled diagnostic — both legs already saw Y4; selection is
  already frozen on dev4 before this stage, so scoring both ensembles once does
  not feed any choice). No re-runs after outcomes; any change becomes a
  disclosed extra row. Via heavy_slot, one job at a time; resume-safe caches
  tmp/runs_dev.pkl / tmp/runs_last.pkl; heartbeat every 600 s; nohup + tmp log.
- Metrics / selection (fixed): per-year 4-phase reset %/mo + DD via
  `reset_metric.year_reset`; dev4 geo mean, W (worst-year R), max yearly DD,
  losing count; 5y geo mean; full-path DD via `v388.mix` equal-1/4 mix from
  2021-09-24 (max of reset DDs and full-path for the gate); pooled book/rung/all
  win rates + fills/year + sized mean multiplier (same collection as
  oc_chronos/run_engine.py). Robust pick on dev4 ONLY among REF / AVG / AGREE:
  DD <= 20, no losing dev year; prefer dev4 mean >= 5 %/mo, then highest dev4
  WORST-year monthly return, ties -> higher mean.

## Timing placebo (CPU-only, per year, both ensembles)

- Method = exact copy of oc_chronos/compute_placebo.py with the AVG (resp. AGREE)
  multiplier instead of C2, on the reused D0+B1 replica ledger (read-only).
- Per year y: base(y), ens(y), realised_mean(y), norm(y) = ens(y)/realised_mean(y).
- Timing placebo (primary): 1000 uniform bar-level permutations of the ensemble
  multipliers over decision bars (seed 20261007+y), normalised by the ACTUAL
  realised mean. Block placebo: 42-bar blocks per (sym, shift) (seed 20261008+y).
  Percentile = 100*(1+#{perm<=actual})/1001; significant iff >= 95. Bar universe
  per year = frozen joined feature rows restricted to year y on each shift grid.
- Script `compute_placebo.py` -> `tmp/placebo_avg.json`, `tmp/placebo_agree.json`.
  Supporting evidence only, not a gate.

## Leakage / checks (stated in REPORT)

- Feature timing (D1: 36 closes <= T; C2: 512 closes <= T; both truncation-tested
  in their own test files; here only joined read-only — join key exact
  (sym, shift, T), tz-aware UTC; joining cannot create foresight).
- Label windows (harness t_exit < A - 7d inherited via frozen fits).
- Fit windows (shift-0 only + 7d embargo inherited; anchor-y fit for year y;
  frozen, never refit here).
- Fill timing (replica live 16..238 strict trade-through + stop-first inherited;
  engine win_start=5 + 1m trade-through + stop-first; perms reassign mults
  within-year only, seeds 20261007+y / 20261008+y).
- No statistic from any test year feeds any choice (fits frozen before this
  study; AVG/AGREE rules frozen above; selection on dev4 only).
- Gate costs inside replica outcomes and the engine.
- Coverage: disclose joined-parquet coverage and any skipped anchor year
  (none expected; missing feature -> mult 1, counted).
- Contamination label: C2 leg released 2024-11 (dev possibly contaminated,
  post-release clean for the leg but the ENSEMBLE post-release is still a
  labelled diagnostic because D1/C2 were both already scored on Y4).

## Compute plan (heavy_slot only for engine, resume-safe)

- `tilt_rule.py`: `assign_mult` + `ensemble_avg` + `ensemble_agree` + `anchor_of`
  pure helpers (unit-tested).
- `compute_overlap.py`: CPU-only joined correlation + agreement tables ->
  `tmp/overlap.json`.
- `run_engine.py`: heavy (same shape as oc_chronos/run_engine.py; rows
  REF,AVG,AGREE; caches `tmp/runs_dev.pkl` / `tmp/runs_last.pkl`).
- `compute_placebo.py`: CPU-only replica-ledger timing/block placebo for AVG +
  AGREE -> `tmp/placebo_avg.json`, `tmp/placebo_agree.json`.
- `analyze.py`: CPU-only scoring (reset metric + v388.mix + wins) ->
  `tmp/dev_table.json`, `tmp/last_table.json`; REPORT.md + results.json written
  from those tables only (D1/C2 rows labelled copied).
- Deliverables: PLAN.md (this file), tilt_rule.py, compute_overlap.py,
  run_engine.py, compute_placebo.py, analyze.py, results.json, REPORT.md,
  tests/test_oc_d1c2.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_d1c2.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the
  original row stays and the change is a disclosed extra row.)
