# oc_weeklybook PLAN (pre-registered BEFORE any outcome is computed, 2026-10-08 — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_weeklybook.md` (= IDEAS10 §6, rank 6) +
`docs/opencode/OPENCODE_W_COMMON_20261007.md` (+ AGENTS.md, OPENCODE_VF_COMMON.md,
`docs/opencode/IDEAS10_20261008.md` §6 + CLOSED rows `oc_cadence` + `v335` + `oc_tsmom` read in full).
Write ONLY `research/tournament/oc_weeklybook/` + `tests/test_oc_weeklybook.py`.
Engine / heavy 1m work via `scripts/heavy_slot.py` (one job at a time, float32).
Long jobs: nohup + log under `tmp/`; never inspect /proc or folders outside the workspace.
CPU only (no GPU). Progress print every ~10 min. Scratch only under
`research/tournament/oc_weeklybook/tmp/`, never the system temp folder.
GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge.
No orders, no authenticated endpoints, no Kaggle uploads.
PLAN.md frozen BEFORE any outcome. No outcome has been computed.

## Why (IDEAS10 §6, rank 6 — quoted, not refit)

Weekly-decision book sleeve (slow diversifier, f=0.10) alongside 4h G2.
Why: all book edge is tested at 4h (skill at h=1..18 bars, oc_bookichorizon); a slow
sleeve trades a DIFFERENT autocorrelation band and rebalances rarely (few fees,
human-followable) — judged on CORRELATION to G2, not standalone return.
Exp: V1 weekly-bar book (Wednesday 00 UTC phase, frozen) at f=0.10 overlaid on G2;
V2 f=0.25. Same members, weekly pooled label; selection on the dev4 overlay
(return AND sleeve-corr <0.7).
Data/harness/cost: local 4h bars resampled weekly (free); book-engine weekly variant +
equity overlay; ~1 run. Prior 6% (oc_cadence 8h/12h: stale drag >> fee save;
v335 daily 1.17-2.09 vs 4h 3.01).
Leak: phase (Wednesday) frozen ex-ante — report the other 6 phases as a clock-luck
diagnostic (lesson 4); weekly label fit pre-anchor + embargo; no phase-picking.
Closest CLOSED: oc_cadence (SLOWED the whole book — this ADDS a small slow sleeve);
v335 (daily MANUAL — different product and scale); oc_tsmom (slow TREND sleeve —
this is the same book MODEL on a slower clock).
CLOSED rows read first: `oc_cadence` (PLAN/REPORT — 8h cadence slows the WHOLE book:
NOT PROMISING 2/5 P&L + 1/5 DD; stale gross drag dwarfs fee save; this study KEEPS the
4h book intact and ADDS a small slow sleeve), `oc_tsmom` (PLAN/REPORT — 0.25x 30d-TSMOM
overlay lifts return 5/5 but worsens DD 5/5, corr +0.17..+0.47: correlated add-on, not
a diversifier; this study uses the SAME book model on a slower clock, judged on
corr <0.7), `v335` (daily MANUAL product 1.17-2.09 vs 4h 3.01 cited in the idea;
different product/scale, not re-scored here). Distinct per IDEAS10 near-duplicate note. Kept.

## Variants (exactly two + reference + two exposure-matched controls, no others)

- REF = G2 unchanged (v421 R2B1D17BFG2: rule inv, k 1.0, kd 1.7, bear True, G 2.0;
  v216 G2 grid trader on v212 S3 trade params: entry limit max(0.10%,0.25*sigma4h),
  n_valid 2 bars, win_start 5, SL 4 sigma_d market / TP 8 sigma_d limit, be_k 2.0,
  tighten 1.5, max_adds 1 + one 50% reduce, grid band max(0.03,0.40*|tg|), COOL 6 bars,
  THETA 0.05; dip sleeve untouched).
- V1 = REF book + weekly slow sleeve f=0.10 (frozen): per standard-grid 4h bar T,
  `w_V1(T) = w_fast(T) + 0.10 * w_slow(T)` (post-bear weights; dip untouched).
