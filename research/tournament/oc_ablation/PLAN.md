# oc_ablation PLAN (pre-registered BEFORE any outcome, 2026-10-07)

Assignment: docs/opencode/OPENCODE_W_oc_ablation.md + common header
docs/opencode/OPENCODE_W_COMMON_20261007.md + AGENTS.md. This file freezes
every choice before any number is computed. Any change after seeing an
outcome is kept as a disclosed extra row, never a silent edit.

## Deployed reference (frozen)

G2 = `R2B1D17BFG2` in research/parallel/rounds/parallel-20260906-r2/v421
(v421_runs.pkl strat R2B1D17BFG2; v421_result.json):
5y reset R 5.410 / W 2.588 / max-yearly-DD 16.91 / full-path DD 16.82,
no losing year. Years (R %/mo, DD %): 2021 (2.588, 10.86),
2022 (3.282, 16.91), 2023 (6.045, 15.81), 2024 (10.677, 8.27),
2025-09-24 labelled most-recent (4.648, 12.90).
G2 config (v421_gross_cap.py worker, non-REF branch): v321 pipe
(history_tm + v221 + v216 GRID trader, agents ON via per-shift
v376/tables_hidden/r2_table_s{shift}.parquet), books = research_books_d2
with x0.5 bear filter on longs ffill to shifted clocks, corr-size inv/kd=1.7
(mult 1/(1+n) x kd x agent-table base size), risk_mult=1.0,
sleeve budget 0.26*1.0*1.7=0.442, gross cap G=2.0, sleeve ON, trade mode,
win_start=5, default gov (0.20, 0.10), default book vol target (0.25/cap 2.0),
dip close5 stop m_sleeve_sl=4.0 + native backstop 8.0, rungs (2.5,3,3.5,4,5).
Gate costs: maker 0.0002, taker 0.00055 (stops/market exits), longs
0.0001/8h, shorts nothing, limit fill only on 1m trade-through, no fill
minutes 0-4, stop-first on ties.
Metric: reset_metric.year_reset per anchor year (fresh 1.0 at each anchor) +
v388.mix hourly full-path DD (max of close/marked, same as v421).
REPRODUCE the G2 numbers above EXACTLY from a fresh engine run before any
ablation; if reproduction fails, stop and report.

## Pre-registered rows (ONE layer removed per row, all else = G2)

- G2: exact v421 replica (proof row).
- NO_GOV: governor off via engine hook gov=(10.0, 0.10) -> g=clip((10-dd)/0.10)=1
  always (dd in [0,1)). risk_mult=1.0 kept. All else = G2.
- NO_BEAR: bear-book filter off (books = std ffill, no x0.5). All else = G2.
- NO_CAP: dip gross cap off (sleeve_gross_cap=None). All else = G2.
- NO_B1: corr-aware sizing off (sleeve_fill_size = kd x agent-table base size,
  mult w=1; kd=1.7 kept, rule inv dropped). All else = G2.
- NO_VT: book vol-target scale fixed at its long-run median via PATCHED engine
  copy (no clean hook exists for the book leg; rung_scale_fixed exists only
  for dips). Patch = copy of engine_user.py in this folder (engine_patch.py)
  with added kwarg vol_fixed=None; when not None, the per-bar strategy scale
  s[i] is replaced by vol_fixed for BOTH the book target
  (tgt=W_BOOKS*s*books*g) and the dip rung size (rn=s*g*...). When None the
  patch is bit-for-bit the audited engine. Proof: G2 via patch+vol_fixed=None
  must match G2 via original engine to the digit before NO_VT runs.
  vol_fixed per shift = median of G2's per-bar scale s over that shift's live
  window (DEV0+sh .. Y1+sh), computed by replicating the engine s formula
  (target 0.25 / cap 2.0 on trailing 60-day book-P&L vol; identical to the
  bars scale field, which skips non-live bars and misaligns).
  If the patch does not reproduce G2, NO_VT is SKIPPED and stated.
- TOUCH: dip close5 stop replaced by 4-sigma touch stop:
  sleeve_stop_mode="touch", m_sleeve_sl=4.0, sleeve_backstop=8.0 passed
  (unused in touch mode, kept for config parity), risk budget still counts
  4.0*sg+gap. All else = G2.
No other variants. No tuning on outcomes. This is a DIAGNOSTIC ablation:
no selection, dev4 and most-recent year both reported, recent year labelled.

