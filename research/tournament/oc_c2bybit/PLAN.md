# oc_c2bybit — PLAN (pre-registered 2026-10-08, BEFORE any outcome)

Assignment: `docs/opencode/OPENCODE_W_oc_c2bybit.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md read). Write ONLY `research/tournament/oc_c2bybit/`
+ `tests/test_oc_c2bybit.py`. Engine runs via heavy_slot (one engine job at a time;
RAM tight). Progress heartbeat every 10 minutes (600 s). Scratch only under
`research/tournament/oc_c2bybit/tmp/`.

## Question

Does the Chronos C2 dip tilt keep its edge under frictions and on BYBIT prices (S5)?
Context (given, not recomputed): `oc_chronos` C2 = dip rung size x1.25 / x0.75 on the
outer quintiles of risk = -ch_q10 (Chronos-Bolt-small ch_q10, per-anchor fits in
oc_chronos/fits.json; engine mechanism run_engine.py / tilt_rule.py) is the dev4
robust pick (dev4 mean 5.739, WORST 2.711 vs K2 5.772/2.469 — picked on highest
WORST). `oc_k2bybit` did exactly this check for K2 — copy its harness
(compute_k2bybit_engine.py, analyze_k2bybit.py) and swap the multipliers (Kronos
low1 -> Chronos ch_q10, frozen oc_chronos fits.json).

## Frozen inputs (read-only, never edited, never copied with changes)

- `research/tournament/oc_chronos/chronos_features_4shift.parquet` (sym, shift, T,
  ch_q10 + others; 258,085 rows; used ONLY ch_q10 here).
- `research/tournament/oc_chronos/fits.json` (per-anchor direction +1 all five
  anchors, q20/q80 of risk = -ch_q10; anchor-2025 fit for the post-release year).
  C2 fits: 2021 dir+1 rho 0.0364 q20 1.1101 q80 2.8608; 2022 +1 0.0760 1.1847
  3.0251; 2023 +1 0.1287 1.0736 2.7737; 2024 +1 0.1187 1.0644 2.6502;
  2025 +1 0.1126 1.0743 2.5977.
- `research/tournament/oc_chronos/REPORT.md` + `results.json` + `tmp/dev_table.json`
  + `tmp/last_table.json` (expected REF/C2 numbers for the reproduction gate).
- `research/tournament/oc_chronos/run_engine.py` + `tilt_rule.py` (mechanism
  + `assign_mult` copied verbatim into this folder; no behaviour change on base).
- `research/tournament/oc_k2bybit/tmp/k2bybit_table.json` + REPORT.md + results.json
  (K2 side-by-side numbers; read-only, never recomputed here).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` +
  `v421_result.json` row R2B1D17BFG2 (G2 baseline: 5.41 %/mo, max yearly DD 16.91,
  full-path DD 16.82).
- `research/parallel/rounds/parallel-20260906-r2/v421_audit/robust_v421.py` +
  `ROBUST.md` (friction defs S1..S5; copied exactly) and
  `research/tournament/oc_amihudrobust/compute_robust_engine.py` (S5 Bybit
  loading pattern `bybit_minutes()`).
- `data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet` (SYM in BTC/ETH/SOL/BNB/XRP;
  cols open_time ms, open/high/low/close) for S5 only.

## Variants (ONLY these; no selection, no tuning, no extra knob)

- REF = G2 unchanged (R2B1D17BFG2: rule inv, k 1.0, kd 1.7, bear True, G 2.0).
- C2 = REF + Chronos C2 tilt: risk = -ch_q10; per anchor A fit from oc_chronos
  fits.json (direction, q20, q80); mult hi=1.25 favourable outer quintile /
  lo=0.75 unfavourable / 1 else; missing/NaN risk -> 1. Fits of anchor A
  applied to all four shifts in year A (year y = [ANCH5[y]+sh,
  min(+365d, live1)); ANCH5 = 2021..2025-09-24).
- Rows (12 engine rows): REF_base, C2_base, REF_S1, C2_S1, REF_S2, C2_S2,
  REF_S3, C2_S3, REF_S4, C2_S4, REF_S5, C2_S5.
- If anything changes after seeing an outcome, the original row stays and the
  change is added as a disclosed extra row (none planned).

## Mechanism (exact copy of oc_chronos/run_engine.py on base = oc_kronoshidden pipe)

- 4 phases (shifts 0..3, 4h grid opens at s, s+4, ... UTC); pipe v321 via
  phase_offset_full.pipe_setup; corr-aware dip sizes mult 1/(1+n)*1.7*tilt*base
  (n = coins with C<=O*(1-2.5*sig)); risk_mult 1.0; sleeve_risk_budget
  0.26*1*1.7; sleeve_gross_cap G=2.0; bear books (BTC 4h open < 1200-bar mean
  halves LONG targets; standard rows, before shifted-clock ffill).
