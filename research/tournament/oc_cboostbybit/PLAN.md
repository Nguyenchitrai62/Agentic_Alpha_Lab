# oc_cboostbybit — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_cboostbybit.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md read in full).
Write ONLY `research/tournament/oc_cboostbybit/` + `tests/test_oc_cboostbybit.py`. Scratch only under
`research/tournament/oc_cboostbybit/tmp/`. GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/
rm/commit/switch/rebase/merge. Engine / heavy 1m work via `scripts/heavy_slot.py` (RAM tight: one engine
job at a time, sequential shifts, one heavy process). Long jobs: nohup + log file under tmp/, poll the log.
Heartbeat print every 600 s in long jobs. Progress print every 10 minutes.

## Question

Does B7 keep its edge under frictions and on BYBIT prices (S5)?

Context (given, not recomputed): `research/tournament/oc_cascadeboost` B7 = dip budget x1.5 for 7 days
after a cascade bar (> 4 sigma 4h close-to-close move, definition of oc_cascadedelay) is the dev4 robust
pick (mean 6.74 / WORST 2.96 / DD 17.92 vs G2 5.60 / 2.59 / 16.91; 5y 6.36).
CONTAMINATION (pre-registered here, before any outcome): the idea was formed after oc_cascadedelay's
replica had covered all five years incl. the post-release year, so post-release numbers are labelled
diagnostics and new evidence must come from controls, unseen years, frictions and prospective paper.
This label is stated here BEFORE any outcome and repeated in REPORT.md / results.json.

## Variants (ONLY these two; no selection, no tuning, no extra knob)

- REF = G2 unchanged (R2B1D17BFG2: rule inv, k 1.0, kd 1.7, bear True, G 2.0; mult 1).
- B7 = REF + cascade boost: dip rung size x mult_B7(T, shift) (1.5 in the 7d window after any >4sg 4h
  bar, else 1.0; market-wide per shift, same for all 5 coins at (shift, T); book byte-identical).
  B3 is NOT run here (cascadeboost showed B3 strictly weaker on dev4 on every metric).
- Rows (12 engine rows): REF_base, B7_base, REF_S1, B7_S1, REF_S2, B7_S2, REF_S3, B7_S3, REF_S4, B7_S4,
  REF_S5, B7_S5.
- If anything changes after seeing an outcome, the original row stays and the change is added as a
  disclosed extra row (none planned).

## Frozen inputs (read-only, never edited, never refit)

- `research/tournament/oc_cascadeboost/boost_mult_4shift.parquet` (shift, T, mult_B7; 53,877 rows;
  closes-only |r|>4*SIG(540,min120) triggers, union over 5 majors per shift: s0 264 / s1 266 / s2 263 /
  s3 255 — reused VERBATIM; missing mult -> 1.0, counted).
- `research/tournament/oc_cascadeboost/REPORT.md` + `results.json` + `tmp/dev_table.json` +
  `tmp/last_table.json` (expected REF/B7 numbers for the reproduction gate; see below).
- `research/tournament/oc_cascadeboost/run_engine.py` + `boost_rule.py` (mechanism + mult lookup copied
  verbatim into this folder; no behaviour change on base).
