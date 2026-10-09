# oc_kronosbase — PLAN (pre-registered 2026-10-08, BEFORE any outcome)

Does the LARGER Kronos (Kronos-base, 102M) carry the K2 signal more strongly?
K2 = research/tournament/oc_kronoshidden K2 tilt (Kronos-small zero-shot,
risk = -low1, 1.25 / 0.75). Same rule, bigger model. If base ranks risk more
strongly / stably, cheapest upgrade of the only new signal; if not, K2 is not
just "more model = more edge". Kronos-base on the local GTX1650 would take too
long (S = 64 paths, 4 clocks, 6 years) so inference runs on Kaggle. FROZEN here;
any change after an outcome keeps the original row + a disclosed extra row.

## Frozen inputs (read-only, never edited)

- `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet` (10,648,736 B):
  4h OHLCV BTC/ETH/SOL/BNB/XRP, shifts 0..3, 2020-08-01 .. last local 4h bar.
- `research/tournament/oc_kronoshidden/kronos_features_4shift.parquet`
  (260,325 rows, 20 (sym,shift) groups, 2020-10-06 .. 2026-09-23): SMALL
  reference for the 50-row reproduction check + low1 Spearman.
- `research/tournament/oc_kronoshidden/PLAN.md` (settings) +
  `run_inference_4shift.py` (sampling/feature math) + `kronos_fast.py` +
  `model/` (copied ../Kronos code, never modify ../Kronos) + `tilt_rule.py` +
  `run_engine.py` + `fits.json`/`ctrl.json` + `REPORT.md` (K2 numbers to
  reproduce before trusting any base row).
