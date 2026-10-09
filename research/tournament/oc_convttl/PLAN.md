# oc_convttl PLAN (pre-registered BEFORE any outcome is computed, 2026-10-08 — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_convttl.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md, IDEAS8_20261008.md idea #7 read in full, CLOSED rows cited read first).
Write ONLY `research/tournament/oc_convttl/` + `tests/test_oc_convttl.py`. Scratch only under
`research/tournament/oc_convttl/tmp/`. GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/
rm/commit/switch/rebase/merge. Engine / heavy 1m work via `scripts/heavy_slot.py` (one job at a time,
float32; one shift per process). Long jobs: nohup + log under tmp/, poll the log; never inspect
/proc or folders outside the workspace. Progress print every 10 minutes. PLAN.md frozen BEFORE any outcome.
CPU only (no heavy local GPU).

## Why (IDEAS8_20261008.md idea #7, rank 7 — quoted, not refit)

Mech: single 10bps/60min limit fills or expires empty (oc_booktwo tried two PRICES, rejected); high-|w|
signals deserve more patience, low-|w| less — differentiate by TIME, not price, with no chasing.
Rule: order price/offsets frozen; TTL = 2 bars if |w| > pre-anchor median |w| (V1), else 1 bar;
V2 threshold p75/1 bar. One placement, no re-peg, expire unfilled.
Data: existing 1m + pre-anchor |w| quantile. Harness: engine vs G2 (fill-rate + fee split).
Effect: +0.0-0.05%/mo, DD flat. Prior 8%.
Leak: quantile pre-anchor+embargo; TTL from signal-bar |w| only; never re-price on placement-window
tape (re-peg rejected by rules).
Closest CLOSED: oc_booktwo (TWO-RUNG 10+25bps ladder) / oc_bookoffset (vol-SCALED offset) — this keeps
ONE price, varies EXPIRY by conviction.
CLOSED rows read first: `oc_booktwo` (PLAN/REPORT/run_engine.py/booktwo.py/analyze.py — fixed 10/25bps
two-rung ladder V1 50/50 V2 70/30, 4-phase engine vs G2, NEGATIVE: dev4 V2 5.456 vs REF 5.601, scored-once
Y4 -0.127pp; this study keeps ONE price, varies only EXPIRY by conviction, no second rung, no weight split),
`oc_bookoffset` (PLAN/REPORT/compute_bookoffset.py — vol-scaled SINGLE offset clip(0.10*sigma,5,40bps)
vs fixed 10bps, PROMISING 5/5 on the from-flat screen; leader-closed 2026-10-06 because the deployed BOT
book in engine trade mode is ALREADY vol-scaled `off=max(min_off,k_off*sigma4h)` k_off 0.25 — this study
keeps the DEPLOYED vol-scaled offset frozen, varies only resting TIME by conviction). Distinct per IDEAS8.

## Variants (exactly two + reference + two diagnostic controls, frozen ex-ante, never fit)

- REF = G2 unchanged (v421 R2B1D17BFG2: rule inv, k 1.0, kd 1.7, bear True, G 2.0; v216 G2 grid trader
  S3 entry `max(0.10%,0.25*sigma4h)` valid 2 bars, win_start 5, SL 4 sigma_d market / TP 8 sigma_d limit,
  be_k 2.0, tighten 1.5, grid band B_abs 0.03 / B_rel 0.40, cool 6, max_adds 99).
- V1 = REF with ONLY the flat-branch new-order validity replaced by conviction-dependent TTL:
  `n_valid = 2 if |w_base[T,s]| > q50_k else 1`, where q50_k = pre-anchor median |w_base| for anchor year k.
- V2 = same with `n_valid = 2 if |w_base[T,s]| > q75_k else 1` (p75 threshold).
- C_V1 (diagnostic, NOT eligible): REF with uniform n_valid=2 but book target `* s_V1,y` per anchor year y,
  where s_V1,y = (1+p_V1,y)/2 and p_V1,y = realised share of standard-grid non-zero cells in year y with
  |w_base| > q50_y (in-year realised mean-TTL scale; uses test-year data so NOT tradable, NOT eligible).
- C_V2: same with V2 (p_V2,y from q75_y, s_V2,y = (1+p_V2,y)/2).
- No other variant, no offset/price change, no SL/TP/policy/threshold/budget change, no dip change.
  Direction, sizing (|tg|), thresholds (theta 0.05) unchanged; only resting TIME varies.

