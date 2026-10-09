# oc_bookband PLAN (pre-registered BEFORE any outcome is computed, 2026-10-08 — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_bookband.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md). Write ONLY `research/tournament/oc_bookband/` +
`tests/test_oc_bookband.py`. Scratch only under `research/tournament/oc_bookband/tmp/`.
GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge.
Engine/heavy 1m work via `scripts/heavy_slot.py` (one job at a time, one phase per process).
Long jobs: heavy_slot + poll; never inspect /proc or folders outside the workspace.
Progress print every 10 minutes. PLAN.md frozen BEFORE any outcome (no turnover/engine number
was computed before this file was written).

## Why

G2 book re-targets every 4h (four clocks); skill lives at h=1..18 bars and the book alone
earns ~2.5%/month with ~51% episode win. Small target changes still cost fees (limit entries
maker 0.0002, exits/closes taker 0.00055) and add stop exposure. No program row has measured
book turnover or tested a no-trade band.

## Variants (exactly two + reference, frozen ex-ante, never fit)

- REF = G2 unchanged (v421 R2B1D17BFG2: rule inv, k 1.0, kd 1.7 corr-inv, bear True, G 2.0;
  v216 G2 grid trader, win_start 5, gate costs maker 0.0002 / taker 0.00055,
  longs funding 0.0001 per 8h settlement, shorts 0, stop-first, minute-5 ban,
  strict trade-through fills).
- NB10 = REF with ONLY the book target series replaced by the no-trade-band filtered
  series F10 (p=0.10, definition below). Everything else bit-identical (dip sleeve,
  governor/vol-target, SL/TP, budgets, G, costs, funding, liquidation, min-notional).
- NB25 = same with p=0.25 (F25).
- No other variant, no threshold tuning, no window tuning, no SL/TP change, no dip change.

## Book target + band rule (frozen, causal)

- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT (engine order).
- Raw book R[t,s] = `forward_v205.research_books_d2` rebuilt exactly (A/Aq/B/Bq/D/Dq files
  in `artifacts/research/engine_real/`, union index, missing -> 0.0), reindexed to the
  `eu.er.v154_books()` standard grid (books154 index), fillna 0.0.
- Bear filter (v421 lines, applied FIRST, identical for all rows): BTC 4h open <
  rolling-1200 mean (min_periods 600) halves positive book weights. Result T[t,s] =
  the deployed G2 final book target (REF engine input before shift-ffill).
- Trailing typical per coin (causal, strictly before t): over the 90d window of 540 4h
  bars [t-540, t-1] on |T[.,s]|: `typ[t,s] = mean(|T[k,s]| for k in window)`.
  min_periods 120: if fewer than 120 history bars exist, use the mean of all available
  strictly-before-t bars; if none exists, or typ non-finite, or typ <= 1e-12, the band
  is INACTIVE at (t,s) (change always executed — no suppression at the start).
- Filtered series F (per variant, per coin, sequential, causal):
  F[0,s] = T[0,s] (first standard-grid bar always executed).
  For t > 0, let prev = F[t-1,s], cur = T[t,s], delta = cur - prev:
  - Flip bypass (ONLY exception): if prev != 0 and cur != 0 and sign(cur) != sign(prev),
    then F[t,s] = cur (direction flips always executed, regardless of size).
  - Else if band active and |delta| <= p * typ[t,s], then F[t,s] = prev (kept;
    engine protection/SL/TP/governor/dip exits still act on the kept position normally).
  - Else F[t,s] = cur.
  Notes (frozen): changes to/from exact 0.0 go through the band (only nonzero sign flips
  bypass); tolerance for zero is exact 0.0 (no 1e-12 band here — T values are the engine
  inputs as-is); prev is the last EXECUTED target, not T[t-1] (band has memory).
- Shifted grid: filter runs on the standard grid; each phase's engine input is
  F.reindex(shifted idx, method=ffill).fillna(0.0) (same ffill as v421 REF).

## Part A — descriptive (no selection, frozen)

- Grid: standard grid intersected with opens_v154 (dropna), bars with a next open inside
  the 2026-09-24 00:00 UTC bound; fwd1[t,s] = open[t+4h,s]/open[t,s]-1 (4h open-to-open
  proxy, disclosed simplification — NOT engine fills).
- Years: anchors 2021..2025-09-24 00:00 UTC, year k = [A_k, A_k+365d) on bar open_time
  (Y4 = most-recent, labelled everywhere; descriptive only, never selects).
- Per (t,s) raw change d[t,s] = T[t,s]-T[t-1,s] (first bar vs 0.0); small10 iff band
  active and |d| <= 0.10*typ[t,s]; small25 iff |d| <= 0.25*typ[t,s].
