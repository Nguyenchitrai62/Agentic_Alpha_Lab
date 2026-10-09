# oc_timesfm — PLAN (pre-registered 2026-10-08, BEFORE any outcome)

Assignment: `docs/opencode/OPENCODE_W_oc_timesfm.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md read). Write ONLY `research/tournament/oc_timesfm/`
+ `tests/test_oc_timesfm.py`. GPU (GTX1650) via heavy_slot; one GPU job at a time;
import torch BEFORE pandas in GPU scripts. Heartbeat print every 600 s.
Scratch only under `research/tournament/oc_timesfm/tmp/`.

## Why

oc_kronoshidden + oc_k2placebo + oc_k2bybit: Kronos-small next-4h-bar low (K2 tilt,
risk = -low1) is the only new information source with significant timing on the
post-release year (placebo pct 97-99), robust on Bybit prices. oc_chronos tests a
second foundation model with the identical rule (C2: clean-year +0.106, timing
99.2, trails K2). A THIRD model with different pretraining tells whether the
signal is generic "next-bar low risk" any good forecaster sees, or
Kronos-specific.

## Model card (disclosed BEFORE any outcome; from HF + GitHub, fetched 2026-10-08)

- Model: `google/timesfm-2.5-200m-pytorch` (TimesFM 2.5, 200M params, PyTorch
  backend, max context 16,384; weights ~925 MB safetensors; Apache-2.0).
- Pretraining corpus (model card, verbatim): GiftEvalPretrain + Wikimedia
  Pageviews (cutoff Nov 2023) + Google Trends top queries (cutoff EoY 2022) +
  synthetic and augmented data.
- Crypto disclosure: the model card lists NO explicit crypto/price series.
  GiftEvalPretrain composition is not fully itemised in the card, so incidental
  financial series cannot be ruled out — disclosed as unknown, not as clean.
  No Kronos-style exchange-candle pretraining is stated.
- Release: TimesFM 2.5 launched Sept 2025 (GitHub README "Sept. 2025 launch").
  For comparison: Chronos-Bolt 2024-11 (mostly non-crypto + synthetic),
  Kronos-small 2025-08 (crypto-heavy, dev likely in-pretraining).
- Contamination labelling (frozen): dev years 2021-2024 predate the Sept-2025
  release but overlap the stated pretraining windows (Trends to EoY 2022, Wiki
  to Nov 2023, GiftEval unknown) -> dev4 numbers are reported as
  POSSIBLY-CONTAMINATED UPPER BOUND. The post-release year 2025-09-24 ..
  2026-09-23 starts AFTER the release AND after every stated cutoff -> clean
  verdict. This is a NEW information source: the post-release year is scored
  ONCE for all four rows below (not a selection input).

## Frozen inputs (read-only, never edited)

- `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet` (5 majors x shifts
  0..3 4h OHLCV from raw Binance USD-M 1m; 1m ends 2026-09-23 23:59; 268,325 rows).
- `research/tournament/oc_kronoshidden/kronos_features_4shift.parquet` (K2 feature
  low1, used ONLY for the K2 reproduction row + T3K2 ensemble; never refit here).
- `research/tournament/oc_kronoshidden/fits.json` (K2 per-anchor direction/q20/q80;
  reused frozen for the K2 row only).
- `research/tournament/oc_kronoshidden/REPORT.md` + `results.json` (expected K2
  numbers for the reproduction gate) + `run_engine.py` + `tilt_rule.py`
  (mechanism + `assign_mult` copied verbatim; no behaviour change on base).
- `research/tournament/harness.py` (per-anchor fits for T3).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` +
  `v421_result.json` row R2B1D17BFG2 (G2 baseline: 5.41 %/mo, max yearly DD 16.91,
  full-path DD 16.82).
- `research/tournament/oc_k2placebo/tmp/ledger.npz` + `bt_all.npy` (D0+B1 replica
  ledger, read-only reuse for the placebo leg; reproduction gate n == 22312 and
  base 4-phase-mean sum5y == 7.718304 +- 0.002).

## Part A — TimesFM features (fixed; GPU through heavy_slot)

