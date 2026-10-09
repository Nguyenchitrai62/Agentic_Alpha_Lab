# oc_booktwo PLAN (pre-registered BEFORE any outcome is computed, 2026-10-08 — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_booktwo.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md, IDEAS6_20261008.md idea #7 read in full, CLOSED rows cited read first).
Write ONLY `research/tournament/oc_booktwo/` + `tests/test_oc_booktwo.py`. Scratch only under
`research/tournament/oc_booktwo/tmp/`. GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/
rm/commit/switch/rebase/merge. Engine / heavy 1m work via `scripts/heavy_slot.py` (one job at a time,
float32; one phase per process is fine). Long jobs: nohup + log under tmp/, poll the log; never inspect
/proc or folders outside the workspace. Progress print every 10 minutes. PLAN.md frozen BEFORE any outcome.

## Why (IDEAS6_20261008.md idea #7, rank 7 — quoted, not refit)

Mech: single 10bps-better limit fills or expires empty; two rungs harvest same signal across minute-0..60 noise, no chasing (placed once, expire 60min).
Rule: split each book order: half 10bps better + half 25bps better, both PostOnly maker, 60min, trade-through, minute-5 ban; unfilled expire. V1 50/50; V2 70/30. SL/TP unchanged.
Data: existing 1m. Harness: engine vs G2 (fill-rate+fee split). Effect: +0.0-0.05%/mo, DD flat. Prior 8%.
Leak: both from minute-0 price once; no re-peg/chase. Close: `oc_bookoffset` (scaled SINGLE offset) / `oc_cadence` (slower) / `oc_idea5_manualrest` (MANUAL rest) — this SPLITS one signal into two prices. Kept.
CLOSED rows read first: `oc_bookoffset` (PLAN/REPORT/compute_bookoffset.py — vol-scaled SINGLE book offset 5..40bps vs fixed 10bps, PROMISING 5/5 on the from-flat screen; leader-closed 2026-10-06 because the deployed BOT book in engine trade mode is ALREADY vol-scaled `off=max(min_off,k_off*sigma4h)` k_off 0.25 — this idea keeps FIXED 10/25bps rungs, no vol scaling), `oc_cadence` (PLAN — hold each book target 8h/12h to cut turnover; this idea keeps every-bar targeting, only splits the PRICE), `oc_idea5_manualrest` (compute_manualrest.py — MANUAL 4h-rest expiry B0/H1/H2 entry windows; this is BOT trade-mode entry price split, expiry 60min per idea). Distinct per IDEAS6.

## Variants (exactly two + reference, frozen ex-ante, never fit)

- REF = G2 unchanged (v421 R2B1D17BFG2: rule inv, k 1.0, kd 1.7, bear True, G 2.0; v216 G2 grid trader, S3 entry `max(0.10%,0.25*sigma4h)` valid 2 bars, win_start 5, SL 4 sigma_d market / TP 8 sigma_d limit, be_k 2.0, tighten 1.5, one add + one 50% reduce).
- V1 = REF with ONLY the flat-branch new-order entry replaced by a two-rung ladder: 50% at 10bps better + 50% at 25bps better (fixed, no vol scaling).
- V2 = same as V1 but 70% at 10bps + 30% at 25bps.
- No other variant, no offset tuning, no split tuning, no re-peg inside the window, no SL/TP-level change, no policy/threshold/budget change, no dip change.

## Ladder rule (frozen, causal)

- Signal, threshold, sizing, policy, budgets, dip sleeve: IDENTICAL to G2. Per (bar i, coin a) with flat state (cur_q==0, no resting order), G2 would issue one limit at weight `w=|tg|` (theta 0.05, book_mult 1.0, risk None so size=|tg|; min-notional `w*prev_eq*10000>=mins[a]` on the TOTAL; sd/s4 finite required). Ladder issues at the same decision, from the same `O0=O[i,0,a]` (1m minute-0 open, known at the bar start T) ONCE:
  - V1: `px1=O0*(1-sgn*0.001)` weight `w1=0.5*w`; `px2=O0*(1-sgn*0.0025)` weight `w2=0.5*w`.
  - V2: `px1` same, `w1=0.7*w`; `px2` same, `w2=0.3*w`.
  - Buy (sgn>0): limits BELOW O0; sell: ABOVE O0. PostOnly maker by construction (fill only on strict trade-through, fill price = limit).