- V2 = same with f=0.25: `w_V2(T) = w_fast(T) + 0.25 * w_slow(T)`.
- C_V1 = exposure-matched constant control for V1 (DIAGNOSTIC, in-year, not tradable,
  NOT eligible): per anchor year y, `w_CV1(T) = c_y * w_REF(T)` every bar of that year
  (after bear, before ffill), where `c_y = sum|w_V1| / sum|w_REF|` over that year's
  standard-grid (T,s) cells (gross exposure ratio from the pre-engine book construction
  below; uses test-year data so NOT tradable). Same C_V2 with V2 gross.
- Claim rule (frozen): V "beats exposure" iff dev4 geometric mean R(V) > R(C)
  AND DDmax(V) <= DDmax(C). A slow sleeve that trails its control is an exposure story.
- Frozen numbers (never fit): f 0.10 / 0.25, Wednesday 00 UTC phase, THETA 0.05,
  band (0.03,0.40), COOL 6, entry/SL/TP/BE/tighten/validity/win_start unchanged.
  No other threshold/scale.

## Weekly slow sleeve (frozen, causal, no refit)

- Members (frozen, no retraining — "same members"): book weights =
  `scripts/forward_v205.py:research_books_d2(eu)` (= 0.8*O1 + 0.2*(D+Dq)/2, union
  index, missing->0.0) from `artifacts/research/engine_real/` member caches
  (read-only). No new label is fit: the "weekly pooled label" of the idea is
  implemented as pure time-aggregation of the same 4h member weights (no parameter,
  no threshold, no quantile); the fit window is therefore vacuous and the 7-day
  embargo is satisfied by construction (nothing is estimated). Disclosed as such.
