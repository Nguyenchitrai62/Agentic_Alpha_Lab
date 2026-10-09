# oc_chronos — PLAN (pre-registered 2026-10-07, BEFORE any outcome)

Assignment: `docs/opencode/OPENCODE_W_oc_chronos.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md read). Write ONLY `research/tournament/oc_chronos/`
+ `tests/test_oc_chronos.py`. GPU (GTX1650) via heavy_slot; one GPU job at a time;
import torch BEFORE pandas in GPU scripts. Heartbeat print every 600 s.
Scratch only under `research/tournament/oc_chronos/tmp/`.

## Why

oc_kronoshidden + oc_k2placebo + oc_k2bybit: the Kronos-small forecast of the next
4h bar's low (K2 tilt, risk = -low1) is the only new information source with
significant timing on the post-release year (placebo pct 97-99), robust on Bybit
prices. If a DIFFERENT foundation model with different pretraining also carries
the signal, the evidence becomes much stronger (and a 2-model ensemble may help).
Chronos-Bolt (amazon/chronos-bolt-small, released 2024-11, trained mostly on
public non-crypto corpora + synthetic data) -> less contamination risk for
2021-2024 than Kronos (still disclose), and the post-release year is clean.
This is a NEW information source: dev4 numbers are reported with the (smaller)
contamination caveat, and the post-release year is scored ONCE for all four rows
below (not a selection input — there is no selection between information
sources here, only the pre-registered dev4 robust pick C2 vs K2/C2K2 reporting).

## Frozen inputs (read-only, never edited)

- `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet` (5 majors x shifts
  0..3 4h OHLCV from raw Binance USD-M 1m; 1m ends 2026-09-23 23:59).
- `research/tournament/oc_kronoshidden/kronos_features_4shift.parquet` (K2 feature
  low1, used ONLY for the K2 reproduction row + C2K2 ensemble; never refit here).
- `research/tournament/oc_kronoshidden/fits.json` (K2 per-anchor direction/q20/q80;
  reused frozen for the K2 row only).
- `research/tournament/oc_kronoshidden/REPORT.md` + `results.json` (expected K2
  numbers for the reproduction gate) + `run_engine.py` + `tilt_rule.py`
  (mechanism + `assign_mult` copied verbatim; no behaviour change on base).
- `research/tournament/harness.py` (per-anchor fits for C2).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` +
  `v421_result.json` row R2B1D17BFG2 (G2 baseline: 5.41 %/mo, max yearly DD 16.91,
  full-path DD 16.82).
- `research/tournament/oc_placebo_dip/compute_placebo_dip.py` (D0 replica for the
  placebo leg, imported read-only) — only if needed; primary placebo is the
  engine-row permutation below.

## Part A — Chronos features (fixed; GPU through heavy_slot)

- Package: `chronos-forecasting` installed into a LOCAL target dir
  `research/tournament/oc_chronos/pylib` (never into .venv; `sys.path.insert(0,
  <pylib>)` in scripts; `--no-deps` fallback if it pulls an incompatible torch).
  Weights `amazon/chronos-bolt-small` via from_pretrained at runtime (HF cache).
- For each majors coin (BTC/ETH/SOL/BNB/XRP), each clock shift s = 0..3 (4h bars
  opening at s, s+4, ... UTC; the Kronos bars file), each bar open T in
  2020-10 .. 2026-09-23 (same range convention as the Kronos file: first T with
  a full 512-bar context available):
  context = the last 512 closes of that shift's bars ending at the bar closing
  at T (log prices), forecast horizon 1 bar, quantiles from Chronos-Bolt
  (it outputs quantile levels 0.1..0.9).
- ch_q10 = (q10 forecast of the next close - log C0) / sigma, ch_q50 likewise
  (ch_q90 stored too); sigma = std of the last 360 4h log returns (same sigma
  as Kronos' sigma); C0 = close of the bar closing at T. risk = -ch_q10.
- Output: `chronos_features_4shift.parquet` (sym, shift, T, ch_q10, ch_q50,
  ch_q90, sigma). Causality: forecast for bar open T uses ONLY closes of bars
  closing <= T on that shift's grid; truncation test (recompute multipliers from
  a truncated feature table -> identical on the kept prefix).
- Determinism: Chronos-Bolt quantile heads are deterministic given weights
  (no sampling temperature); record package version + model revision in
  results.json. No threshold/parameter is tuned on any outcome.

## Part B — tilt (fixed; identical to K2 except the feature)

- C2: rung-size multiplier x1.25 / x0.75 on the outer quintiles of risk =
  -ch_q10, per-anchor fit on harness training rows
  (`research/tournament/harness.py`: t_exit < A - 7 d, shift-0 feature joined on
  (sym, T)): direction = sign of Spearman(risk, y_dep), edges q20 / q80 of risk.
  Mult hi=1.25 favourable outer quintile / lo=0.75 unfavourable / 1 else;
  missing/NaN risk -> 1. Fits of anchor A applied to all four shifts in year A.
  Most-recent-year fits use all harness rows with t_exit < 2025-09-17 (same
  convention as oc_kronoshidden). No K1 (1.5/0.5) variant: the assignment fixes
  C2 at 1.25/0.75.
