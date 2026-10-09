# oc_stopentry — PLAN (pre-registered BEFORE any outcome is computed, 2026-10-08 — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_stopentry.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md, IDEAS10_20261008.md idea #5 read in full, CLOSED rows cited read first).
Write ONLY `research/tournament/oc_stopentry/` + `tests/test_oc_stopentry.py`. Scratch only under
`research/tournament/oc_stopentry/tmp/`. GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/
rm/commit/switch/rebase/merge. Engine / heavy 1m work via `scripts/heavy_slot.py` (one job at a time,
float32). Long jobs: nohup + log under tmp/, poll the log; never inspect /proc or folders outside
the workspace. Heartbeat print every 600 s. Progress print every 10 minutes. PLAN.md frozen BEFORE
any outcome. No outcome has been computed.

## Why (IDEAS10_20261008.md idea #5, rank 5 — quoted, not refit)

Mech: book entries rest 10bps better and miss fast moves (late-fill trail costs 10-39bps, oc_filltime);
a buy-stop through the price buys CONFIRMATION — a different fill population (momentum vs value),
executable on Bybit as conditional orders.
Rule: V1 all book signals as stop-entries 5bps through the minute-0 price (taker 0.00055, minute-5
ban kept, SL/TP attached as now); V2 stop-entry only when |w| exceeds its pre-anchor median (chase
strong signals), passive limit otherwise.
Data: local 1m archive (have); book-engine variant in trade mode (engine_user); ~1-2 runs.
Effect: ±0.1 %/mo. Prior 7% (chasing usually pays spread — makerexit lesson: 91% save 4.5bps, 8%
remainder sells deeper).
Leak: stop distance and |w| median frozen ex-ante (median pre-anchor + embargo); fills on 1m
trade-THROUGH only (no stop-touch claim); stop-first kept.
CLOSED rows read first: stop-limit STOPS (rejected by user rules — this study is stop-ENTRY, explicitly
allowed; entries are conditional breakout orders, stops stay market SL as now); `oc_bookoffset`
(PLAN/REPORT — vol-scaled LIMIT offset, same passive fill family `low<L / high>L`, strict trade-through,
minute-5 ban; this study changes ORDER TYPE to stop-through, not the offset distance); `oc_earlystart`
(PLAN/REPORT — earlier TIME window 6..238 vs 16..238 at the SAME static level; this study changes the
PRICE side of the level, from better-than-open to through-open). Kept distinct per IDEAS10.

## Variants (exactly these + reference + two exposure-matched controls, no others)

- REF = G2 unchanged (v421 R2B1D17BFG2: rule inv, k 1.0, kd 1.7, bear True, G 2.0; v216 G2 grid
  trader on v212 S3 trade params: entry limit max(0.10%,0.25*sigma4h), n_valid 2 bars, win_start 5,
  SL 4 sigma_d market / TP 8 sigma_d limit, be_k 2.0, tighten 1.5, max_adds 1 + one 50% reduce,
  grid band max(0.03,0.40*|tg|), COOL 6 bars, THETA 0.05; dip sleeve untouched).
- V1_STOPALL = REF with EVERY flat->open book entry order as a stop-entry 5bps through the minute-0
  open (taker 0.00055 on the entry fill; minute-5 ban kept; SL/TP/BE/tighten/validity/dip unchanged;
  in-position adds/reduces/closes stay passive G2 limits — disclosed entry-only scope).
- V2_STRONG = REF with stop-entry ONLY when |w| exceeds its pre-anchor median for that (anchor, coin)
  (chase strong signals), passive G2 limit otherwise. |w| and medians per Signal below.
