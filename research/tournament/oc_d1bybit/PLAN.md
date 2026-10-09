# oc_d1bybit — PLAN (pre-registered 2026-10-08, BEFORE any outcome)

Assignment: `docs/opencode/OPENCODE_W_oc_d1bybit.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md read). Write ONLY `research/tournament/oc_d1bybit/`
+ `tests/test_oc_d1bybit.py`. Engine runs via heavy_slot (one engine job at a time;
RAM tight: one engine job at a time, load one coin at a time where applicable).
Progress print every 10 minutes (heartbeat every 600 s in engine). Scratch only under
`research/tournament/oc_d1bybit/tmp/`. GIT IS READ-ONLY: never stash/reset/checkout/
restore/clean/rm/commit/switch/rebase/merge. No exchange orders, no authenticated
endpoints, no Kaggle uploads. Long jobs: nohup + log file under tmp/, poll the log.

## Question

Does the downside-share dip tilt D1 keep its dev edge under frictions and on BYBIT
prices (S5)? Context (given, not recomputed): `oc_downshare` D1 (dip rung size
x1.25/x0.75 on the outer quintiles of the trailing-6d downside-RV share, per-anchor
fits.json D1 section, no pretraining anywhere) is the dev4 robust pick (dev4 mean
5.776 / WORST 2.921 / DDmax 16.09 vs REF 5.601 / 2.588 / 16.91) but the post-release
year was -0.057 vs REF (4.591 vs 4.648). `oc_c2bybit` did exactly this friction check
for C2 — copy its harness (compute_c2bybit_engine.py, analyze_c2bybit.py) and swap the
multipliers (Chronos ch_q10 -> downshare risk_D1, frozen oc_downshare fits.json D1).

## Frozen inputs (read-only, never edited, never refit)

- `research/tournament/oc_downshare/downshare_features_4shift.parquet` (sym, shift,
  T, risk_D1 + risk_D2; 268,325 rows; D1 cov 0.9972; used ONLY risk_D1 here).
- `research/tournament/oc_downshare/fits.json` D1 section only (per-anchor direction
  + q20/q80 of risk_D1, shift-0 harness rows t_exit < A - 7d; anchor-2025 fit for the
  post-release year). D1 fits: 2021 dir+1 rho 0.0127 q20 0.2517 q80 0.6849; 2022 -1
  -0.0200 0.3219 0.7600; 2023 -1 -0.0051 0.3160 0.7667; 2024 +1 0.0011 0.2961
  0.7528; 2025 +1 0.0026 0.2903 0.7420. D2 is NOT run here.
- `research/tournament/oc_downshare/REPORT.md` + `results.json` + `tmp/dev_table.json`
  + `tmp/last_table.json` (expected REF/D1 numbers for the reproduction gate).
- `research/tournament/oc_downshare/run_engine.py` + `tilt_rule.py` (mechanism +
  `assign_mult` copied verbatim into this folder; only the feature source stays the
  same risk_D1 — no behaviour change on base).
- `research/tournament/oc_c2bybit/tmp/c2bybit_table.json` + REPORT.md + results.json
  (C2 side-by-side numbers; read-only, never recomputed here).
- `research/tournament/oc_chronos/chronos_features_4shift.parquet` (ch_q10) +
  `fits.json` (C2 direction +1 all anchors) — read-only, ONLY for the D1-vs-C2
  multiplier Spearman comparison (frozen features + frozen fits, CPU-only).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` +
  `v421_result.json` row R2B1D17BFG2 (G2 baseline: 5.41 %/mo, max yearly DD 16.91,
  full-path DD 16.82).
- `research/parallel/rounds/parallel-20260906-r2/v421_audit/robust_v421.py` +
  `ROBUST.md` (friction defs S1..S5; copied exactly) and
  `research/tournament/oc_amihudrobust/compute_robust_engine.py` (S5 Bybit loading
  pattern `bybit_minutes()`).
- `data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet` (SYM in BTC/ETH/SOL/BNB/XRP;
  cols open_time ms, open/high/low/close) for S5 only.

