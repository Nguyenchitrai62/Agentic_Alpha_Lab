# oc_vpinveto — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_vpinveto.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md, `docs/opencode/IDEAS5_20261008.md` §2 read in full).
Write ONLY `research/tournament/oc_vpinveto/` + `tests/test_oc_vpinveto.py`.
Engine / heavy 1m work via `scripts/heavy_slot.py` (one job at a time, one coin at a time, float32).
Heartbeat print every 600 s in long jobs. Scratch only under `research/tournament/oc_vpinveto/tmp/`.
GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge.
No orders, no authenticated endpoints, no Kaggle uploads. No inspection outside the workspace.

## Why (IDEAS5 §2, rank 2)

"Bitcoin wild moves" (SciDirect 2025: VPIN predicts jumps, VAR) + Shunya 2024-25
(1.07B trades: VPIN elevated before inflections; OFI tracks momentum). Toxic one-sided
flow = market-maker withdrawal ahead (Easley-Lopez-O'Hara); 2026 cascade panel:
taker-flow variance compression is the sole placebo-tested precursor (p ~5e-6).
CLOSED row read: `oc_i2_tapecancel` (dSum -0.40, REPORT.md): cancelled resting bids on
POST-placement 30m tape — this is an EX-ANTE book gate on volume-clock toxicity with
pre-anchor norms, different leg and timing, so kept per IDEAS5 near-duplicate note.

## Variants (exactly two + reference, no others)

- REF = G2 unchanged (R2B1D17BFG2, v421 runs: rule inv, k 1.0, kd 1.7, bear True, G 2.0).
- V1 = per-(T,sym) book-LONG veto: if VPIN gate true at decision bar T for coin sym,
  and the bear-filtered book weight > 0 (long), weight x0.5. Shorts untouched.
- V2 = V1 + skip new dip bids that bar: same book veto PLUS dip rung multiplier 0
  for that (T,sym) (no new dip position opened on a gated holding bar; exits of
  already-open rungs unchanged).
- No exposure-matched control (IDEAS5 §2 does not ask; §4-style control not applicable
  to a toxicity veto; disclosed).
- Frozen thresholds (never fit): trailing window 24h, 50 equal-volume buckets,
  z > 2.0, trailing-1y norm window, 7-day embargo, x0.5, dip skip = 0. All round
  numbers from IDEAS5, frozen ex-ante.

## VPIN gate (exact causal definition, frozen, no new parameter)

- Data (read-only, never edited): `data/raw/aggflow_20260929_orders_1m/<COIN>/<COIN>-aggTrades-YYYY-MM.parquet`
  (local, 2020+: BTC/ETH/XRP from 2020-01, BNB from 2020-02-10, SOL from 2020-09-14;
  all cover the first norm window 2020-09-17..2021-09-17, so NO anchor-year skip;
  if a coin/year norm has <1000 samples the gate is never true there — disclosed skip,
  never imputed).
- Per-1m bar m: B_m = sum(buy_* notional, float32), S_m = sum(sell_* notional),
  V_m = B_m + S_m (quote notional; exchange taker flags = ground truth that
  normal-CDF bulk classification (BVC) approximates; using flags removes BVC estimation
  noise and is strictly causal — disclosed implementation of "bulk-classified (1m bars,
  normal-CDF)"; pure BVC helper `bvc_buy_frac` kept in `vpin_rule.py` for the synthetic
  unit test only and NOT used on real data).