- C_V1 / C_V2 = exposure-matched constant controls (DIAGNOSTIC, in-year, not tradable, NOT eligible):
  REF mechanism (all passive limits) with per anchor year y a constant book multiplier
  `c_y = sum|V_fill_gross_y| / sum|REF_fill_gross_y|` (summed over the 4 shifts; book_fill |weight|
  sums from this study's own dev engine runs; fallback 1.0 when REF sum is 0/non-finite). Applied via
  engine_user `book_size` at order issuance (the entry's multiplier holds for the life of that order /
  position, same as G2 grid adds/reduces aiming at the scaled target). By construction C matches V's
  average filled exposure with no timing/selection. Uses test-year realised fills so NEVER picked.
- Claim rule (frozen): V "beats exposure" iff dev4 geometric mean R(V) > R(C_V) AND DDmax(V) <= DDmax(C_V).
  A stop-entry that trails its control is an exposure (fill-rate) story.
- S5_BYBIT row: for the dev4 robust pick + REF only, rerun on Bybit 1m (S5 harness of oc_c2bybit:
  bybit_minutes() from data/raw/bybit_linear_1m_20261004, live0 = 2021-11-15 + shift, standard index
  filtered to >= 2021-11-15 before shift, win_start=5). Year 2021 is a SHORT window (labelled). If Bybit
  files missing/unreadable, S5 = not reproducible (no silent fallback).
- Frozen numbers (never fit): stop distance 0.0005 (5bps); THETA 0.05; band (0.03,0.40); COOL 6;
  entry/SL/TP/BE/tighten/validity/win_start unchanged except the entry side/fee below. No other knob.

## Exact causal definitions (frozen before seeing numbers)

- Symbols: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- Books: fw.research_books_d2(eu) on the standard v154 index, bear-halved on standard rows (BTC 4h open
  < 1200-bar mean halves LONG targets), ffilled to each shift grid (same as oc_chronos/run_engine.py).
- Minute-0 price P0[i,a] = 1m open at minute 0 of holding bar i for coin a (O[i,0,a] of the engine cube;
  known at the bar open T = idx[i]+4h). Stop level (entry orders only):
  long (sgn>0): `P_stop = P0*(1+0.0005)`; short (sgn<0): `P_stop = P0*(1-0.0005)` (5bps THROUGH).
  Passive G2 limit (unchanged): `P_lim = P0*(1-sgn*off)`, `off=max(0.001,0.25*s4)` (better-than-open).
- ENTRY SCOPE (frozen, disclosed): only flat->open orders (cur_q==0, no resting order, new `order_issue`)
  are routed stop vs passive. Resting-order carry across bars keeps the side/price fixed at issuance
  (a resting stop stays a stop until fill/cancel/expire). In-position adds/reduces/closes, SL/TP/BE/tighten,
  dip ladder: UNCHANGED (same offsets/validity/fees as G2).
- FILL (strict trade-THROUGH, ft=0, no stop-touch claim): new stop order fillable over minutes
  [win_start,240) = [5,240) of its issuance bar (minute-5 ban kept); resting stop from an earlier bar
  fillable from minute 0 of later bars (same carry rule as G2 resting limits). Long stop fills iff
  `max(Hi[win:]) > P_stop` (strictly through; touch `==` does NOT fill); short stop fills iff
  `min(Lo[win:]) < P_stop`. Fill price = P_stop (the stop level; queue-position assumption labelled:
  breakout fills claim the level on a through-trade, same conservatism as G2 limit fills claiming theirs).
  Fill fee = TAKER 0.00055 on the entry notional (IDEAS10: stop-entries are taker). Passive fills stay
  maker 0.0002. First through-minute wins; unfilled -> expires after n_valid=2 bars (same as G2).
- SL/TP attached as now (user rule): SL = entry*(1-ps*4*sigma_d) market taker 0.00055, TP = entry*(1+ps*8*sigma_d)
  limit maker 0.0002 (m_tp=8 default from S3 trade params via v216.GRID; engine handles). Checked every 1m bar;
  stop-first on any same-minute stop+TP touch (engine handles). BE at +2 sigma_d, tighten 1.5 on opposite
  signal: unchanged.
- Signal |w| (V2 gate only): `|w[i,a]|` = absolute post-bear standard-grid book weight for (coin a,
  decision bar with holding open T) — after bear halving, BEFORE vol-target/governor/ffill (variant-independent,
  close-known, no engine state). Pre-anchor median `med_k[a]` = median of finite |w| over standard-grid rows
  with time in [2021-09-24, A_k-7d), per (anchor A_k, coin a); requires >=120 finite observations else NaN.
  Anchor 2021 has an empty window by construction (books start 2021-09-24) -> all medians NaN -> V2 uses passive
  limits for the whole 2021 year (disclosed fallback, conservative, never a stop). V2 route per new entry order
  at (i,a) in year k: stop iff finite |w[i,a]| and finite med_k[a] and |w[i,a]| > med_k[a]; else passive.
  Year of T on shift s: [A_y+s, min(A_y+s+365d, live1)) with A=(2021..2025-09-24), same anchor_of as oc_c2bybit.
  Medians frozen ex-ante (computed once from books+fills-free history, written to tmp/stop_meds.json before any
  engine run; no test-year statistic feeds any choice beyond the disclosed in-year C controls).
- Gate costs inside the engine (unchanged): maker 0.0002 (passive entries/TP/closes), taker 0.00055
  (stop entries, stops, market exits), adverse long funding 0.0001 per 8h settlement held / shorts 0,
  no fill minutes 0-4 for NEW orders, stop-first in the same 1m bar (engine handles).

## Inputs (read-only, never edited)

- Books: `scripts/forward_v205.py:research_books_d2(eu)` (= 0.8*O1 + 0.2*(D+Dq)/2, union index,
  missing->0.0) from `artifacts/research/engine_real/` member caches (this idea is NOT a retraining idea;
  REF==research_books_d2 to <1e-12 by the V0 gate below).
- Opens: `artifacts/research/engine_real/opens_v154.parquet` via `eu.er.v154_books()` (4h opens);
  1m klines via `pod.minutes()` float32 cube (same as v421) for base; Bybit 1m from
  `data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet` (cols open_time ms, open/high/low/close) for S5 only.
- R2 size/TP agents: `artifacts/research/engine_real/v321_r2_table_m0.parquet` via hist.R2_TABLE
  (same as v421 pipe; dip size/TP lookups, no refit).
- Symbols, market-data cap 2026-09-23 (assignment override; all five years are research data; any finding
  needs prospective validation).

## Engine (fixed: 4-phase, exactly v421 G2 R2B1D17BFG2 + stop patch)

- Byte-logic replica of v421/v421_gross_cap.py::worker for R2B1D17BFG2 (rule inv, k 1.0, kd 1.7, bear True,
  G 2.0): per shift s in {0,1,2,3}: pod.minutes() 1m (or bybit_minutes() for S5), prep_idx(M,
  books154.index+s, s, cols), books ffill'd to the shifted clock, pipe_setup("v321", hist, v221, v216,
  idx, cols, True) + corr_size inv/kd=1.7 + risk_mult k=1.0 + sleeve_risk_budget 0.26*1.0*1.7 +
  sleeve_gross_cap 2.0, patched simulate(books_bear, opens, prep, trade=trade, win_start=5, events=ev,
  bars=bars, stop_route=..., book_size=... for C rows). Books per row: REF/V1/V2 share the SAME post-bear
  books (entry execution differs); C_V1/C_V2 use REF books with per-year book_size=c_y (after bear, before ffill
  equivalent via issuance scaling). Trade per row: REF/C_* use v216.grid_policy(0.03,0.40); V1/V2 wrap issuance
  with the stop route above (same band/cooldown/THETA/policy, plus the entry-side switch). Dip sleeve, governor,
  agents, funding, liquidation, min-notional unchanged.