## Weights, quantiles, TTL rule (frozen, causal)

- Base books: `w_ens = 0.8*o1 + 0.2*cb` with `o1 = 0.25*(A+Aq+B+Bq)`, `cb = 0.5*(D+Dq)` on the books154 index
  (same 6 cached members as oc_memberagree: A/Aq/B/Bq/D/Dq; union index, missing -> 0.0; builder check:
  REF must equal `forward_v205.research_books_d2` to <1e-12 max abs diff).
- Bear filter (fixed, all five rows, v421 rule on the standard grid BEFORE shifted ffill):
  `bear[T] = BTC_open[T] < mean(BTC_open[T-1199..T])` (rolling(1200,min_periods=600) on opens_v154 BTCUSDT,
  NaN -> False); `w_base[T,s] = 0.5*w_ens[T,s]` iff bear[T] and w_ens[T,s] > 0 else unchanged (longs halved,
  shorts/flats kept). Same mask for all rows (opens only). Scale and bear commute for C rows.
- Grid: books154 index (standard grid). Quantile pool per anchor year k (A_k in 2021..2025-09-24):
  training rows `U < A_k - 7d` (7-day embargo per common header) on the FULL standard-grid history
  (earliest available through A_k-7d), pooled across the 5 coins, NON-ZERO |w_base| cells only
  (active signals; zeros would be untraded TTL-irrelevant mass — frozen choice).
  `q50_k = quantile(|w_base[U,s]|, 0.50)`, `q75_k = quantile(|w_base[U,s]|, 0.75)` (numpy quantile, linear).
  Pool is non-empty for every k (books exist from 2020, >1y before A_0-7d). No within-year, no test-year,
  no most-recent-year data enters any q. Thresholds frozen per year, one value per year (not per coin).
- Signal: at flat-branch issuance for (shifted bar i, coin a) with ffill'd `w_base[i,a]` (source standard row
  r <= t_s, close-known; identity at shift 0), `TTL = 2 if |w_base[i,a]| > q_k else 1` where k = anchor year
  containing the decision (year = [A_k+sh, A_k+sh+365d) on that shift; strict `>`, ties go short TTL).
  |w| is the signal-bar |w_base| only (before vol-target/governor scaling; vol/governor are per-bar global
  multipliers so ranking by |w_base| == ranking by |tg| within a bar, and |w_base| is the pure signal
  conviction — frozen choice). Zero signals never issue (theta 0.05 gate unchanged).
- Order price/offsets frozen (G2 deployed): `off = max(0.001, 0.25*s4)` from minute-0 open O0 once;
  PostOnly maker by construction (fill only on strict trade-through `low<px*(1-ft)` / `high>px*(1+ft)`,
  ft=0; fill price = limit). Fill window for a NEW order: minutes [5,240) of the issue bar only
  (win_start=5 pipeline ban; G2 checks the resting order each holding bar from `start = win_start` on the
  issue bar and from minute 0 on carried bars). One placement, no re-peg (price/weight never updated while
  resting), expire unfilled at `i >= T["exp"]` where `T["exp"] = i + TTL` (TTL=2 G2 default; TTL=1 expires
  at the next decision). Resting-order fill from minute 0 on carried bars unchanged. Unfilled expiry:
  position stays as it was until the next decision (no market fallback). In-position scale orders
  (adds/reduces/close) keep uniform `n_valid=2` (G2) — only the INITIAL flat-branch entry TTL varies.
- After a fill the position continues EXACTLY as G2: same grid policy (open/add/reduce/close/tighten,
  band max(0.03,0.40*|tg|), cool 6), same break-even (+2sd), same SL market taker 0.00055 / TP limit maker
  0.0002, same stop-first, same funding (longs 0.0001 per settlement in (T,T+4h], shorts 0), same
  governor/vol-target, same dip sleeve. SL/TP levels from the fill price with the SAME sd (psd at issue)
  and SAME multiples (m_sl=4.0, m_tp=None->8.0 sigma_d).
- Fees: entries maker 0.0002; SL legs taker 0.00055; TP legs maker 0.0002. Funding identical to G2.

## Engine (book idea: 4-phase engine vs G2, BINDING)