- VPIN(T, sym): trailing 24h window W(T) = {1m bars with close_time in (T-24h, T]}
  (strictly <= the 4h bar close T; never the gate bar's own future flow). If
  |W| < 1200 bars or total V <= 0 → NaN (never gate). Else split W chronologically
  into 50 equal-volume buckets by cumulative V_m (bucket boundaries on 1m bars;
  last bucket takes remainder): per bucket b, imb_b = |sum(B-S) in b|; VPIN =
  sum_b imb_b / sum_b V_b in [0,1] (VPIN-50 form; 1m bars are the finest buckets).
- Norms (walk-forward, pre-anchor + 7d embargo, frozen per anchor year):
  ANCH5 = 2021-09-24 .. 2025-09-24. For anchor A and coin sym: mu[A,sym], sd[A,sym] =
  mean/std of VPIN(T,sym) over 4h closes T in [A-372d, A-7d] (365d window ending 7d
  before the anchor; uses only rows ending before A minus embargo; no test-year data).
  Year y=[A, A+365d) uses mu/sd of its anchor A on all four phase shifts.
- z(T,sym) = (VPIN(T,sym) - mu[A,sym]) / sd[A,sym] (sd<=1e-12 or NaN → never gate).
  Gate(T,sym) = z > 2.0 (strictly greater; NaN → False).
- Evaluation at holding-bar open T+4h? NO — at the decision bar close T itself:
  the book row indexed T (books154 standard grid) uses VPIN(T) from 1m <= T;
  the engine forward-fills books to holding bars (same ffill as v426, causal).
  Rows with T < 2021-09-24 are never gated.
- Expected gate rate (IDEAS5: ~10-20 gate-bars/yr): reported, not selected on.

## Engine (fixed; per-(T,sym) book-multiplier copy of v426_book_brake.py mechanism)

- v414 pipe v321, corr-aware inv sizes kd=1.7, bear books built EXACTLY as v421
  (`btc = _opens_std["BTCUSDT"].reindex(books154.index)`,
  `bear = (btc < btc.rolling(1200, min_periods=600).mean())`,
  `sb.loc[bear] = sb.loc[bear].where(sb<=0, sb*0.5)`), risk budget 0.26*1*1.7,
  sleeve_gross_cap G=2.0, win_start=5, gate costs inside the engine (maker 0.0002,
  taker 0.00055, longs pay 0.0001/8h, shorts 0; limit fill only on 1m trade-through;
  nothing in first 5 min after a 4h close; stop-first in shared 1m bar — engine handles).
- Book veto applied AFTER the bear filter, BEFORE the shifted-clock forward fill:
  `sbb = sb.where(~(gate_long & (sb > 0)), sb * 0.5)` where gate_long is the VPIN
  gate DataFrame on the standard grid (T,sym). V2 additionally multiplies the
  dip `tilt(i,a)` by 0 when Gate(T[i],cols[a]) true (skip new dip bids that bar).
- Rows run through the engine (ONLY these three): REF, V1, V2.
- Stages: stage dev runs [DEV0=2021-09-24, DEV1=2025-09-24) for the three rows
  (REF first; must reproduce v421 G2 years 0..3 R/DD to the digit, else STOP).
  Stage last runs [DEV0, Y1=2026-09-23) for the dev4 robust pick + REF ONLY, ONCE
  (every Y4 number labelled scored-once; REF Y4 must reproduce v421 G2 Y4 to digit).
  No re-runs after seeing outcomes; any change becomes a disclosed extra row.
- V2 dip-leg replica gate FIRST (IDEAS5 dip rule): before V2 engine, mask the frozen
  D0+B1 replica ledger (`oc_k2placebo/tmp/ledger.npz`, read-only) on gated (T,sym)
  bars and compute dSum_dev4; V2 engine runs regardless (book leg justifies it) but
  the replica dSum vs +0.273 is reported as the dip-leg gate (PROMISING iff
  dSum_dev4 >= +0.273); disclosed.

## Metrics / gates (fixed)

- Gate costs as above (inside engine).
- Per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4 geo mean,
  W (worst-year R), max yearly DD, losing count; 5y geo mean (years 0..4 on stage-last
  runs); full-path DD via `v388.mix` equal-1/4 mix from 2021-09-24 (max of reset DDs
  and full-path for the gate); pooled book/rung/all win rates + fills/year + gated
  share of (T,sym) bars + sized mean book multiplier (same collection as
  oc_beargate/run_engine.py).
- Robust pick on dev4 ONLY among REF/V1/V2: DD <= 20 and no losing dev year; prefer
  dev4 mean >= 5 %/mo, then highest dev4 WORST-year monthly return, ties -> higher mean.
- G2 baseline to reproduce (v421_result R2B1D17BFG2): dev
  [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)], Y4 (4.648/12.90),
  5y 5.410, full-path DD 16.82. Reproduce REF to the digit first, else STOP.

## Leakage / checks (stated in REPORT)

- Feature timing (1m bars with close_time <= T only; gate-bar's own future flow never
  used; truncation-tested in tests/test_oc_vpinveto.py); label windows (no labels fit;
  norms are unsupervised moments, window [A-372d,A-7d] only); fit windows (mu/sd frozen
  per anchor year, 7d embargo, no statistic from any test year feeds any choice);
  fill timing (win_start=5 + 1m trade-through + stop-first, engine). Gate costs inside
  the engine. No statistic from any test year feeds any choice.

## Compute plan (heavy_slot, resume-safe, one coin at a time, float32)

- `vpin_rule.py`: pure helpers (`bucketed_vpin`, `bvc_buy_frac`, `gate_z`, `anchor_of`)
  — no data access; unit-tested.
- `compute_vpin.py`: one coin at a time → per-coin 1m totals (float32) → VPIN per 4h
  close (standard grid from engine books? approximated by 4h closes 2020-09-01..2026-09-23)
  → per-anchor mu/sd (CSV) → gate table `gates_4shift.parquet` {(shift,T,sym): gate}.
  CPU-only except via heavy_slot (1m RAM > 0.4 GB). Resume-safe per-coin caches.
- `check_g2.py`: f=0-style reproduction assert (v421_runs.pkl + reset_metric) to digit.
- `run_engine.py`: sequential shifts per stage, heartbeat every 600 s, caches
  `tmp/runs_dev.pkl` / `tmp/runs_last.pkl` (resume-safe). Via heavy_slot, one job.
- `replica_gate_v2.py`: CPU-only mask of k2placebo ledger on gated bars → dSum_dev4
  vs +0.273 (dip-leg gate for V2).
- `analyze.py`: CPU-only scoring (reset metric + v388.mix + wins) →
  `tmp/dev_table.json` + `tmp/last_table.json` (+ 5y means + full-path DD).
- Deliverables: PLAN.md (this file), vpin_rule.py, compute_vpin.py, check_g2.py,
  run_engine.py, replica_gate_v2.py, analyze.py, results.json, REPORT.md,
  tests/test_oc_vpinveto.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_vpinveto.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the
  original row stays and the change is a disclosed extra row.)