- Package: `timesfm` (with the torch extra) installed into a LOCAL target dir
  `research/tournament/oc_timesfm/pylib` (never into .venv; `sys.path.insert(0,
  <pylib>)` in scripts; `--no-deps` fallback if it pulls an incompatible torch;
  broken torch/numpy/pandas shadows removed from pylib if they appear, .venv
  torch 2.12.1+cu126 is used). Weights `google/timesfm-2.5-200m-pytorch` via
  from_pretrained at runtime (HF cache). If the package cannot run on this
  Windows host after a reasonable effort, STOP and report exactly why — do not
  substitute another model.
- For each majors coin (BTC/ETH/SOL/BNB/XRP), each clock shift s = 0..3 (4h bars
  opening at s, s+4, ... UTC; the Kronos bars file), each bar open T in the same
  range convention as the Kronos file (first T with a full 512-bar context
  available; START floor 2020-08-01, same mask as oc_chronos):
  context = the last 512 closes of that shift's bars ending at the bar closing
  at T (LOG prices, raw log values passed; model-side scaling via
  ForecastConfig normalize_inputs=True which z-normalises internally and returns
  forecasts in input scale), forecast horizon 1 bar.
- Compile (frozen): ForecastConfig(max_context=512, max_horizon=1,
  normalize_inputs=True, per_core_batch_size=32, use_continuous_quantile_head=True,
  force_flip_invariance=True, infer_is_positive=True, fix_quantile_crossing=True,
  quantiles=[0.1..0.9]). Batch B=64 series per forecast() call on GPU
  (CPU fallback: B=256 if GPU wait > 30 min). torch_compile=False (Windows
  compat). Seed 20261008 (only affects any stochastic fallback; quantile head
  is deterministic).
- f_q10 = (q10 forecast of the next close - log C0) / sigma, f_q50 / f_q90
  likewise, where quantile_forecast[:,0,1/5/9] = q10/q50/q90 (timesfm API:
  quantile_forecast shape (B,H,10) = [mean,q10..q90]); sigma = std of the last
  360 4h log returns (SAME formula as Kronos/Chronos sigma: std of
  diff(log(open)) rolling 360); C0 = close of the bar closing at T.
  risk = -f_q10 (in tilt/make_fits, not here).
- Output: `timesfm_features_4shift.parquet` (sym, shift, T, f_q10, f_q50,
  f_q90, sigma). Causality: forecast for bar open T uses ONLY closes of bars
  closing <= T on that shift's grid (bars e-512..e-1 for the bar at index e);
  truncation test (features for T unchanged when all data after T's open is
  deleted; recompute multipliers from a truncated feature table -> identical on
  the kept prefix).
- Determinism: quantile heads are deterministic given weights; record package
  version + model revision in results.json. No threshold/parameter is tuned on
  any outcome.
- Compute: GPU via heavy_slot (`--tag oc_timesfm_gpu`); sequential (sym, shift)
  groups, checkpoint per group to the parquet (resume-safe: skip finished
  groups), heartbeat every 600 s. Long jobs: nohup, log progress to a file
  under tmp/, poll the log. If GPU wait > 30 min, run on CPU with batched
  inference instead.

## Part B — tilt (fixed; identical to K2/C2 except the feature)

- T3: rung-size multiplier x1.25 / x0.75 on the outer quintiles of risk =
  -f_q10, per-anchor fit on harness training rows
  (`research/tournament/harness.py`: t_exit < A - 7 d, shift-0 feature joined on
  (sym, T)): direction = sign of Spearman(risk, y_dep), edges q20 / q80 of risk.
  Mult hi=1.25 favourable outer quintile / lo=0.75 unfavourable / 1 else;
  missing/NaN risk -> 1. Fits of anchor A applied to all four shifts in year A.
  Most-recent-year fits use all harness rows with t_exit < 2025-09-17 (same
  convention as oc_kronoshidden/oc_chronos). No 1.5/0.5 variant: the assignment
  fixes T3 at 1.25/0.75.
- Engine mechanism: exact copy of oc_kronoshidden/run_engine.py (= v414 pipe
  v321, corr-aware inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7,
  sleeve_gross_cap G=2.0, win_start=5, gate costs inside the engine).