- Patched engine asserts verbatim source anchors and is bit-identical to the audited engine_user when
  stop_route=None and book_size=None (REF gate). Stop fills are the ONLY behavioural delta for V rows.
- REPRODUCE FIRST: REF must reproduce v421_result R2B1D17BFG2 (R 5.41 / max yearly DD 16.91 / full-path DD
  16.82, yearly rows [(2.588,10.86),(3.282,16.91),(6.045,15.81),(10.677,8.27),(4.648,12.90)]) to the digit
  before any other row is scored; if not, STOP and report.
- Rows run (ONLY): dev stage REF+V1+V2 first; then C_V1+C_V2 dev (c_y from the dev runs); last stage REF +
  dev4 pick ONLY (controls never run in the last stage; Y4 numbers labelled scored-once); S5 dev stage REF +
  dev4 pick ONLY (short-2021 labelled). Via heavy_slot, one job at a time; resume-safe caches
  tmp/runs_dev_base.pkl + tmp/runs_last_base.pkl + tmp/runs_dev_S5.pkl (+ tmp/stop_meds.json, tmp/ctrl.json);
  heartbeat every 600 s; nohup + tmp log.
- If anything changes after seeing an outcome, the original row stays and the change is added as a disclosed
  extra row (none planned).

## Scoring (fixed)

- Anchors Y0..Y4 = 2021..2025-09-24, year = [A, A+365d). Dev4 = Y0..Y3; Y4 (2025-09-24..2026-09-23) scored
  ONCE for REF + dev4 pick only (labelled REF; never a selection input); 5y = years 0..4 (context).
