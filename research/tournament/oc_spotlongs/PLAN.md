# oc_spotlongs — PLAN (pre-registered 2026-10-08, BEFORE any outcome)

Assignment: `docs/opencode/OPENCODE_W_oc_spotlongs.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md, IDEAS10_20261008.md idea #3 read; CLOSED rows
oc_bookfunding / oc_carryborrow / oc_cashcarry read). Write ONLY
`research/tournament/oc_spotlongs/` + `tests/test_oc_spotlongs.py`.
Engine runs via heavy_slot (one job at a time; RAM tight). Heartbeat print every
600 s. Scratch only under `research/tournament/oc_spotlongs/tmp/`.

## Question (IDEAS10 #3, rank 3, prior 12%, effect +0.0-0.2 %/mo, DD flat)

Book longs on spot-margin instead of perp (keep exposure, kill funding bleed).
Gate funding taxes every long 0.01%/8h (~1.1%/mo on full long exposure);
oc_bookfunding's answer was CUT longs (x0.75 when crowded) but hot funding marks
strength (5y -8.8% when cut). Routing longs to spot keeps the exposure while
paying ~0 funding.

## Hypothesis (fixed here)

Routing book LONG exposure to spot-margin (no funding, maker in/out, USDT borrow
where leveraged) preserves G2 exposure and adds the saved long funding back to
equity minus a small borrow drag, so dev4 mean rises by +0.0-0.2 pp/mo with DD
flat (borrow haircut in stress). Gated routing (V2) keeps most of the save with
less borrow. Any clean failure is a valid result.

## Frozen mechanism (exact copy base = oc_c2bybit base = oc_chronos pipe)

- 4 phases (shifts 0..3, 4h grid opens at s, s+4, ... UTC); pipe v321 via
  phase_offset_full.pipe_setup; corr-aware dip sizes mult 1/(1+n)*1.7*tilt*base
  (n = coins with C<=O*(1-2.5*sig); tilt=1 here, no Chronos/Kronos tilt);
  risk_mult 1.0; sleeve_risk_budget 0.26*1*1.7; sleeve_gross_cap G=2.0;
  bear books (BTC 4h open < 1200-bar mean halves LONG targets; standard rows,
  before shifted-clock ffill).
- Gate costs inside the engine: maker 0.0002, taker 0.00055 (stops/market taker),
  longs pay 0.0001/8h, shorts 0. Limit orders fill only on 1m trade-through,
  strictly through the price; no fill in the first 5 minutes after a 4h close
  (win_start=5). Stop-first in a shared 1m bar (engine handles).
- Every book position keeps limit entry + market SL + limit TP, stop-first
  (user rule; this idea is NOT a stop-entry order, so entries stay limit).
- Fill basis from minute data (same 1m cube as base; spot-perp basis assumed 0,
  labelled assumption, no close-sample claim).

## Variants (ONLY these; no selection beyond the frozen robust rule, no tuning)

- REF = G2 unchanged (R2B1D17BFG2: rule inv, k 1.0, kd 1.7, bear True, G 2.0).
- V1_SPOT = REF + ALL book longs as spot-margin: book long funding 0 on every
  holding bar where the end-of-bar book quantity is long (shorts still 0, dip
  sleeve funding unchanged: rung timeout pays FUND_LONG when settle, as base).
  Borrow interest on the spot long leg where leveraged (see Borrow below) at
  APR 10%/yr main; stress row APR 15%/yr (same two numbers, no fit).
  Maker in/out 0.0002, SL market taker 0.00055, TP limit maker 0.0002, stop-first,
  win_start=5 — all unchanged. Shorts stay perp.
- V2_GATED = V1 routing ONLY when that coin's trailing 7d average settled
  funding exceeds its pre-anchor median (see Signal below); otherwise that
  coin-bar stays perp (pays gate funding when long at a settlement). Shorts
  always perp. Borrow same as V1 but only on the spot-routed portion.
- CTRL_PERP_EXP (exposure-matched control): SAME quantity path / fills as V1
  (identical weights, same borrow-cap/liquidation path) but charges perp book
  funding on longs (FUND_LONG when settle) and NO borrow. By construction it
  matches V1 exposure exactly, so V1-CTRL isolates funding-save-minus-borrow
  when exposure is unchanged; REF-V1 shows the full-account effect including
  any exposure change (borrow cap / liquidation / compounding).
- S5_BYBIT row: for the dev4 robust pick + REF only, rerun on Bybit 1m
  (S5 harness of oc_c2bybit: bybit_minutes() from
  data/raw/bybit_linear_1m_20261004, live0 = 2021-11-15 + shift, standard index
  filtered to >= 2021-11-15 before shift, win_start=5). Year 2021 is a SHORT
  window (labelled). If Bybit files missing/unreadable, S5 = not reproducible.

## Exact causal definitions (fixed before seeing numbers)

- Symbols: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- Books: fw.research_books_d2(eu) on the standard v154 index, bear-halved on
  standard rows, ffilled to each shift grid (same as oc_chronos/run_engine.py).
- Funding signal F7[T,s] (V2 gate only): mean of settled `last_funding_rate`
  from data/raw/binance_premium_20260928/*_funding.parquet (calc_time =
  settlement time UTC) over settlements with T-7d <= c < T (left-inclusive,
  right-exclusive; strictly before T, millisecond-exact; a settlement stamped
  08:00:00.001 is NOT usable at T=08:00:00). Require >= 14 settlements else NaN
  (7d at 8h cadence expects 21; NaN rows stay perp, never spot).
- Pre-anchor median med_k[s] (V2 fit): median of F7[.,s] over settlement history
  with bar time in [2020-01-01, A_k - 7d), finite F7 only, per coin, where A_k
  is the anchor (2021..2025-09-24). Uses ONLY data before the anchor minus a
  7-day embargo; no statistic from any test year feeds any choice. Borrow APR
  fixed ex-ante (10/15% grid, no fit).
- V2 route rule per (holding bar i, coin a) in year k: spot_routed = finite
  F7[T,s] and F7[T,s] > med_k[s]; else perp. T = holding-bar open
  (idx[i]+4h). The median of anchor A is applied to all four shifts in year A.
- Borrow (V1 on all book longs; V2 on spot-routed longs only): per holding bar,
  after the engine steps quantities, borrowed notional B_bar = max(0,
  long_notional_spot_end - equity_start), where long_notional_spot_end =
  sum over spot-routed coins of max(q_end_a, 0) * o2[i][a] (end-of-bar quantity
  x next-open valuation, same convention as the engine's funding leg), and
  equity_start = bar-start equity. Hourly rate APR/8760 applied per 4h bar as
  B_bar * APR * (4/8760), deducted from bar PnL alongside funding (causal: uses
  only this bar's quantities/equity, no future data). If long_notional <=
  equity, borrow = 0 (cash covers; "where leveraged" per IDEAS10). Short cash
  does NOT offset longs (conservative). Implementation: engine patch that zeroes
  the book-long funding leg for spot-routed (coin,bar) and subtracts the borrow
  term; dip sleeve untouched. SL/TP attached as now.
- Spot-perp basis: fill prices from the same 1m cube for spot and perp legs
  (basis 0 assumption, labelled; majors basis is bps-level vs the funding save).

## Windows / metrics (fixed)

- Anchors 2021..2025-09-24; dev4 = years 0..3 ([A,A+365d)); Y4 = 2025-09-24..
  2026-09-23 scored ONCE, only for the dev4 robust pick + REF, labelled REF
  (post-release year; every Y4 number including REF is a labelled re-score,
  never a selection input); 5y = years 0..4 (context).
- Per-year 4-phase reset %/mo + DD via reset_metric.year_reset; dev4/5y geo
  mean, W (worst-year R), max yearly DD, losing count; full-path DD via
  v388.mix equal-1/4 mix from 2021-09-24 (max of reset DDs and full-path for
  the gate); pooled book/rung/all win rates + fills/year (same collection as
  oc_chronos run_engine.py).
- Reproduction gate (STOP if failed): REF base years 0..4 R/DD ==
  v421_result.json G2 R2B1D17BFG2 [(2.588/10.86),(3.282/16.91),(6.045/15.81),
  (10.677/8.27),(4.648/12.90)] to the digit, 5y 5.410, max yearly DD 16.91,
  full-path DD 16.82.
- Robust pick (dev4 ONLY): among V1_SPOT, V2_GATED with full-path DD <= 20 and
  no losing dev year, prefer dev4 mean >= 5 %/mo, then highest dev4 WORST-year
  monthly return, ties -> higher mean. S5 Bybit row reported for the pick only.
- Cost rows: main APR 10%; stress APR 15% (sensitivity, same positions;
  no refit). S1 cost stress NOT rerun (funding/borrow question is orthogonal;
  gate costs only).

## Leakage / contamination (pre-registered checks, stated in REPORT)

- Feature timing: books known at close of T, held over [T,T+1); F7 uses only
  settlements with c < T (millisecond-exact); V2 route uses only (coin,
  holding-bar T) F7 vs frozen med_k. Truncation test: recompute F7/med from a
  truncated funding panel — identical on the kept prefix; route set subset of
  {perp, spot}.
- Label windows: no label fit here; engine uses the realised 1m path.
- Fit windows: med_k from [2020-01-01, A_k-7d) only, per (anchor, coin); year y
  uses anchor-y median only, never a later anchor; borrow APR fixed ex-ante.
- Fill timing: win_start=5 asserted in source (no fill minutes 0-4); limit fills
  only on 1m trade-through (strictly through); stop-first asserted; spot fills
  use the same minute cube (basis 0 labelled).
- Contamination caveat next to EVERY dev number: dev years were available when
  the idea was scored (IDEAS10 is post-hoc); the post-release year
  (2025-09-24..2026-09-23) is the clean verdict but scored once for the pick
  only (selection on dev4).

## Compute plan (heavy_slot, resume-safe)

- `spot_rule.py`: pure F7/med/route + borrow-term helpers (unit-tested).
- `compute_spotlongs_engine.py`: sequential shifts 0..3 per variant (one heavy
  process at a time), heartbeat print every 600 s, caches
  `tmp/runs_<variant>.pkl` (resume-safe: skip cached shifts). Invoked as
  `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_spotlongs_eng
  --min-free-gb 2.0 -- .venv/Scripts/python.exe
  research/tournament/oc_spotlongs/compute_spotlongs_engine.py
  [--stage dev|last] [--shifts ...] [--rows ...]`. Long runs: nohup + log under
  tmp/ (never system temp; never /proc or folders outside the workspace).
- `analyze_spotlongs.py`: CPU-only scoring (reset metric + v388.mix + wins) ->
  `tmp/spotlongs_table.json`; REPORT.md + results.json written from that table
  only.
- Deliverables: PLAN.md (this file), spot_rule.py, compute_spotlongs_engine.py,
  analyze_spotlongs.py, results.json, REPORT.md, tests/test_oc_spotlongs.py.

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the
  original row stays and the change is a disclosed extra row.)