## Engine harness (fixed)

- Per shift s=0..3: M=pod.minutes() once; opens,prep=pof.prep_idx(M,
  books154.index+sh, s, cols); std=fw.research_books_d2(eu); bear flag from
  _opens_std BTC rolling 1200 exactly as v421 lines 69-72; books_bear ffill.
  hist.R2_TABLE=tables_hidden/r2_table_s{s}.parquet; kw,trade=pof.pipe_setup(
  "v321",hist,v221,v216,idx,cols,True); then v421 overrides per row
  (corr/kd/budget/cap/risk_mult as above) + row-specific hook.
- Live window per shift: [DEV0+sh, Y1+sh), Y1=2026-09-23 (v388.Y1), 5 years
  continuous; eu.v110.START/END set accordingly; simulate with trade=trade,
  win_start=5, events captured per row, bars captured per row (for scale
  median + governor check).
- One phase per heavy_slot process is fine: run_shift.py <shift> runs all 7
  rows sequentially for that shift, writes tmp/runs_s{shift}.pkl
  (per row: t/eq/eq_min/stats/bars-scale-median) + tmp/events_s{shift}_{row}.parquet.
  Progress print per row (equity end) ~= every 10 min printing.
- Heavy via: .venv/Scripts/python.exe scripts/heavy_slot.py run
  --tag oc_ablation --min-free-gb 2.0 -- <cmd>. Never --leader.

## Metrics (fixed, per row)

- Per anchor year y=0..4 (A=2021..2025-09-24, each [A,A+365d)):
  reset_metric.year_reset R (%/mo geometric) and DD (marked) on the 4-phase
  mix (fresh 1.0 at each anchor). y=4 labelled most-recent, never selected on.
- 4-phase reset means: dev4 geo mean (y0..3), 5y geo mean, W (min yearly R),
  losing count, max yearly DD (all from year_reset).
- Full-path DD: continuous 4-phase mix from grid start via v388.mix, max of
  close/marked, v421 formula.
- Worst single-phase DD: max over s=0..3 of that phase sub-account's
  full-window max(close DD, 1m-marked DD) from its stored eq/eq_min.
- Engine stats totals per row (fills, rungs, stops/tps, fees, funding) +
  coverage (live bars simulated).
- Gap test (oc_gapstress method, -10% all-coin gap, per row): rebuild open
  book+dip fractions from that row's saved events + hourly_ext marks with
  compute_gapstress.build_state logic (FIFO dips, book flats, qty x mark x
  start-equity/end-equity); loss%=100*(S*0.10+0.00055*G*0.90); 4-phase
  equity-weighted mix on union of sample times; report worst-minute loss%,
  its timestamp, gross/dip/book split, plus loss at G2's worst minute and
  minute-weighted median/p99/max. G2 worst minute is the reference timestamp.

## Table: return bought / DD bought per layer (fixed)

Per row vs G2: dR_dev4 = R_row_dev4 - R_G2_dev4, dR_recent, dDD = DD_row - DD_G2
(max yearly), dFull = full_row - full_G2, dGap = gapRow_worst - gapG2_worst.
A layer "earns its keep" if removing it lowers return and/or raises DD/gap.

## Leakage / causality (fixed)

- Books/sigma/vol-scale/governor/agents all causal per v421 harness; agent
  size/TP keyed by holding bar (decided at bar open); fills win_start=5 +
  trade-through + stop-first; embargo: research_books_d2 members frozen before
  each anchor (same as deployed); no test-year or most-recent-year statistic
  enters any threshold (NO_VT median is per-shift live-window scale, computed
  inside the simulated window, same for every year — disclosed as in-window,
  not pre-anchor; it is a diagnostic constant, not a tuned threshold).
- Gap rebuild uses hourly marks ffill (last CLOSED hourly bar strictly before
  t) and event times only.

## Outputs (ONLY these paths)

- research/tournament/oc_ablation/PLAN.md (this file), run_shift.py,
  engine_patch.py (copy+vol_fixed only), analyze_ablation.py,
  compute_gap.py, REPORT.md, results.json, tmp/ snippets.
- tests/test_oc_ablation.py (>=1 causality/truncation test + >=1 synthetic
  hand-checked case; run with .venv/Scripts/python.exe -m pytest -q).
