# oc_k2bybit — PLAN (pre-registered 2026-10-07, BEFORE any outcome)

Assignment: `docs/opencode/OPENCODE_W_oc_k2bybit.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md read). Write ONLY `research/tournament/oc_k2bybit/`
+ `tests/test_oc_k2bybit.py`. Engine runs via heavy_slot. Progress heartbeat every
10 minutes (600 s). Scratch only under `research/tournament/oc_k2bybit/tmp/`.

## Question

Does the Kronos K2 dip tilt keep its edge on BYBIT prices (S5) and under the
other frictions? Context (given, not recomputed): `oc_kronoshidden` K2 = dip rung
size x1.25 / x0.75 on the outer quintiles of -low1, per-anchor fits in
fits.json, engine mechanism copied from v414; `oc_k2placebo` post-release timing
percentile 97.2; a paper runner with K2 runs now (paper_d17bfg2k2);
`oc_amihudrobust` showed a book tilt can vanish on Bybit prices (S5).

## Frozen inputs (read-only, never edited, never copied with changes)

- `research/tournament/oc_kronoshidden/kronos_features_4shift.parquet` (sym, shift,
  T, low1 + others; 260,325 rows; used ONLY low1 here).
- `research/tournament/oc_kronoshidden/fits.json` (per-anchor direction +1 all five
  anchors, q20/q80 of risk = -low1; anchor-2025 fit for the post-release year).
- `research/tournament/oc_kronoshidden/REPORT.md` + `results.json` + `tmp/dev_table.json`
  + `tmp/last_table.json` (expected REF/K2 numbers for the reproduction gate).
- `research/tournament/oc_kronoshidden/run_engine.py` + `tilt_rule.py` (mechanism
  + `assign_mult` copied verbatim into this folder; no behaviour change on base).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` +
  `v421_result.json` row R2B1D17BFG2 (G2 baseline).
- `research/parallel/rounds/parallel-20260906-r2/v421_audit/robust_v421.py` +
  `ROBUST.md` (friction defs S1..S5; copied exactly) and
  `research/tournament/oc_amihudrobust/compute_robust_engine.py` (S5 Bybit
  loading pattern `bybit_minutes()`).
- `data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet` (SYM in BTC/ETH/SOL/BNB/XRP;
  cols open_time ms, open/high/low/close) for S5 only.

## Variants (ONLY these; no selection, no tuning, no extra knob)

- REF = G2 unchanged (R2B1D17BFG2: rule inv, k 1.0, kd 1.7, bear True, G 2.0).
- K2 = REF + K1-rule with 1.25 / 0.75: risk = -low1; per anchor A fit from
  fits.json (direction, q20, q80); mult hi=1.25 favourable outer quintile /
  lo=0.75 unfavourable / 1 else; missing/NaN risk -> 1. Fits of anchor A
  applied to all four shifts in year A (year y = [ANCH5[y]+sh,
  min(+365d, live1)); ANCH5 = 2021..2025-09-24).
- Rows (12 engine rows): REF_base, K2_base, REF_S1, K2_S1, REF_S2, K2_S2,
  REF_S3, K2_S3, REF_S4, K2_S4, REF_S5, K2_S5.
- If anything changes after seeing an outcome, the original row stays and the
  change is added as a disclosed extra row (none planned).

## Mechanism (exact copy of oc_kronoshidden/run_engine.py on base)

- 4 phases (shifts 0..3, 4h grid opens at s, s+4, ... UTC); pipe v321 via
  phase_offset_full.pipe_setup; corr-aware dip sizes mult 1/(1+n)*1.7*tilt*base
  (n = coins with C<=O*(1-2.5*sig)); risk_mult 1.0; sleeve_risk_budget
  0.26*1*1.7; sleeve_gross_cap G=2.0; bear books (BTC 4h open < 1200-bar mean
  halves LONG targets; standard rows, before shifted-clock ffill).
- Gate costs (engine): maker 0.0002, taker 0.00055 (stops/market taker), longs
  pay 0.0001/8h, shorts 0. Limits fill only on 1m trade-through, nothing in the
  first 5 min after a 4h close on base (win_start=5); stop-first in a shared 1m
  bar (engine handles).