- `research/tournament/oc_c2bybit/compute_c2bybit_engine.py` + `analyze_c2bybit.py` (friction harness
  S1..S5 copied exactly; only the tilt lookup is swapped for the frozen boost mult).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` + `v421_result.json` row
  R2B1D17BFG2 (G2 baseline: dev years [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)],
  Y4 (4.648/12.90), 5y 5.410, max yearly DD 16.91, full-path DD 16.82).
- `research/parallel/rounds/parallel-20260906-r2/v421_audit/robust_v421.py` + `ROBUST.md` (friction defs
  S1..S5; copied exactly) and `research/tournament/oc_amihudrobust/compute_robust_engine.py` (S5 Bybit
  loading pattern `bybit_minutes()`).
- `data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet` (SYM in BTC/ETH/SOL/BNB/XRP; cols open_time ms,
  open/high/low/close) for S5 only.

## Mechanism (exact copy of oc_cascadeboost/run_engine.py on base = oc_chronos pipe = v414 pipe v321)

- 4 phases (shifts 0..3, 4h grid opens at s, s+4, ... UTC); pipe v321 via phase_offset_full.pipe_setup;
  corr-aware dip sizes mult 1/(1+n)*1.7*boost*base (n = coins with C<=O*(1-2.5*sig)); risk_mult 1.0;
  sleeve_risk_budget 0.26*1*1.7; sleeve_gross_cap G=2.0; bear books (BTC 4h open < 1200-bar mean halves
  LONG targets; standard rows, before shifted-clock ffill).
- Gate costs (engine): maker 0.0002, taker 0.00055 (stops/market taker), longs pay 0.0001/8h, shorts 0.
  Limits fill only on 1m trade-through, nothing in the first 5 min after a 4h close on base
  (win_start=5); stop-first in a shared 1m bar (engine handles).

## Frictions (exactly as robust_v421.py / oc_c2bybit; one knob each)

- S1 cost stress: MAKER 0.0004 / TAKER 0.0012 (0.0007+0.0005) patched via `eu.simulate.__globals__`,
  restored after (robust_v421.py line ~284).
- S2 latency 15/16: win_start=15, sleeve_start=16.
- S3 latency 30/31: win_start=30, sleeve_start=31.
- S4 stop slip 50%: win_start=5, stop_slip=0.5.
- S5 Bybit prices from 2021-11-15: `bybit_minutes()` from the Bybit dir instead of `pod.minutes()`;
  live0 = 2021-11-15 + shift; standard index filtered to >= 2021-11-15 before shift; run with
  win_start=5 (base fills). Year 2021 is a SHORT window (labelled everywhere). If Bybit files are
  missing/unreadable, report S5 as not reproducible (no silent fallback).
- Base = win_start=5, no other change.

## Windows / metrics (fixed)

- Anchors 2021..2025-09-24; dev4 = years 0..3 ([A,A+365d)); Y4 = 2025-09-24..2026-09-23 (CONTAMINATED:
  B7 idea formed after seeing oc_cascadedelay replica incl. this year — every Y4 number here, including
  base, is a labelled DIAGNOSTIC re-score under frictions, never a selection input); 5y = years 0..4.
- Per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4/5y geo mean, W (worst-year R), max
  yearly DD, losing count; full-path DD via `v388.mix` equal-1/4 mix from 2021-09-24 (max of reset DDs
  and full-path for the gate); worst 1m-marked DD episode per row (peak/trough/depth on
  dd(t) = 1 - ms(t)/peak(es)(t)); pooled book/rung/all win rates + fills/year + sized mean multiplier
  (same collection as oc_cascadeboost run_engine.py).
- Reproduction gate (STOP if failed): base REF years 0..4 R/DD == v421_result.json G2
  [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27),(4.648/12.90)] to the digit, 5y 5.410,
  full-path DD 16.82; base B7 years == oc_cascadeboost results.json
  [dev (2.955/14.67),(3.264/17.92),(8.537/15.94),(12.486/11.01); Y4 4.88/13.81; full-path dev 17.75 /
  full 17.75; dev4 6.738/W 2.955; 5y 6.364] to the digit. REF_S1..S5 should equal v421_audit ROBUST.md
  G2 friction row to the digit (S1 4.571/17.45/17.37, S2 5.212/16.91/16.86, S3 4.578/17.32/17.24,
  S4 4.898/17.31/17.24, S5 4.883/18.11/18.09) as a second harness check.
- Verdict rule (fixed): B7 robust iff B7-REF gap > 0 on dev4 mean AND on 5y mean under base AND under
  EVERY friction S1..S5 (gaps reported per friction), with B7 full-path DD <= 20 (per friction; S5
  labelled). 3-line Vietnamese verdict in REPORT.md.

## Leakage / contamination (pre-registered checks, stated in REPORT)

- Feature timing: cascade triggers use closes with close_time <= tc only (SIG window excludes the tested
  bar; boost window strictly after tc 0 < T-tc <= 7d). Truncation test: recompute triggers from truncated
  bars -> identical on kept prefix; multiset subset of {1.0, 1.5}.
- Label windows: no labels fit anywhere in this study (no harness join).
- Fit windows: no fits; threshold 4.0, windows 540/120, boost 1.5, N=7 all frozen ex-ante, never scanned;
  no statistic from any test year feeds any choice (S5 grid change is a price-source switch, not a fit).
- Fill timing: win_start/sleeve_start/stop_slip per friction asserted in
  `test_friction_constants_match_robust_v421` (S1 globals patch + restore in source; S5 live0 2021-11-15
  + Bybit dir); engine fills only on 1m trade-through with stop-first (inherited harness).
- Contamination caveat next to EVERY Y4/post-release number: B7 idea formed AFTER oc_cascadedelay replica
  covered all five years incl. the post-release year -> Y4 is a LABELLED DIAGNOSTIC (not clean evidence);
  new evidence here comes from frictions + Bybit prices only; only prospective paper could confirm B7.

## Compute plan (heavy_slot, resume-safe)

- `boost_rule.py`: pure helpers copied VERBATIM from oc_cascadeboost (`close_returns`, `trailing_sigma`,
  `triggers_of`, `boosted_mask`, `anchor_of`; BOOST 1.5, B7_DAYS 7) — no data access; unit-tested.
- `compute_cboostbybit_engine.py`: sequential shifts 0..3 per friction (one heavy process at a time),
  heartbeat print every 600 s, caches `tmp/runs_<fric>.pkl` (resume-safe: skip cached shifts), final
  `tmp/runs_all.pkl`. Invoked as `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_cboostbybit_eng
  --min-free-gb 2.0 -- .venv/Scripts/python.exe research/tournament/oc_cboostbybit/compute_cboostbybit_engine.py
  [--fric ...]`. Long frictions: nohup + log under tmp/, poll the log.
- `analyze_cboostbybit.py`: CPU-only scoring (reset metric + v388.mix + wins + worst marked episode) ->
  `tmp/cboostbybit_table.json`; REPORT.md + results.json written from that table only.
- Deliverables: PLAN.md (this file), boost_rule.py, compute_cboostbybit_engine.py, analyze_cboostbybit.py,
  results.json, REPORT.md, tests/test_oc_cboostbybit.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_cboostbybit.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row stays and the
  change is a disclosed extra row.)