- Fill window: minutes [5,65) only (Python slice 5:65, 60 bars; minute-5 ban for pipeline latency; 60min expiry per idea). Strict trade-through: buy fills iff `low[m]<px`; sell iff `high[m]>px` (touch `==` never fills; NaN minutes never fill). Each rung fills at most once, at its FIRST qualifying minute. Unfilled rung expires at minute 65 with no market fallback (position stays as filled half or flat). No carry of the unfilled half to the next bar (differs from G2 n_valid=2 by IDEA DESIGN, disclosed; no chasing).
- Sequential minute simulation over [5,65): at each minute m, first fill any still-resting rung whose trade-through holds at m (maker fee 0.0002 on the filled half), updating total quantity `q=sgn*(w1*I1/px1+w2*I2/px2)` and average entry `E=(w1*I1+w2*I2)/(w1*I1/px1+w2*I2/px2)`; then check SL/TP on the open quantity (if any) at the same minute with stop-first (same as engine: stop touch wins any tie). SL/TP levels recomputed from the CURRENT average entry E with the SAME sd (psd=sd_a at issue) and SAME multiples (m_sl=4.0, m_tp=None→8.0 sigma_d): `SL=E*(1-side*4*sd)`, `TP=E*(1+side*8*sd)`; be/part flags reset to False on the second fill updating the average (disclosed simplification; in-position add/reduce offsets after the window stay G2 vol-scaled).
- After minute 65: expired halves cancelled (event `order_expire` for diagnostics). The open position (full, half, or none) continues EXACTLY as a G2 position: same grid policy (open/add/reduce/close/tighten), same break-even (+2sd), same SL market taker 0.00055 / TP limit maker 0.0002, same stop-first, same funding (longs 0.0001 per settlement in (T,T+4h], shorts 0), same governor/vol-target, same dip sleeve. A stopped/TP'd position cancels no further ladder (halves already expired). A flat (neither filled) bar behaves as G2 unfilled (no position until next decision).
- In-position scale orders (adds/reduces/close) keep G2 vol-scaled offsets `max(0.001,0.25*s4)` and validity; only the INITIAL entry is fixed-split.
- Fees: filled halves maker 0.0002 each; SL legs taker 0.00055; TP legs maker 0.0002. Funding identical to G2.

## Engine (book idea: 4-phase engine vs G2, BINDING)

- Mechanism = exact copy of v421 worker (v421_gross_cap.py: pipe_setup "v321", corr-aware inv sizes kd=1.7, bear books (BTC<MA1200 longs×0.5), risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0, win_start=5, gate costs inside) with ONLY the flat-branch entry replaced by the ladder above (V1/V2). Dip sleeve, books, governor, agents (R2 table sizes/TPs), funding, liquidation, min-notional (total-weight check) unchanged.
- Rows run (ONLY): REF (=G2 unchanged) first + V1 + V2. REF must reproduce v421 G2 to the digit (dev years R/DD [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)] + Y4 (4.648/12.90), 5y 5.410, full-path DD 16.82) — else STOP.
- Stages: dev [2021-09-24,2025-09-24) for REF+V1+V2 (all four shifts); then last [2021-09-24,2026-09-23) ONCE for REF + the dev4 robust pick ONLY (every Y4 number labelled scored-once). Via heavy_slot, one job at a time; resume-safe caches tmp/runs_dev.pkl + tmp/runs_last.pkl; heartbeat every 600 s; nohup + tmp log.
- Metrics/selection per OPENCODE_W_COMMON_20261007: per-year 4-phase reset %/mo + DD via reset_metric.year_reset; dev4 geo mean, W (worst-year R), max yearly DD, losing count; 5y geo mean; full-path DD via v388.mix equal-1/4 mix from 2021-09-24 (max of close/marked); pooled book/all win rates + fills/year + fee/funding split. Robust pick on dev4 ONLY: eligible DD<=20 and no losing dev year; prefer dev4 mean>=5, then highest dev4 WORST-year R, ties→higher mean. Y4 never picks.
- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT. 1m via pod.minutes() float32 cube (same as v421); books = research_books_d2 + bear filter; opens = shifted-grid opens.

## Leakage / checks (stated in REPORT)

- Feature timing (entry px from O0 only, known at T; sd/s4 from bars ≤ decision-2 lag via engine; no re-peg; truncation-tested), label windows (no labels fit; exits mechanical), fit windows (no fits/thresholds/quantiles; 10/25bps + 50/50 + 70/30 frozen ex-ante; agents/R2 tables pre-date anchors), fill timing (entry [5,65) strict trade-through + minute-5 ban; SL market / TP limit; stop-first; NaN never fills). Gate costs inside all legs. No test-year statistic feeds any choice.

## Compute plan

- `booktwo.py`: pure helpers (split_weights, limit_prices, find_fill, avg_entry, sl_tp_from_entry) + sequential window simulator for unit tests, no I/O.
- `run_engine.py`: v421-exact worker per shift × variant (REF/V1/V2), dev + last stages, resume-safe caches, heartbeat, progress every 10 min.
- `analyze.py`: reset_metric + v388.mix + win/fee/funding splits → `results.json`.
- `results.json` (engine rows), REPORT.md. Tests `tests/test_oc_booktwo.py` (≥1 causality/truncation + ≥1 hand-checked synthetic; `.venv/Scripts/python.exe -m pytest tests/test_oc_booktwo.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row stays and the change is a disclosed extra row.)