## Frictions (exactly as robust_v421.py / oc_amihudrobust; one knob each)

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
  2026-09-23 (clean BUT already scored once by oc_kronoshidden for base — every
  Y4 number here, including base, is a labelled diagnostic re-score, never a
  selection input); 5y = years 0..4.
- Per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4/5y geo
  mean, W (worst-year R), max yearly DD, losing count; full-path DD via
  `v388.mix` equal-1/4 mix from 2021-09-24 (max of reset DDs and full-path for
  the gate); pooled book/rung/all win rates + fills/year + sized mean
  multiplier (same collection as oc_kronoshidden run_engine.py).
- Reproduction gate (STOP if failed): base REF years 0..4 R/DD ==
  v421_result.json G2 [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27),
  (4.648/12.90)] to the digit, 5y 5.410, full-path DD 16.82; base K2 years ==
  oc_kronoshidden REPORT Table (dev 2.469/11.78, 3.478/16.20, 6.679/15.69,
  10.653/8.54; Y4 4.801/12.10; full-path dev 16.09 / full 16.09*) to the digit.
  (*full-path over 2021-09-24..Y1; dev full-path over dev window; both checked.)
- Verdict rule (fixed): K2 robust iff K2-REF gap > 0 on dev4 mean AND on 5y
  mean under base AND under EVERY friction S1..S5 (gaps reported per friction),
  with K2 full-path DD <= 20 (per friction; S5 labelled). 3-line Vietnamese
  verdict in REPORT.md.

## Leakage / contamination (pre-registered checks, stated in REPORT)

- Feature timing: Kronos forecast for bar open T uses ONLY the 400 bars closing
  <= T on that shift's grid (inherited Part A); tilt uses only (coin,
  holding-bar T) low1. Truncation test: recompute K2 multipliers from a
  truncated feature table (assert identical on the kept prefix).
- Label windows: harness t_exit < A - 7d inherited for fits (not recomputed);
  engine uses the realised 1m path; no label fit here.
- Fit windows: fits.json reused frozen (shift-0 only + 7d embargo); year y uses
  anchor-y fit only, never a later anchor; no statistic from any test year
  feeds any choice (S5 grid change is a price-source switch, not a fit).
- Fill timing: win_start per friction + 1m trade-through + stop-first (engine);
  tests assert the friction constants in the engine script.
- Contamination caveat next to EVERY dev number: dev years likely IN Kronos
  pretraining (released 2025-08) -> UPPER BOUND; Y4 is the only clean year (but
  already scored once for base -> diagnostic re-score here).

## Compute plan (heavy_slot, resume-safe)

- `tilt_rule.py`: pure `assign_mult` + `anchor_of` copy (unit-tested).
- `compute_k2bybit_engine.py`: sequential shifts 0..3 per friction (one heavy
  process at a time), heartbeat print every 600 s, caches
  `tmp/runs_<fric>.pkl` (resume-safe: skip cached shifts), final
  `tmp/runs_all.pkl`. Invoked as
  `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_k2bybit_eng
  --min-free-gb 2.0 -- .venv/Scripts/python.exe
  research/tournament/oc_k2bybit/compute_k2bybit_engine.py [--fric ...]`.
- `analyze_k2bybit.py`: CPU-only scoring (reset metric + v388.mix + wins) ->
  `tmp/k2bybit_table.json`; REPORT.md + results.json written from that table
  only.
- Deliverables: PLAN.md (this file), tilt_rule.py, compute_k2bybit_engine.py,
  analyze_k2bybit.py, results.json, REPORT.md, tests/test_oc_k2bybit.py.

## Post-hoc log

- 2026-10-07 pre-outcome (before any engine run): fixed shared-dict
  `pop("win_start")` -> fresh `dict(fric_extra(fric))` copy per variant (would
  have reset S2/S3 latency on the 2nd variant) + comment cleanup. No rows,
  thresholds, fits, or gates touched.
- 2026-10-07 post-outcome: no definition changes. All 12 rows scored as
  pre-registered; reproduction gates passed to the digit (REF_base==v421 G2,
  K2_base==oc_kronoshidden K2, REF_S1..S5==ROBUST.md G2).