- Gate costs (engine): maker 0.0002, taker 0.00055 (stops/market taker), longs
  pay 0.0001/8h, shorts 0. Limits fill only on 1m trade-through, nothing in the
  first 5 min after a 4h close on base (win_start=5); stop-first in a shared 1m
  bar (engine handles).

## Frictions (exactly as robust_v421.py / oc_k2bybit; one knob each)

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
  2026-09-23 (clean BUT already scored once by oc_chronos for base+C2 — every
  Y4 number here, including base, is a labelled diagnostic re-score under
  frictions, never a selection input); 5y = years 0..4.
- Per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4/5y geo
  mean, W (worst-year R), max yearly DD, losing count; full-path DD via
  `v388.mix` equal-1/4 mix from 2021-09-24 (max of reset DDs and full-path for
  the gate); pooled book/rung/all win rates + fills/year + sized mean
  multiplier (same collection as oc_chronos run_engine.py).
- K2 side-by-side: read oc_k2bybit tmp/k2bybit_table.json (REF/K2 x base/S1..S5
  dev4/Y4/5y + gaps); never rerun K2 here.
- Reproduction gate (STOP if failed): base REF years 0..4 R/DD ==
  v421_result.json G2 [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27),
  (4.648/12.90)] to the digit, 5y 5.410, full-path DD 16.82; base C2 years ==
  oc_chronos REPORT/results.json Table (dev 2.711/11.52, 3.460/15.48,
  6.250/15.07, 10.721/8.29; Y4 4.754/12.86; full-path dev 15.42 / full 15.42)
  to the digit.
- Verdict rule (fixed): C2 robust iff C2-REF gap > 0 on dev4 mean AND on 5y
  mean under base AND under EVERY friction S1..S5 (gaps reported per friction),
  with C2 full-path DD <= 20 (per friction; S5 labelled). 3-line Vietnamese
  verdict in REPORT.md.

## Leakage / contamination (pre-registered checks, stated in REPORT)

- Feature timing: Chronos forecast for bar open T uses ONLY the 512 closes
  ending at the bar closing at T on that shift's grid (inherited Part A); tilt
  uses only (coin, holding-bar T) ch_q10. Truncation test: recompute C2
  multipliers from a truncated frozen feature table — identical on the kept
  prefix; multiset ⊂ {0.75, 1.0, 1.25}.
- Label windows: harness t_exit < A - 7d inherited for fits (not recomputed);
  engine uses the realised 1m path; no label fit here.
- Fit windows: fits.json reused frozen (shift-0 only + 7d embargo); year y uses
  anchor-y fit only, never a later anchor; no statistic from any test year
  feeds any choice (S5 grid change is a price-source switch, not a fit).
- Fill timing: win_start/sleeve_start/stop_slip per friction asserted in
  `test_friction_constants_match_robust_v421` (S1 globals patch + restore in
  source; S5 live0 2021-11-15 + Bybit dir); engine fills only on 1m
  trade-through with stop-first (inherited harness).
- Contamination caveat next to EVERY dev number: Chronos-Bolt released 2024-11,
  mostly non-crypto + synthetic pretraining -> LESS contamination risk for
  2021-2024 than Kronos, but dev is still labelled possibly-contaminated; the
  post-release year (2025-09-24..2026-09-23, after BOTH releases) is the clean
  verdict (but already scored once for base -> diagnostic re-score here).

## Compute plan (heavy_slot, resume-safe)

- `tilt_rule.py`: pure `assign_mult` + `anchor_of` copy (unit-tested).
- `compute_c2bybit_engine.py`: sequential shifts 0..3 per friction (one heavy
  process at a time), heartbeat print every 600 s, caches
  `tmp/runs_<fric>.pkl` (resume-safe: skip cached shifts), final
  `tmp/runs_all.pkl`. Invoked as
  `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_c2bybit_eng
  --min-free-gb 2.0 -- .venv/Scripts/python.exe
  research/tournament/oc_c2bybit/compute_c2bybit_engine.py [--fric ...]`.
- `analyze_c2bybit.py`: CPU-only scoring (reset metric + v388.mix + wins) ->
  `tmp/c2bybit_table.json`; REPORT.md + results.json written from that table
  only.
- Deliverables: PLAN.md (this file), tilt_rule.py, compute_c2bybit_engine.py,
  analyze_c2bybit.py, results.json, REPORT.md, tests/test_oc_c2bybit.py.

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the
  original row stays and the change is a disclosed extra row.)