- Rows (ONLY these four, fixed):
  - REF = G2 unchanged (tilt 1).
  - T3 = REF + TimesFM T3 tilt (fits.json written by make_fits.py in this folder).
  - K2 = REF + Kronos K2 tilt (frozen oc_kronoshidden fits.json + low1;
    reproduction row, hi/lo 1.25/0.75).
  - T3K2 = average of the two multipliers (m = (m_T3 + m_K2) / 2;
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
- Robust pick on dev4 ONLY (T3 vs K2 vs T3K2; informational, no adoption here):
  DD <= 20, no losing dev year; prefer dev4 mean >= 5 %/mo, then highest dev4
  WORST-year monthly return, ties -> higher mean.
- Timing placebo on the post-release year exactly like
  research/tournament/oc_k2placebo (1000 within-year permutations of the T3
  multipliers over decision bars, normalised by the actual realised mean;
  percentile = 100*(1+#{perm<=actual})/1001; significant iff >= 95). T3 only
  (K2 already has 97.2, C2 has 99.2). Light numpy code reusing the K2placebo
  ledger (D0-replica leg). Block placebo (42-bar blocks per (sym,shift)) as
  a secondary row, same seeds as K2/C2 (timing 20261007+y, block 20261008+y).
- Correlation: Spearman(risk_T3, Kronos -low1) pooled + per-year on the same
  joined rows (shift-0 harness overlap AND full decision-bar universe); Pearson
  as a side row. Weak correlation (~0.2 like C2) = genuinely different signal.

## Leakage / contamination (pre-registered checks, stated in REPORT)

- Feature timing: TimesFM context = 512 closes of bars closing <= T on that
  shift's grid (assert in code; truncation test on the frozen parquet).
- Label windows: harness t_exit < A - 7d inherited for fits (not recomputed).
- Fit windows: shift-0 only + 7d embargo; year y uses anchor-y fit only, never a
  later anchor; no statistic from any test year feeds any choice.
- Fill timing: win_start=5 + 1m trade-through + stop-first (engine).
- Contamination caveat next to EVERY number: TimesFM 2.5 released Sept 2025,
  pretraining = GiftEvalPretrain + Wiki pageviews (Nov 2023) + Google Trends
  (EoY 2022) + synthetic (no explicit crypto in card, GiftEval remainder
  undisclosed) -> dev labelled possibly-contaminated UPPER BOUND; the
  post-release year (2025-09-24..2026-09-23, after release and all cutoffs) is
  the clean verdict. Disclose model release date + pretraining corpora in REPORT.

## Compute plan (heavy_slot, resume-safe)

- `tilt_rule.py`: pure `assign_mult` + `ensemble_mult` + `anchor_of` copy
  (unit-tested).
- `run_timesfm_4shift.py`: GPU inference, sequential (sym, shift) groups,
  checkpoint per group to the parquet (resume-safe: skip finished groups),
  heartbeat every 600 s. Invoked via
  `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_timesfm_gpu
  --min-free-gb 2.0 -- .venv/Scripts/python.exe
  research/tournament/oc_timesfm/run_timesfm_4shift.py`.
- `make_fits.py`: CPU-only harness join -> `fits.json` (direction/q20/q80/rho/n).
- `run_engine.py`: copy of oc_chronos/run_engine.py with C2->T3 swap; sequential
  shifts per stage (one heavy process), heartbeat every 600 s, caches
  `tmp/runs_dev.pkl` / `tmp/runs_last.pkl` (resume-safe).
- `compute_placebo.py`: CPU-only 1000-permutation timing (+block) placebo for T3
  on Y4, reusing oc_k2placebo ledger read-only.
- `analyze.py`: CPU-only scoring (reset metric + v388.mix + wins) ->
  `tmp/*_table.json`; REPORT.md + results.json written from those tables only.
- Deliverables: PLAN.md (this file), tilt_rule.py, run_timesfm_4shift.py,
  make_fits.py, run_engine.py, compute_placebo.py, analyze.py,
  timesfm_features_4shift.parquet, fits.json, results.json, REPORT.md,
  tests/test_oc_timesfm.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_timesfm.py -q`).

## Post-hoc log

- 2026-10-08: no outcome-driven changes. Procedural staging only (REF dev rows
  run first to check the reproduction gate before the tilt rows; same code,
  same frozen fits). All four rows defined here; REPORT.md + results.json
  written from tmp/*_table.json only. No re-runs after seeing outcomes.