- Engine mechanism: exact copy of oc_kronoshidden/run_engine.py (= v414 pipe
  v321, corr-aware inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7,
  sleeve_gross_cap G=2.0, win_start=5, gate costs inside the engine).
- Rows (ONLY these four, fixed):
  - REF = G2 unchanged (tilt 1).
  - C2 = REF + Chronos C2 tilt (fits.json written by make_fits.py in this folder).
  - K2 = REF + Kronos K2 tilt (frozen oc_kronoshidden fits.json + low1;
    reproduction row, hi/lo 1.25/0.75).
  - C2K2 = average of the two multipliers (m = (m_C2 + m_K2) / 2;
    pre-registered ensemble; missing leg -> the present leg averaged with 1.0,
    i.e. m = (m_present + 1.0)/2, same rule as a missing feature in that leg).
- Stages: stage dev runs [DEV0=2021-09-24, DEV1=2025-09-24) for all four rows
  (REF first; must reproduce v421 G2 years 0..3 R/DD to the digit AND
  oc_kronoshidden K2 dev R/DD to the digit, else STOP); stage last runs
  [DEV0, Y1=2026-09-23) for all four rows ONCE (new information source; every
  Y4 number labelled as scored-once). No re-runs after seeing outcomes; any
  change becomes a disclosed extra row.

## Metrics / gates (fixed)

- Gate costs: maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts 0. Limits
  fill only on 1m trade-through, nothing in the first 5 min after a 4h close
  (win_start=5); stop-first in shared 1m bar (engine handles).
- Per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4/5y geo
  mean, W (worst-year R), max yearly DD, losing count; full-path DD via
  `v388.mix` equal-1/4 mix from 2021-09-24 (max of reset DDs and full-path for
  the gate); pooled book/rung/all win rates + fills/year + sized mean multiplier
  (same collection as oc_kronoshidden run_engine.py).
- Reproduction gate (STOP if failed): REF years 0..4 R/DD == v421_result.json G2
  [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27),(4.648/12.90)] to the
  digit, 5y 5.410, full-path DD 16.82; K2 years == oc_kronoshidden REPORT Table
  (dev 2.469/11.78, 3.478/16.20, 6.679/15.69, 10.653/8.54; Y4 4.801/12.10;
  full-path 16.09) to the digit.
- Robust pick on dev4 ONLY (K2 vs C2 vs C2K2; informational, no adoption here):
  DD <= 20, no losing dev year; prefer dev4 mean >= 5 %/mo, then highest dev4
  WORST-year monthly return, ties -> higher mean.
- Timing placebo on the post-release year exactly like
  research/tournament/oc_k2placebo (1000 within-year permutations of the C2
  multipliers over decision bars, normalised by the actual realised mean;
  percentile = 100*(1+#{perm<=actual})/1001; significant iff >= 95). C2 only
  (K2 already has 97.2). Light numpy code after the engine (D0-replica leg only
  if the engine placebo needs a cross-check; not pre-registered as a gate).

## Leakage / contamination (pre-registered checks, stated in REPORT)

- Feature timing: Chronos context = 512 closes of bars closing <= T on that
  shift's grid (assert in code; truncation test on the frozen parquet).
- Label windows: harness t_exit < A - 7d inherited for fits (not recomputed).
- Fit windows: shift-0 only + 7d embargo; year y uses anchor-y fit only, never a
  later anchor; no statistic from any test year feeds any choice.
- Fill timing: win_start=5 + 1m trade-through + stop-first (engine).
- Contamination caveat next to EVERY number: Chronos-Bolt released 2024-11,
  trained mostly on public non-crypto corpora + synthetic data -> LESS
  contamination risk for 2021-2024 than Kronos (released 2025-08, crypto-heavy),
  but dev is still labelled possibly-contaminated; the post-release year
  (2025-09-24..2026-09-23, after BOTH releases) is the clean verdict. Disclose
  model release dates + pretraining corpora statement in REPORT.

## Compute plan (heavy_slot, resume-safe)

- `tilt_rule.py`: pure `assign_mult` + `anchor_of` copy (unit-tested).
- `run_chronos_4shift.py`: GPU inference, sequential (sym, shift) groups,
  checkpoint per group to the parquet (resume-safe: skip finished groups),
  heartbeat every 600 s. Invoked via
  `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_chronos_gpu
  --min-free-gb 2.0 -- .venv/Scripts/python.exe
  research/tournament/oc_chronos/run_chronos_4shift.py`.
- `make_fits.py`: CPU-only harness join -> `fits.json` (direction/q20/q80/rho/n).
- `run_engine.py`: sequential shifts per stage (one heavy process), heartbeat
  every 600 s, caches `tmp/runs_dev.pkl` / `tmp/runs_last.pkl` (resume-safe).
- `compute_placebo.py`: CPU-only 1000-permutation timing placebo for C2 on Y4.
- `analyze.py`: CPU-only scoring (reset metric + v388.mix + wins) ->
  `tmp/*_table.json`; REPORT.md + results.json written from those tables only.
- Deliverables: PLAN.md (this file), tilt_rule.py, run_chronos_4shift.py,
  make_fits.py, run_engine.py, compute_placebo.py, analyze.py,
  chronos_features_4shift.parquet, fits.json, results.json, REPORT.md,
  tests/test_oc_chronos.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_chronos.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the
  original row stays and the change is a disclosed extra row.)