- `research/tournament/oc_k2placebo/compute_k2placebo.py` + `PLAN.md`: timing
  (seed 20261007+y) + block-42 (seed 20261008+y) placebo spec, N = 1000,
  pct = 100*(1+#{perm<=actual})/1001, significant iff >= 95.
- G2 deployed reference = `R2B1D17BFG2` in
  `research/parallel/rounds/parallel-20260906-r2/v421` (5.41 %/mo 4-phase reset
  metric, max yearly DD 16.91, full-path DD 16.82; equity in `v421_runs.pkl`).

## Part A — features on Kaggle (fixed; identical to oc_kronoshidden but -base)

- Model: `NeoQuasar/Kronos-base` + `NeoQuasar/Kronos-Tokenizer-base` from the HF
  hub INSIDE the kernel. Code: `kronos_fast.py` + `model/` copied verbatim from
  oc_kronoshidden into this folder's kernel bundle (never modify ../Kronos).
- Settings EXACT: context 400 x 4h bars, pred_len 6, S = 64, T = 1.0,
  top_p = 0.9, top_k = 0, torch seed 1234, fp32, per-window z-normalisation +
  clip 5, same bars file, same T range (forecast for bar open T uses ONLY the
  400 bars closing <= T on that shift's grid), same 8 features + sigma/C0
  (er1, er6, vol1, vol6, rng1, low1, pdrop2, pdrop3).
- Reproduction GATE first on Kaggle: Kronos-SMALL with this bundle reproduces
  50 rows of `kronos_features_4shift.parquet` (low1 max abs diff; GPU
  nondeterminism must be small) BEFORE any Kronos-base run. Gate fails: STOP.
- Output: `kronosbase_features_4shift.parquet` (sym, shift, T, same columns).
  Kernel resumable/chunked (one run per clock shift) if the 12 h limit is tight.
  Kernel + dataset PRIVATE; download ONLY the output parquet.

## Part B — tilt + engine (fixed; K2's rule with base low1)

- KB2 = K2's rule with Kronos-base low1. Per anchor A in
  {2021,2022,2023,2024,2025}-09-24: TRAINING = majors rows of harness.load()
  with t_exit < A - 7 d AND shift-0 base feature present (join on (sym, T)):
  risk = -low1_base; direction = sign of Spearman(risk, y_dep); edges q20/q80
  of risk. Mult 1.25 favourable outer quintile / 0.75 unfavourable / 1 else;
  missing/NaN -> 1. Fits of A applied to all four shifts in year A.
  Most-recent-year fits use rows with t_exit < 2025-09-17.
- Engine = G2 path via oc_kronoshidden `run_engine.py` / `tilt_rule.py` verbatim
  (mechanism = v414 pipe v321, corr-aware inv kd=1.7, bear books, budget
  0.26*1*1.7, G=2.0, win_start=5, gate costs inside). Reproduce REF and K2
  first (REF bit-identical 5.41 / 16.91 / 16.82; K2 = oc_kronoshidden dev
  2.469/3.478/6.679/10.653 + last year 4.801) else STOP.
- Variants (ONLY these four, fixed):
  - REF = G2 unchanged.
  - K2 = small-low1 1.25/0.75 (reference, reproduced).
  - KB2 = base-low1 1.25/0.75 (candidate).
  - KBK2 = average of the K2 and KB2 multipliers per (coin, bar)
    (pre-registered; e.g. 1.25+1.25->1.25, 0.75+0.75->0.75, 1.25+0.75->1.0,
    1.25+1.0->1.125, 0.75+1.0->0.875, 1.0+1.0->1.0; missing either side -> 1
    for that side before averaging is NOT used — missing low1 on either model
    maps that side to 1.0 first, then average).
- Score dev4 (anchors 2021..2024, each [A, A+365d)): per-year 4-phase reset
  %/mo, yearly DD, full-path DD (continuous from 2021-09-24), all-trade win
  rate, fills/year, mean multiplier. Choose KB2 vs KBK2 on dev4 ONLY with the
  robust criterion (DD <= 20, no losing dev year; prefer dev4 mean >= 5 %/mo,
  then highest dev4 WORST-year monthly return, ties -> higher mean). Then score
  the most recent year 2025-09-24 .. 2026-09-23 ONCE for the chosen + REF (+K2
  reproduced reference) and label it. No selection on the last year.
  Report also the 5y geometric mean. Dev rows labelled UPPER BOUND (inside
  Kronos pretraining); the post-release year is a different model and gets no
  selection use (prospective paper log stays the decider).
- Extra diagnostics (fixed): Spearman correlation of the two low1 series
  (base vs small, pooled + per coin, shift-0 join on (sym,T)); timing placebo
  pct on the post-release year EXACTLY like oc_k2placebo (1000 uniform + 1000
  block-42 per year, same seeds/formula; focus y=4, dev years for context with
  contamination label). Post-2026-09-23 window: labelled extra row only if the
  4-phase engine minutes + books cover it (oc_kronoshidden found it NOT
  runnable — expect "why not").

## Costs / leakage / caveats (fixed)

- Gate costs: maker 0.0002, taker 0.00055 (stops/market exits taker), longs pay
  0.0001/8h settlement held (00/08/16 UTC), shorts 0. Limits fill only on a 1m
  trade-through, nothing in the first 5 min after a 4h close; stop-first in a
  shared 1m bar (engine handles).
- Leakage checks in REPORT: feature timing (400 bars <= T), label windows
  (harness t_exit < A - 7d), fit windows (shift-0 only + 7d embargo), fill
  timing (win_start=5, trade-through). No statistic from any test year feeds
  any choice. Contamination caveat next to EVERY dev number (upper bound).
- A negative result is valid. Vietnamese 3-line verdict at the end of REPORT.

## Compute / guardrails (frozen)

- Kaggle, account 1 ONLY, DEFAULT auth (already configured). Never read, print,
  copy or pass any token (.env, ~/.kaggle); never use the second account.
  First `kaggle kernels list --mine`, check running kernels / GPU quota; one
  kernel at a time. Bars parquet uploaded as a PRIVATE dataset (own
  dataset-metadata.json under this folder). Kernel PRIVATE; download only the
  output parquet. Local GTX1650 NOT used for the full S=64/4-clock/6-year job.
  If Kaggle unavailable or out of GPU quota: STOP and report.
- Wave guardrail conflict (disclosed BEFORE any outcome):
  docs/opencode/OPENCODE_W_COMMON_20261007.md forbids Kaggle uploads for this
  wave. So this worker PREPARES the dataset metadata + kernel bundle locally
  but does NOT run `kaggle datasets create` / `kaggle kernels push`. If the
  guardrail stands, Part A stays BLOCKED and REPORT records blocked + the
  prepared bundle + the read-only `kernels list --mine` evidence. No heavy
  engine run is started without the base feature file (would be outcome-driven
  compute). Heavy steps, when unblocked, go through heavy_slot; GPU scripts
  import torch before pandas. Progress printed at least every 10 min
  (heartbeat thread in long scripts).
- Write ONLY `research/tournament/oc_kronosbase/` + `tests/test_oc_kronosbase.py`.
  Scratch only under `research/tournament/oc_kronosbase/tmp/`. Never touch the
  registry, ledgers, docs (except this PLAN), bot/, backend/, scripts/, other
  workers' folders, ../Kronos, artifacts/bot/*, .env/credentials. GIT READ-ONLY.

## Outputs

- `research/tournament/oc_kronosbase/PLAN.md` (this file, frozen),
  `kronosbase_features_4shift.parquet` (when unblocked), `REPORT.md` (per-year
  tables %/mo + DD + trades + win rate, what failed and why, leakage section,
  Vietnamese verdict), `results.json` (numbers + seeds + coverage next to it).
- `tests/test_oc_kronosbase.py` (>=1 causality/truncation test + >=1
  hand-checked synthetic case; `.venv/Scripts/python.exe -m pytest <file> -q`).
