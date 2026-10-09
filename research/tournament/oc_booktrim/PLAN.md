# oc_booktrim — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_booktrim.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md read). Write ONLY `research/tournament/oc_booktrim/`
+ `tests/test_oc_booktrim.py`. Engine runs via heavy_slot (one engine job at a time;
RAM tight). Progress heartbeat every 10 minutes (600 s). Scratch only under
`research/tournament/oc_booktrim/tmp/`.

## Question

Is G2's book over-sized? Book and dip share the gross cap 2.0, so a smaller book
leaves room for more dip fills, which earn more per unit of gross. Several studies'
exposure-matched constant controls (uniform book scale < 1, e.g. ~0.8-0.95, built
from each study's realised scale) beat G2 on dev4 mean: oc_memberagree C08 5.861,
oc_spillgate 5.832/5.707, oc_volvolbrake 5.830/5.821, oc_decayexit 5.751 vs G2
5.601. CAUTION (assignment): those controls were built from each study's realised
scale; this task tests the trim directly with constants fixed in advance.

## Variants (exactly two + reference; constants fixed now, no tuning)

- REF = G2 unchanged (R2B1D17BFG2: rule inv, k 1.0, kd 1.7, bear True, G 2.0,
  no book_mult key in the trade dict).
- BT08 = REF + `trade["book_mult"] = 0.8` (every book target x0.8).
- BT06 = REF + `trade["book_mult"] = 0.6` (every book target x0.6).
- Everything else exactly G2 (dip sleeve, caps, carry off). Dip leg byte-identical
  mechanics; only the shared gross path changes via a smaller book.
- Rows (6 engine rows): REF_base, BT08_base, BT06_base, REF_S5, BT08_S5, BT06_S5.
- If anything changes after seeing an outcome, the original row stays and the
  change is added as a disclosed extra row (none planned).

## Mechanism (verbatim G2 = oc_c2bybit base harness = v421 worker)

- 4 phases (shifts 0..3, 4h grid opens at s, s+4, ... UTC); pipe v321 via
  phase_offset_full.pipe_setup; corr-aware dip sizes mult 1/(1+n)*1.7*base
  (n = coins with C<=O*(1-2.5*sig)); risk_mult 1.0; sleeve_risk_budget
  0.26*1*1.7; sleeve_gross_cap G=2.0; bear books (BTC 4h open < 1200-bar mean
  halves LONG targets; standard rows, before shifted-clock ffill).
- Book leg: `trade["book_mult"]` scales every book target (signal threshold uses
  the unscaled target; engine_user line ~230). REF omits the key (= 1.0).
- Gate costs (engine): maker 0.0002, taker 0.00055 (stops/market taker), longs
  pay 0.0001/8h, shorts 0. Limits fill only on 1m trade-through, nothing in the
  first 5 min after a 4h close (win_start=5); stop-first in a shared 1m bar
  (engine handles).

## Frictions (two price sources; S5 exactly as oc_c2bybit / robust_v421)

- base (Binance): `pod.minutes()`; live0 = 2021-09-24 + shift; win_start=5.
- S5 (Bybit): `bybit_minutes()` from `data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet`
  instead of `pod.minutes()`; live0 = 2021-11-15 + shift; standard index filtered
  to >= 2021-11-15 before shift; win_start=5. Year 2021 on S5 is a SHORT window
  (labelled everywhere). If Bybit files are missing/unreadable, report S5 as not
  reproducible (no silent fallback).

## Windows / metrics / selection (fixed)

- Anchors 2021..2025-09-24; dev4 = years 0..3 ([A,A+365d)); Y4 = 2025-09-24..
  2026-09-23; 5y = years 0..4.
- Staging (selection discipline): stage dev runs [DEV0, DEV1=2025-09-24) for
  REF/BT08/BT06 on base+S5 -> robust pick on dev4 Binance base ONLY. Stage last
  runs [DEV0, Y1=2026-09-23) ONCE for the pick + REF on base+S5 (every Y4 number
  labelled scored-once; the losing variant's Y4 is never computed).
- Per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4/5y geo
  mean, W (worst-year R), max yearly DD, losing count; full-path DD via
  `v388.mix` equal-1/4 mix from 2021-09-24 (max of reset DDs and full-path for
  the gate); pooled book/rung/all win rates + fills/year (same collection as
  oc_chronos run_engine.py: trade_stats book nb/wb + rung_tp/sl/timeout nr/wr).
- Reproduction gate (STOP if failed): REF_base dev years 0..3 R/DD ==
  v421_result.json G2 [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)]
  to the digit; REF_base full-window 5y 5.410 + full-path DD 16.82; REF_S5 ==
  oc_c2bybit tmp/c2bybit_table.json REF_S5 (R + DD per year) to the digit.
- Robust pick (fixed, COMMON header): among REF/BT08/BT06 with dev4 DD <= 20 and
  no losing dev year, prefer dev4 mean >= 5 %/mo (if any), then the highest dev4
  WORST-year monthly return, ties -> higher mean.

## Decomposition (fixed, answers "does the dip leg actually gain fills?")

Per phase run collect `attrib` (per live bar: per-asset book PnL array + sleeve
PnL, fractions of bar-start equity) and `events` (rung_fill with weight w =
notional/equity + rung_tp/sl/timeout exits with ret; fill immediately followed
by its exit in the list, so pairs are consecutive per rung):

- book_pnl_y / dip_pnl_y: sum of attrib book (sum over assets) / sleeve entries
  with anchor_y <= t < anchor_y+365d, pooled over 4 phases (mean per phase).
  Labelled attrib-sum (non-compounded fractions of bar-start equity; leg-share
  diagnostic, NOT the reset %/mo).
- dip fills_y: count of rung_fill events per anchor year, pooled 4 phases; mean
  rung weight per year.
- gross-cap binds: rebuild rung intervals (fill_t, exit_t, w) per phase from the
  consecutive fill/exit pairs; for each fill in time order C_before = sum of w
  of intervals with fill_t <= t < exit_t excluding itself; near = C_before >=
  1.5 (within 0.5 of G=2.0); over = C_before + w > 2.0 + 1e-9 (cut evidence;
  engine cuts to room so realised over ≈ 0). Report fills_total, near count +
  share, over count, max concurrent gross per phase. Skips leave no event, so
  this is a lower bound on cap pressure (disclosed).
- Also report stats["rungs"] per phase sanity sum vs rung_fill counts.

## Leakage / contamination (pre-registered checks, stated in REPORT)

- Feature timing: no new feature; books are the frozen v154/research_books_d2
  pipeline (decision at 4h close uses only data available then; inherited G2).
  Truncation test: rerun the book_mult wiring check on truncated books is N/A;
  instead the causality test asserts trade["book_mult"] only scales targets and
  the synthetic test hand-checks scaling (below).
- Label windows: no labels fit anywhere in this study.
- Fit windows: no fits; constants 0.8/0.6 fixed in the assignment before any
  outcome; no statistic from any test year feeds any choice. S5 is a
  price-source switch, not a fit.
- Fill timing: win_start=5 asserted in source + test; engine fills only on 1m
  trade-through with stop-first (inherited harness).
- Contamination caveat next to EVERY dev number: dev years were used to form the
  hypothesis (controls of other studies); the post-release year
  (2025-09-24..2026-09-23) is the clean verdict but scored once for pick+REF
  only.

## Compute plan (heavy_slot, resume-safe)

- `compute_booktrim_engine.py`: `--stage dev|last --fric base|S5 --shifts 0,1,2,3
  --rows REF,BT08,BT06` (subset per stage); sequential shifts, heartbeat print
  every 600 s, caches `tmp/runs_dev_<fric>.pkl` / `tmp/runs_last_<fric>.pkl`
  (resume-safe: skip cached shifts; each shift entry holds run + wins + attrib
  sums + rung intervals summary, NOT full attrib lists to keep RAM small...
  actually attrib lists are ~10k bars x 6 floats, small; store per-year sums +
  interval arrays). Invoked as
  `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_booktrim_eng
  --min-free-gb 2.0 -- .venv/Scripts/python.exe
  research/tournament/oc_booktrim/compute_booktrim_engine.py [--stage ...]`.
- `analyze_booktrim.py`: CPU-only scoring (reset metric + v388.mix + wins +
  decomposition) -> `tmp/booktrim_table.json`; REPORT.md + results.json written
  from that table only.
- Deliverables: PLAN.md (this file), compute_booktrim_engine.py,
  analyze_booktrim.py, results.json, REPORT.md, tests/test_oc_booktrim.py
  (>=1 causality/truncation test + >=1 hand-checked synthetic case;
  `.venv/Scripts/python.exe -m pytest tests/test_oc_booktrim.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the
  original row stays and the change is a disclosed extra row.)