## Variants (ONLY these; no selection, no tuning, no extra knob)

- REF = G2 unchanged (R2B1D17BFG2: rule inv, k 1.0, kd 1.7, bear True, G 2.0).
- D1 = REF + downshare D1 tilt: risk = risk_D1 (trailing-6d downside-RV share);
  per anchor A fit from oc_downshare fits.json D1 (direction, q20, q80); mult
  hi=1.25 favourable outer quintile / lo=0.75 unfavourable / 1 else;
  missing/NaN risk -> 1. Fits of anchor A applied to all four shifts in year A
  (year y = [ANCH5[y]+sh, min(+365d, live1)); ANCH5 = 2021..2025-09-24).
- Rows (12 engine rows): REF_base, D1_base, REF_S1, D1_S1, REF_S2, D1_S2,
  REF_S3, D1_S3, REF_S4, D1_S4, REF_S5, D1_S5.
- If anything changes after seeing an outcome, the original row stays and the
  change is added as a disclosed extra row (none planned).

## Mechanism (exact copy of oc_downshare/run_engine.py on base = oc_chronos pipe)

- 4 phases (shifts 0..3, 4h grid opens at s, s+4, ... UTC); pipe v321 via
  phase_offset_full.pipe_setup; corr-aware dip sizes mult 1/(1+n)*1.7*tilt*base
  (n = coins with C<=O*(1-2.5*sig)); risk_mult 1.0; sleeve_risk_budget
  0.26*1*1.7; sleeve_gross_cap G=2.0; bear books (BTC 4h open < 1200-bar mean
  halves LONG targets; standard rows, before shifted-clock ffill).
- Gate costs (engine): maker 0.0002, taker 0.00055 (stops/market taker), longs
  pay 0.0001/8h, shorts 0. Limits fill only on 1m trade-through, nothing in the
  first 5 min after a 4h close on base (win_start=5); stop-first in a shared 1m
  bar (engine handles).

## Frictions (exactly as robust_v421.py / oc_c2bybit; one knob each)

- S1 cost stress: MAKER 0.0004 / TAKER 0.0012 (0.0007+0.0005) patched via
  `eu.simulate.__globals__`, restored after (robust_v421.py line ~284).
- S2 latency 15/16: win_start=15, sleeve_start=16.
- S3 latency 30/31: win_start=30, sleeve_start=31.
- S4 stop slip 50%: win_start=5, stop_slip=0.5.
- S5 Bybit prices from 2021-11-15: `bybit_minutes()` from the Bybit dir instead
  of `pod.minutes()`; live0 = 2021-11-15 + shift; standard index filtered to
  >= 2021-11-15 before shift; run with win_start=5 (base fills). Year 2021 is a
  SHORT window (labelled everywhere). If Bybit files are missing/unreadable,
  report S5 as not reproducible (no silent fallback).
- Base = win_start=5, no other change.

## Windows / metrics (fixed)

- Anchors 2021..2025-09-24; dev4 = years 0..3 ([A,A+365d)); Y4 = 2025-09-24..
  2026-09-23 (clean BUT already scored once by oc_downshare for base+D1 — every
  Y4 number here, including base, is a labelled diagnostic re-score under
  frictions, never a selection input); 5y = years 0..4.
- Per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4/5y geo
  mean, W (worst-year R), max yearly DD, losing count; full-path DD via
  `v388.mix` equal-1/4 mix from 2021-09-24 (max of reset DDs and full-path for
  the gate); pooled book/rung/all win rates + fills/year + sized mean
  multiplier (same collection as oc_downshare run_engine.py).
- C2 side-by-side: read oc_c2bybit tmp/c2bybit_table.json (REF/C2 x base/S1..S5
  dev4/Y4/5y + gaps); never rerun C2 here.