- Mechanism = byte-logic replica of v421 worker (v421_gross_cap.py: pipe_setup "v321", corr-aware inv sizes
  kd=1.7, bear books, risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0, win_start=5, gate costs inside) with ONLY
  the flat-branch `T["exp"]` assignment replaced by the conviction TTL above (V1/V2; REF/C rows unpatched,
  bit-exact G2). Dip sleeve, books (except C-row uniform scaling), governor, agents (R2 table sizes/TPs),
  funding, liquidation, min-notional unchanged. Patch via audited exec pattern (oc_booktwo/run_engine.py:
  assert unique anchors, replace in live eu module dict so the summarize override applies).
- Rows run (ONLY): REF + V1 + V2 + C_V1 + C_V2. REF must reproduce v421 G2 to the digit
  (dev years R/DD [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)] + Y4 (4.648/12.90),
  5y 5.410, full-path DD 16.82) — else STOP.
- Stages: dev [2021-09-24,2025-09-24) for all five rows (all four shifts); then
  last [2021-09-24,2026-09-23) ONCE for REF + the dev4 robust pick ONLY (every Y4 number labelled
  scored-once). Via heavy_slot (`--tag oc_convttl`, one job at a time; resume-safe caches
  tmp/std_books.pkl + tmp/shift_{s}.pkl + tmp/shift_last_{s}.pkl; heartbeat every 600 s; nohup + tmp log).
- Metrics/selection per OPENCODE_W_COMMON_20261007: per-year 4-phase reset %/mo + DD via
  reset_metric.year_reset; dev4 geo mean, W (worst-year R), max yearly DD, losing count; 5y geo mean;
  full-path DD via v388.mix from 2021-09-24 (max of close/marked); pooled book/all win rates (book_episodes
  walk as oc_memberagree) + fills/year + fee/funding split + TTL diagnostics (thresholds q50/q75 per year,
  long-TTL share p per year, mean TTL, fill rate per row/year). Robust pick on dev4 ONLY among REF/V1/V2:
  eligible DD<=20 and no losing dev year; prefer dev4 mean>=5, then highest dev4 WORST-year R,
  ties->higher mean. Controls reported, NOT eligible. Y4 never picks.
- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT. 1m via pod.minutes() float32 cube (same as v421);
  books = research_books_d2 + bear filter; opens = shifted-grid opens.

## Leakage / checks (stated in REPORT)

- Feature timing (TTL uses ffill'd w_base[i,a] from source row r <= t_s only, known at the decision close;
  px from O0 only; sd/s4 from bars <= decision-2 lag via engine; no re-peg; truncation-tested),
  label windows (no labels fit; exits mechanical), fit windows (quantiles q50/q75 from U < A_k-7d non-zero
  |w_base| only, frozen round quantiles 0.50/0.75; R2 size/TP agents pre-date anchors; C-row s_y in-year
  realised so diagnostic/non-eligible by construction), fill timing (entry strict trade-through + minute-5
  ban; SL market / TP limit; stop-first; NaN never fills). Gate costs inside all legs. No test-year or
  most-recent-year statistic feeds any eligible choice (dev pick uses 2021-2024 only; Y4 scored once for
  REF+pick).

## Compute plan

- `convttl.py`: pure helpers (ttl_for_weight, year_of_bar, mean_ttl_scale, threshold lookup) + no I/O.
- `run_convttl.py`: books builder (`--build-books`: w_ens/bear/q50/q75/p/s/C-rows + research_books_d2 check) +
  per-shift heavy runner (`--shift S --stage dev|last`: 4-phase engine replica, TTL patch for V1/V2) +
  scorer (`--score`: REF digit check + reset metric + v388.mix + win/fee/funding/TTL splits -> results.json).
- `results.json` (engine rows), REPORT.md. Tests `tests/test_oc_convttl.py` (>=1 causality/truncation +
  >=1 hand-checked synthetic; `.venv/Scripts/python.exe -m pytest tests/test_oc_convttl.py -q`).

## Post-hoc log

- 2026-10-08 (before any engine outcome; build-books factual fix): standard-grid books154 index
  starts 2021-09-24 (checked via eu.er.v154_books), so the Y0 pool U < A_0-7d is EMPTY (PLAN's
  "non-empty for every k / books from 2020" was wrong). Frozen fix: Y0 thresholds q50_0=q75_0=-1.0,
  i.e. rule INACTIVE in 2021 (every |w_base|>=0 exceeds -1, all TTL=2 = G2; C-row s=1.0 in Y0).
  Years 1-4 unchanged (pool = U < A_k-7d non-zero |w_base|, 2000+ rows/coin). No threshold, variant,
  engine, or selection change; no variant P&L seen.