- Per row x year: 4-phase reset metric R + yearly DD via research/diagnostics/r2_decompose5/reset_metric.py::year_reset
  (same as v421), full-path DD via v388.mix continuous path (max of marked/close, v421 convention). Full-path DD one
  number per row over 2021-09-24..2026-09-23 (dev rows: full path uses dev runs + last runs when available; S5 uses
  its own dev-window path labelled). 5y mean = geometric mean of the five yearly R.
- Book episodes + fee split: engine events walked as v213.trade_stats book trades (after fees) per year + rung
  tp/sl/timeout counts (same collection as oc_chronos run_engine.py): per year book trades + win rate, rung count +
  win rate, pooled all-trade win rate, fills/year, stop-entry share of fills + stop-vs-passive fill-rate split
  (from entry_type in events), engine stats totals (fills/stops/tps/fees/funding/issued/cancelled/expired).
- Exposure diagnostic per row x year: filled-gross ratio sum|V_fill|/sum|REF_fill| (= c_y for C rows by construction;
  engine time-in-position share reported descriptively).
- Selection: robust criterion on dev4, REF + V1 + V2 only (controls reported, NOT eligible): eligible iff DDmax
  (max of max-yearly-DD and full-path DD) <= 20 and no losing dev year; prefer dev4 mean >= 5 %/month, then highest
  dev4 WORST-year monthly return, ties -> higher mean. (If none eligible, pick = "none-eligible" and the last/S5
  stages run REF only.) Y4 never picks.

## Leakage statement (how checked; fixed)

- Feature timing: P0 from minute-0 1m open (known at T); stop levels from P0 only; |w|/med from close-known book
  weights with bars <= decision (shifted clocks use latest standard row r <= t_s, ffill; identity at s=0); V2 route
  uses only (issuance-bar |w|, frozen med_k). Truncation-tested in tests/test_oc_stopentry.py (post-T data cannot
  move the stop level/route; pre-THETA signals never open).
- Label windows: no labels fit anywhere (entries mechanical stop/passive, exits SL/TP/timeout).
- Fit windows: none tradable in this study (stop 5bps + THETA/band/COOL frozen ex-ante; R2 size/TP agents pre-date
  anchors; med_k from [2021-09-24, A_k-7d) with >=120 obs else NaN->passive; C_* use in-year realised fills so
  labelled diagnostic/non-eligible and never picked; S5 is a price-source switch, not a fit).
- Fill timing: patched trade-mode (stop/passive trade-through, no fill minutes 0-4 for NEW orders, stop-first).
  Gate costs inside every leg (stop entries taker). No test-year statistic feeds any tradable choice (dev pick uses
  2021-2024 only; Y4/S5 scored once for REF+pick).
- CLOSED rows oc_bookoffset/oc_earlystart + stop-limit-STOP distinction read; this direction closes in this form
  whatever the outcome.

## Deliverables / resources (fixed)

research/tournament/oc_stopentry/: PLAN.md (this file, BEFORE any outcome), stop_rule.py (pure helpers: STOP_OFF,
medians, route matrix, control_mult; no I/O), stop_patch.py (verbatim engine_user + STOP PATCH, asserted),
compute_stopentry_engine.py (per-shift heavy runner; HEAVY via heavy_slot), analyze_stopentry.py (scoring +
results.json; LIGHT), results.json, REPORT.md.
Tests: tests/test_oc_stopentry.py (>=1 causality/truncation test + >=1 hand-checked synthetic case), run with
`.venv/Scripts/python.exe -m pytest tests/test_oc_stopentry.py -q`.
HEAVY: `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_stopentry --min-free-gb 2.0 -- <cmd>`
(never --leader); one shift per heavy job preferred, all book/entry variants sequentially inside the job reusing
one minutes load. Write ONLY research/tournament/oc_stopentry/ + the test file. No commits.

## Post-hoc log

- 2026-10-08, after dev/last/S5 outcomes: stop_patch recorded every stop fill with entry_type
  "limit" (the is_stop flag was cleared one statement before the book_fill event; caught by the
  tmp/dbg_stop.py synthetic — fill price/minute/fee were already exact). Fixed to use the pre-clear
  local _fill_stop in the event + counter + fee lines. LABEL-ONLY: V1/V2 re-ran bit-identical
  (equity, R/DD, ctrl.json unchanged); only stop_share diagnostics changed. Original rows kept;
  no extra variant.