- Per year: turnover_total = sum|d|; turnover_small10/25 + shares (count share over
  nonzero-d cells AND turnover share); fee proxy = turnover*0.0002 (maker, disclosed);
  gross_total = sum T[t,s]*fwd1[t,s]; gross_small10/25 = sum_{small cells} d[t,s]*fwd1[t,s]
  (marginal one-bar P&L of the increment); net_small = gross_small - fee_small.
  Also full-period totals. Suppressed-turnover estimate: sum|T-F10| turnover saved
  (L1 distance between target paths) per year + fee saved proxy.
- Light compute: 4h parquets only, one process, direct python (no heavy_slot, RAM << 0.4 GB).

## Part B — engine (BINDING, frozen)

- Mechanism = exact copy of the v421 worker (v421_gross_cap.py: pipe_setup "v321",
  corr-aware inv sizes kd=1.7, bear books as above then band filter, risk budget
  0.26*1*1.7, sleeve_gross_cap G=2.0, win_start=5, gate costs inside) with ONLY the
  book series swapped REF->F10/F25. Dip sleeve, governor, agents (R2 table sizes/TPs),
  funding, liquidation, min-notional unchanged.
- Rows run (ONLY): REF + NB10 + NB25. REF must reproduce v421 G2 to the digit
  (dev years R/DD [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)] +
  Y4 (4.648/12.90), 5y 5.410, max yearly DD 16.91, full-path DD 16.82) — else STOP.
  Stored-run check first (v421_runs.pkl via reset_metric/v388.mix); engine REF rerun
  must also match (same code path as NB rows).
- Stages: dev [2021-09-24,2025-09-24) for REF+NB10+NB25 (all four shifts 0..3);
  then last [2021-09-24,2026-09-23) ONCE for REF + the dev4 robust pick ONLY (every Y4
  number labelled scored-once). Via heavy_slot, one job at a time; resume-safe caches
  tmp/runs_dev.pkl + tmp/runs_last.pkl; heartbeat every 600 s.
- Metrics/selection per OPENCODE_W_COMMON_20261007: per-year 4-phase reset %/mo + DD via
  reset_metric.year_reset; dev4 geo mean, W (worst-year R), max yearly DD, losing count;
  5y geo mean; full-path DD via v388.mix equal-1/4 mix from 2021-09-24 (max of
  close/marked); pooled book win rate + fills/year + fee/funding split (v216 trade_stats
  book trades + engine stats). Robust pick on dev4 ONLY among REF/NB10/NB25: eligible
  DD<=20 and no losing dev year; prefer dev4 mean>=5, then highest dev4 WORST-year R,
  ties->higher mean. Y4 never picks. Report fees saved (REF fees - pick fees) and book
  win rate delta.

## Leakage / checks (stated in REPORT)

- Feature timing (T[t] known at bar-t close; typ[t] uses strictly-before-t bars only;
  F[t] uses T[t]+typ[t]+F[t-1] only; entry px from minute-0 1m open once; sd/s4 from
  bars <= decision-2 lag via engine; truncation-tested), label windows (fwd1/descriptive
  proxy is scoring only; engine exits mechanical), fit windows (no fits/thresholds fit:
  p=0.10/0.25 + 90d/540-bar + min 120 frozen ex-ante; agents/R2 tables pre-date anchors),
  fill timing (entry window [5,65) strict trade-through + minute-5 ban; SL market taker /
  TP limit maker; stop-first; NaN never fills). Gate costs inside all engine legs.
  No test-year or most-recent-year statistic feeds any choice. Sealed-Y4 discipline
  (dev pick before last stage; last stage REF+pick only).

## Compute plan (frozen file list)

- `bookband.py`: pure helpers (trailing_typical, apply_band, turnover_stats) + constants,
  no I/O. `compute_turnover.py`: Part A descriptive -> `turnover.json` (stdout table).
- `run_engine.py`: v421-exact worker per shift x variant (REF/NB10/NB25), dev + last
  stages, resume-safe caches, heartbeat, progress every 10 min (heavy_slot only).
- `analyze.py`: reset_metric + v388.mix + win/fee/funding splits -> `results.json`
  (dev table + pick + last scored-once); REF identity asserts inside.
- `REPORT.md` (per-year tables A+B, fees saved, book win rate, leakage statement,
  3-line Vietnamese verdict) + `results.json` (engine + descriptive rows).
- Tests `tests/test_oc_bookband.py` (>=1 causality/truncation + >=1 hand-checked
  synthetic; `.venv/Scripts/python.exe -m pytest tests/test_oc_bookband.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original
  row stays and the change is a disclosed extra row.)
