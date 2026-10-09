# oc_toto — PLAN (pre-registered 2026-10-08, BEFORE any outcome)

Assignment: `docs/opencode/OPENCODE_W_oc_toto.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md read). Write ONLY `research/tournament/oc_toto/`
+ `tests/test_oc_toto.py`. GPU (GTX1650) via heavy_slot; one GPU job at a time;
import torch BEFORE pandas in GPU scripts. Heartbeat / progress print every 600 s.
Scratch only under `research/tournament/oc_toto/tmp/`. Never inspect /proc.

## Why

oc_kronoshidden + oc_k2placebo + oc_k2bybit: the Kronos-small forecast of the next
4h bar's low (K2 tilt, risk = -low1) is the only new information source with
significant timing on the post-release year (placebo pct 97-99), robust on Bybit
prices. oc_chronos tests a second foundation model with the identical rule.
A third model with different pretraining tells whether the signal is generic
"next-bar low risk" that any good forecaster sees, or Kronos-specific.
Datadog Toto (Toto-Open-Base-1.0, observability metrics + public benchmark sets,
probably the least crypto-contaminated foundation model, so its dev years may
count as nearly clean) is the third test. The post-release year is scored ONCE
for all rows (a new information source; no selection on it).

## Model card / contamination disclosure (checked 2026-10-08, before any outcome)

- Model: `Datadog/Toto-Open-Base-1.0` (151M params, decoder-only, Student-T mixture,
  probabilistic; paper arxiv:2505.14766, NeurIPS 2026). Pip package `toto-ts 0.2.0`.
- Pretraining (model card Training Data Summary): ~1T points Datadog internal
  observability metrics (no customer data) + public datasets
  `Salesforce/GiftEvalPretrain` + `autogluon/chronos_datasets` + ~1/3 synthetic.
  Total ~2T points, largest open-weights TS pretraining set claimed.
- Crypto check: model card names only GIFT-Eval Pretrain + Chronos datasets as
  public sources. GIFT-Eval Pretrain and the Chronos pretraining corpus are
  general time-series benchmarks (energy/weather/traffic/synthetic/finance mix);
  neither model-card page lists a crypto series. Full dataset manifests were not
  enumerated file-by-file here; residual crypto contamination via the public
  corpora cannot be fully excluded, so dev4 is labelled "nearly clean / upper
  bound with small caveat", strictly cleaner than Kronos (released 2025-08,
  crypto-heavy) and comparable-or-cleaner than Chronos-Bolt (released 2024-11).
  The post-release year 2025-09-24..2026-09-23 (after the Toto release ~May 2025
  paper / model publication) is the clean verdict. Release dates + this caveat
  appear next to EVERY number in REPORT.

## Frozen inputs (read-only, never edited)

- `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet` (5 majors x shifts
  0..3 4h OHLCV from raw Binance USD-M 1m; 1m ends 2026-09-23 23:59).
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
  ledger, reused read-only for the placebo leg; reproduction gate n == 22312 and
  base 4-phase-mean sum5y == 7.718304 +- 0.002).
- `research/tournament/oc_chronos/*` (reference for identical feature/tilt/plumbing
  conventions only; no numbers feed any choice here).

## Part A — Toto features (fixed; GPU through heavy_slot, CPU fallback allowed)

- Package: `toto-ts` installed into a LOCAL target dir
  `research/tournament/oc_toto/pylib` (never into .venv; `sys.path.insert(0,
  <pylib>)` in scripts; `--no-deps` + minimal pure-python deps if it pulls an
  incompatible torch; broken torch/numpy/pandas shadows removed from pylib so
  .venv torch 2.12.1+cu126 is used). Weights `Datadog/Toto-Open-Base-1.0` via
  from_pretrained at runtime (HF cache). If the package cannot run on this
  Windows host after reasonable effort, STOP and report exactly why (no substitute).
- For each majors coin (BTC/ETH/SOL/BNB/XRP), each clock shift s = 0..3 (4h bars
  opening at s, s+4, ... UTC; the Kronos bars file), each bar open T in the same
  range as `kronos_features_4shift.parquet` (first T with a full 512-bar context
  available): context = the last 512 closes of that shift's bars ending at the
  bar closing at T (log prices; scale the context as the model expects),
  forecast horizon 1 bar.
- Probabilistic output: >= 256 samples (samples_per_batch as memory allows) or the
  predictive distribution; q10/q50/q90 of the next close.
  f_q10 = (q10 - log C0) / sigma, f_q50/f_q90 likewise; sigma = std of the last
  360 4h log returns (SAME formula as Kronos' sigma: std of diff(log(open))
  rolling 360); C0 = close of the bar closing at T. risk = -f_q10.
- Output: `toto_features_4shift.parquet` (sym, shift, T, f_q10, f_q50, f_q90, sigma).
- Causality: forecast for bar open T uses ONLY closes of bars closing <= T on that
  shift's grid; truncation test (features for T unchanged when all data after T's
  open is deleted; recompute multipliers from a truncated table -> identical prefix).
- Determinism: torch seed fixed, samples seed recorded; package version + model
  revision recorded in results.json. No threshold/parameter tuned on any outcome.
- Resume-safe: checkpoint per (sym, shift) group to the parquet (skip finished
  groups); heartbeat every 600 s; long jobs via nohup with log under tmp/.
- GPU contention: GPU via heavy_slot tag oc_toto_gpu; other workers (oc_k2seeds,
  oc_chronos) also need it — if wait > 30 min, run on CPU with batched inference.

## Part B — tilt (fixed; identical to K2/C2 except the feature)

- T3: rung-size multiplier x1.25 / x0.75 on the outer quintiles of risk = -f_q10,
  per-anchor fit on harness training rows (`research/tournament/harness.py`:
  t_exit < A - 7 d, shift-0 feature joined on (sym, T)): direction = sign of
  Spearman(risk, y_dep), edges q20 / q80 of risk. Mult hi=1.25 favourable outer
  quintile / lo=0.75 unfavourable / 1 else; missing/NaN risk -> 1. Fits of anchor A
  applied to all four shifts in year A. Most-recent-year fits use all harness rows
  with t_exit < 2025-09-17 (same convention as oc_kronoshidden). No 1.5/0.5 variant.
- Engine mechanism: exact copy of oc_kronoshidden/run_engine.py (= v414 pipe
  v321, corr-aware inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7,
  sleeve_gross_cap G=2.0, win_start=5, gate costs inside the engine).
- Rows (ONLY these four, fixed):
  - REF = G2 unchanged (tilt 1).
  - T3 = REF + Toto T3 tilt (fits.json written by make_fits.py in this folder).
  - K2 = REF + Kronos K2 tilt (frozen oc_kronoshidden fits.json + low1;
    reproduction row, hi/lo 1.25/0.75).
  - T3K2 = average of the two multipliers (m = (m_T3 + m_K2) / 2;
    pre-registered ensemble; missing leg -> the present leg averaged with 1.0).
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
  the gate); pooled book/rung/all win rates + fills/year + sized mean multiplier.
- Reproduction gate (STOP if failed): REF years 0..4 R/DD == v421_result.json G2
  [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27),(4.648/12.90)] to the
  digit, 5y 5.410, full-path DD 16.82; K2 years == oc_kronoshidden REPORT Table
  (dev 2.469/11.78, 3.478/16.20, 6.679/15.69, 10.653/8.54; Y4 4.801/12.10;
  full-path 16.09) to the digit.
- Robust pick on dev4 ONLY (T3 vs K2 vs T3K2; informational, no adoption here):
  DD <= 20, no losing dev year; prefer dev4 mean >= 5 %/mo, then highest dev4
  WORST-year monthly return, ties -> higher mean.
- Timing placebo on the post-release year exactly like oc_k2placebo (1000
  within-year permutations of the T3 multipliers over decision bars, normalised
  by the actual realised mean; percentile = 100*(1+#{perm<=actual})/1001;
  significant iff >= 95) + block variant (42-bar blocks per (sym, shift)).
  T3 only (K2 already has 97.2, C2 99.2).
- Extra: Spearman correlation of Toto risk (-f_q10) with Kronos -low1 on the same
  (sym, shift-0, T) rows (pooled + per-year), same join as fits.

## Leakage / contamination (pre-registered checks, stated in REPORT)

- Feature timing: Toto context = 512 closes of bars closing <= T on that shift's
  grid (assert in code; truncation test on the frozen parquet).
- Label windows: harness t_exit < A - 7d inherited for fits (not recomputed).
- Fit windows: shift-0 only + 7d embargo; year y uses anchor-y fit only, never a
  later anchor; no statistic from any test year feeds any choice.
- Fill timing: win_start=5 + 1m trade-through + stop-first (engine).
- Contamination note next to EVERY number (see Model card section): dev4 nearly
  clean (upper bound with small caveat); post-release year is the clean verdict.

## Compute plan (heavy_slot, resume-safe)

- `tilt_rule.py`: pure `assign_mult` + `anchor_of` + `ensemble_mult` copy (unit-tested).
- `run_toto_4shift.py`: inference (GPU preferred, CPU fallback), sequential
  (sym, shift) groups, checkpoint per group (resume-safe: skip finished groups),
  heartbeat every 600 s. Invoked via
  `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_toto_gpu
  --min-free-gb 2.0 -- .venv/Scripts/python.exe
  research/tournament/oc_toto/run_toto_4shift.py`.
- `make_fits.py`: CPU-only harness join -> `fits.json` (direction/q20/q80/rho/n).
- `run_engine.py`: copy of oc_kronoshidden mechanism for REF/T3/K2/T3K2,
  sequential shifts per stage, heartbeat 600 s, caches `tmp/runs_dev.pkl` /
  `tmp/runs_last.pkl` (resume-safe).
- `compute_placebo.py`: CPU-only 1000-permutation timing placebo for T3 on Y4
  (ledger reuse from oc_k2placebo).
- `analyze.py`: CPU-only scoring (reset metric + v388.mix + wins) ->
  `tmp/*_table.json`; REPORT.md + results.json written from those tables only.
- Deliverables: PLAN.md (this file), tilt_rule.py, run_toto_4shift.py,
  make_fits.py, run_engine.py, compute_placebo.py, analyze.py,
  toto_features_4shift.parquet, fits.json, results.json, REPORT.md,
  tests/test_oc_toto.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_toto.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the
  original row stays and the change is a disclosed extra row.)