- D1-vs-C2 multiplier Spearman per year (frozen, CPU-only): on the intersection
  of frozen feature rows (majors, all 4 shifts, T in year y) with both risk_D1
  and ch_q10 present, compute D1 mult (oc_downshare D1 fit of anchor y) and C2
  mult (oc_chronos C2 fit of anchor y) via assign_mult 1.25/0.75, then Spearman
  rho + n per year (scipy or rank-corr pure; ties handled; NaN risks -> mult 1
  included as 1). Answers: are they different signals? Low |rho| = different.
- Reproduction gate (STOP if failed): base REF years 0..4 R/DD ==
  v421_result.json G2 [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27),
  (4.648/12.90)] to the digit, 5y 5.410, full-path DD 16.82; base D1 years ==
  oc_downshare REPORT/results.json (dev 2.921/12.59, 3.604/16.09, 6.541/15.74,
  10.191/8.19; Y4 4.591/13.38; full-path dev 15.98 / full 15.98) to the digit;
  REF_S1..S5 == v421_audit ROBUST.md G2 friction row to the digit (same values
  asserted in oc_c2bybit REPORT section 0).
- Verdict rule (fixed): D1 robust iff D1-REF gap > 0 on dev4 mean AND on 5y
  mean under base AND under EVERY friction S1..S5 (gaps reported per friction),
  with D1 full-path DD <= 20 (per friction; S5 labelled). 3-line Vietnamese
  verdict in REPORT.md.

## Leakage / contamination (pre-registered checks, stated in REPORT)

- Feature timing: downside share for bar open T uses ONLY the 36 closes ending
  at bars closing <= T on that shift's grid (inherited oc_downshare Part A);
  tilt uses only (coin, holding-bar T) risk_D1. Truncation test: recompute D1
  multipliers from a truncated frozen feature table — identical on the kept
  prefix; multiset subset of {0.75, 1.0, 1.25}.
- Label windows: fits.json reused frozen (harness rows t_exit < A - 7d,
  shift-0 only); year y uses anchor-y fit only, never a later anchor.
- Fit windows: no refit here; 2022/2023 direction -1 is the frozen Spearman
  outcome, not a choice; S5 is a price-source switch, not a fit.
- Fill timing: win_start/sleeve_start/stop_slip per friction asserted in
  `test_friction_constants_match_robust_v421` (S1 globals patch + restore in
  source; S5 live0 2021-11-15 + Bybit dir); engine fills only on 1m
  trade-through with stop-first (inherited harness).
- Contamination caveat next to EVERY dev number: downside-share uses only
  existing 4h closes (no model, no pretraining) -> NO contamination risk; C2
  (Chronos-Bolt released 2024-11) dev is still labelled possibly-contaminated
  in the side-by-side column; the post-release year (2025-09-24..2026-09-23) is
  clean for both (but already scored once for base+D1 -> diagnostic re-score here).
- Spearman uses only frozen anchor-y fits + frozen features (no test statistic
  feeds any choice).

## Compute plan (heavy_slot, resume-safe)

- `tilt_rule.py`: pure `assign_mult` + `anchor_of` copy (unit-tested).
- `compute_d1bybit_engine.py`: sequential shifts 0..3 per friction (one heavy
  process at a time), heartbeat print every 600 s, caches
  `tmp/runs_<fric>.pkl` (resume-safe: skip cached shifts), final
  `tmp/runs_all.pkl` (optional merge). Invoked as
  `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_d1bybit_eng
  --min-free-gb 2.0 -- .venv/Scripts/python.exe
  research/tournament/oc_d1bybit/compute_d1bybit_engine.py [--fric ...]`.
- `analyze_d1bybit.py`: CPU-only scoring (reset metric + v388.mix + wins) ->
  `tmp/d1bybit_table.json`; Spearman D1-vs-C2 per year -> same table;
  REPORT.md + results.json written from that table only.
- Deliverables: PLAN.md (this file), tilt_rule.py, compute_d1bybit_engine.py,
  analyze_d1bybit.py, results.json, REPORT.md, tests/test_oc_d1bybit.py.

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the
  original row stays and the change is a disclosed extra row.)