- Fast leg: `w_fast` = post-bear REF book row at standard-grid T (NaN->0.0, exactly
  as the engine's fillna(0.0)); bear filter EXACTLY as v421
  (`btc = opens_std BTC reindexed to books154.index`,
  `bear = (btc < rolling(1200,min600).mean())`, `longs x0.5 on bear rows`).
- Slow leg: weekly anchors W = all Wednesdays 00:00 UTC (frozen phase).
  `w_slow(T) = w_fast(W*(T))` where `W*(T) = max{W : W <= T}` (last Wednesday-midnight
  row at or before T, post-bear, NaN->0.0); for T before the first Wednesday anchor
  at/after the grid start, `w_slow(T) = 0` (no lookback beyond the grid; causal).
  Slow is a step function changing only on Wednesdays 00 UTC; strictly causal since
  `W*(T) <= T` and `w_fast(W*)` uses closes <= W*.
- Overlay: `w_V(T) = w_fast(T) + f * w_slow(T)` per (T,s) on the standard grid
  (after bear, before shifted-clock ffill). Engine forward-fills each variant's books
  to its shifted holding clock with the same causal ffill (latest standard row <= t_s).
- Clock-luck diagnostic (LIGHT, proxy only, no engine, never picked): the same slow
  construction for the other 6 weekday-00-UTC phases (Mon,Tue,Thu,Fri,Sat,Sun),
  proxy-scored only (gross/net correlation + net P&L vs Wednesday). No phase-picking:
  Wednesday stays the reported phase whatever the diagnostic shows.
- Sleeve-corr (frozen diversifier gate): per anchor year, Pearson corr of per-bar
  standard-grid proxy NET returns (see scoring-proxy below) of the slow sleeve
  standalone (f=1.0 leg: `r_slow`) vs the fast leg (`r_fast`). PROMISING requires
  max yearly corr over the 4 dev years < 0.7 (strict; NaN = FAIL). Descriptive only
  beyond the gate (standalone slow P&L reported, not gated).

## Inputs (read-only, never edited)

- Books: `scripts/forward_v205.py:research_books_d2(eu)` from
  `artifacts/research/engine_real/` member caches (read-only; this idea is NOT a
  retraining idea so no per-anchor training and no builder-reproduction check beyond
  REF==research_books_d2 to <1e-12).
- Opens: `artifacts/research/engine_real/opens_v154.parquet` via `eu.er.v154_books()`
  (4h opens); 1m klines via `pod.minutes()` float32 cube (same as v421, Binance).
  Bybit S5 leg: `data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet` via the
  `oc_c2bybit` harness (read-only).
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-23 may be read (assignment override; all five years are
  research data; any finding needs prospective validation).
- No new data (per IDEAS10; same members + time aggregation only).

## Engine (fixed: 4-phase, exactly v421 G2 R2B1D17BFG2 + book-row patch)

- Byte-logic replica of v421/v421_gross_cap.py::worker for R2B1D17BFG2 (rule inv,
  k 1.0, kd 1.7, bear True, G 2.0): per shift s in {0,1,2,3}: pod.minutes() 1m,
  prep_idx(M, books154.index + s, s, cols), books ffill'd to the shifted clock,
  pipe_setup("v321", hist, v221, v216, idx, cols, True) + corr_size inv/kd=1.7 +
  risk_mult k=1.0 + sleeve_risk_budget 0.26*1.0*1.7 + sleeve_gross_cap 2.0,
  eu.simulate(books_bear, opens, prep, trade=trade, win_start=5, events=ev).
  Books per row: REF/V1/V2/C_V1/C_V2 share the pipeline above with different
  pre-ffill standard-grid books (REF pre = research_books_d2; V1/V2 pre = fast+f*slow;
  C_* pre = REF pre x per-year constant c_y). Trade policy identical G2 grid for ALL
  five rows (no policy patch; this is a book-target idea). Dip sleeve, governor,
  agents (R2 tables), funding, liquidation, min-notional unchanged.
- Gate costs are the engine's own (unchanged): maker 0.0002 (entries/TP/closes),
  taker 0.00055 (stops/market exits), adverse long funding 0.0001 per 8h settlement
  held / shorts 0, no fill minutes 0-4 after a 4h close, stop-first in the same 1m bar.
- REPRODUCE FIRST: REF must reproduce v421_result R2B1D17BFG2 (R 5.41 / max yearly
  DD 16.91 / full-path DD 16.82, yearly rows
  [(2.588,10.86),(3.282,16.91),(6.045,15.81),(10.677,8.27),(4.648,12.90)])
  to the digit before any other row is scored; if not, STOP and report.
- Rows run (ONLY): dev stage REF+V1+V2+C_V1+C_V2; last stage REF + dev4 pick ONLY
  (controls never run in the last stage; Y4 numbers labelled scored-once); S5 stage
  REF + dev4 pick ONLY on Bybit 1m (friction row, dev window; Y4 not run on Bybit).
- Stages: dev [2021-09-24,2025-09-24) for the five rows (REF first); then last
  [2021-09-24,2026-09-23) ONCE for REF + the dev4 robust pick ONLY (every Y4 number
  labelled scored-once); then S5 [2021-11-15,2025-09-24) ONCE for REF + pick on Bybit
  prices (year 2021 = short window from 2021-11-15, disclosed, friction row only).
  Via heavy_slot, one job at a time; resume-safe caches
  tmp/runs_dev.pkl + tmp/runs_last.pkl + tmp/runs_s5.pkl (+ tmp/std_books.pkl,
  tmp/controls.json); heartbeat every 600 s; nohup + tmp log.

## Scoring-proxy (LIGHT, standard grid, diagnostic scale only)

- Grid: inner join of the REF book index with the opens index over
  [2021-09-24,2026-09-23), sorted 4h; every kept bar must have all 5 forward opens
  non-NaN (last bar dropped). Returns `R1[T,s] = open[T+1]/open[T]-1`.
  Costs 0.0005/unit turnover per (T,s) with each leg's own prev (first prev 0):
  net cell = `W*R1 - 0.0005*|W-W_prev|`. Per-bar portfolio net `rp[T]=sum_s net`.
  Used ONLY for: exposure ratios c_y, sleeve-corr, phase diagnostic, standalone slow
  stats. Engine equity (with SL/TP/funding/1m fills) is the binding scale; proxy
  never overrides it.

## Scoring (fixed)

- Anchors Y0..Y4 = 2021..2025-09-24, year = [A, A+365d). Dev4 = Y0..Y3;
  Y4 (2025-09-24..2026-09-23) scored ONCE for REF + dev4 pick only (Binance).
- Per row x year: 4-phase reset metric R + yearly DD via
  research/diagnostics/r2_decompose5/reset_metric.py::year_reset (same as v421),
  full-path DD via v388.mix continuous path (max of marked/close, v421 convention).
  Full-path DD one number per row over 2021-09-24..2026-09-23 (dev stage: dev window
  only for the gate table; last stage: full window). 5y mean = geometric mean of the
  five yearly R (dev stage: 4y only; last stage: 5y with Y4 labelled).
- Book episodes + fee split: engine events walked as oc_memberagree::book_episodes
  (v213-style book_fill/add/reduce/stop/tp/close + rung tp/sl/timeout): per year book
  episode count + win rate (net of fees), rung count + win rate, fee split = maker vs
  taker fees summed over book episodes in that year + engine stats totals
  (fees/funding/fills/stops/tps). Book-only P&L NOT separable from equity (engine stores
  t/eq/eq_min only, same as v421) — reported as not separable.
- Exposure diagnostic per row x year: standard-grid gross ratio
  sum|w_row|/sum|w_REF| (= c_y for C rows by construction; V proxy ratios reported;
  engine time-in-position share reported descriptively).
- Selection: robust criterion on dev4, REF + V1 + V2 only (controls reported, NOT
  eligible; S5 never eligible): eligible iff DDmax <= 20 and no losing dev year;
  prefer dev4 mean >= 5 %/mo, then highest dev4 WORST-year monthly return,
  ties -> higher mean. (If none eligible, pick = "none-eligible" and the last stage
  runs REF only.) Y4 never picks.
- PROMISING (idea gate, frozen): the dev4 robust pick is V1 or V2 (beats REF under
  the robust rule) AND its sleeve-corr gate holds (max dev4 yearly slow-vs-fast proxy
  corr < 0.7) AND it beats its exposure-matched control (R(V) > R(C) AND DD(V) <= DD(C)).
  Otherwise NOT PROMISING. S5 is a friction row only (reported, never gated).

## Leakage statement (how checked; fixed)

- Feature timing: w_fast uses closes <= T only (cached member weights are close-known;
  shifted clocks use latest standard row r <= t_s, ffill); w_slow uses only the weekly
  anchor W* <= T (truncation-tested: post-Wednesday data cannot move the slow leg).
- Label windows: no labels fit anywhere (slow = aggregation of frozen member weights;
  no weekly label estimated; vacuous fit window disclosed).
- Fit windows: none in this study (f 0.10/0.25 + Wednesday phase frozen ex-ante;
  R2 size/TP agents pre-date anchors; C_* use in-year realised means so labelled
  diagnostic/non-eligible and never picked).
- Fill timing: engine trade-mode (limit trade-through, no fill minutes 0-4, stop-first).
  Gate costs inside every leg. No test-year statistic feeds any choice (dev pick uses
  2021-2024 only; Y4 scored once for REF+pick; S5 scored once for REF+pick as friction).
- CLOSED rows oc_cadence/oc_tsmom/v335-citation read; this direction closes in this form
  whatever the outcome.

## Deliverables / resources (fixed)

research/tournament/oc_weeklybook/: PLAN.md (this file, BEFORE any outcome),
weeklybook_rule.py (pure helpers: weekly anchors, slow sampling, overlay, control_mult,
sleeve_corr; no I/O), compute_books.py (REF books + bear + weekly slow + controls +
phase/proxy diagnostics; LIGHT), run_engine.py (per-shift heavy runner + scorer;
HEAVY via heavy_slot; dev/last/S5), analyze.py (dev scoring + robust pick + corr gate;
LIGHT), analyze_last.py (last + S5 scored-once tables; LIGHT), results.json, REPORT.md.
Tests: tests/test_oc_weeklybook.py (>=1 causality/truncation test + >=1 hand-checked
synthetic case), run with `.venv/Scripts/python.exe -m pytest tests/test_oc_weeklybook.py -q`.
HEAVY: `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_weeklybook
--min-free-gb 2.0 -- <cmd>` (never --leader); one shift per heavy job preferred,
all five book rows sequentially inside the job reusing one minutes load.
Write ONLY research/tournament/oc_weeklybook/ + the test file. No commits.

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original
  row stays and the change is a disclosed extra row.)
