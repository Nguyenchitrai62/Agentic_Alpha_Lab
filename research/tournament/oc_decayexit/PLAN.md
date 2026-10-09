# oc_decayexit PLAN (pre-registered BEFORE any outcome is computed, 2026-10-08 — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_decayexit.md` (= IDEAS8 §6, rank 6) +
`docs/opencode/OPENCODE_W_COMMON_20261007.md` (+ AGENTS.md, OPENCODE_VF_COMMON.md,
`docs/opencode/IDEAS8_20261008.md` §6 + CLOSED rows `oc_bookholdcap` + `oc_bookexit` read in full).
Write ONLY `research/tournament/oc_decayexit/` + `tests/test_oc_decayexit.py`.
Engine / heavy 1m work via `scripts/heavy_slot.py` (one job at a time, float32).
Long jobs: nohup + log under `tmp/`; never inspect /proc or folders outside the workspace.
CPU only (no heavy local GPU). Progress print every ~10 min. Scratch only under
`research/tournament/oc_decayexit/tmp/`.
GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge.
No orders, no authenticated endpoints, no Kaggle uploads.
PLAN.md frozen BEFORE any outcome. No outcome has been computed.

## Why (IDEAS8 §6, rank 6 — quoted, not refit)

Mech: stale drag >> fee save (oc_cadence: slower cadence P&L 2/5); fixed 42-bar cap
failed (oc_bookholdcap) because it holds decayed losers and cuts live winners equally.
Exit on signal DEATH, not on the clock.
Rule: remember entry |w0|; exit (limit, maker) when |w| < 0.3*|w0| (V1), V2 0.5x;
sign-flip exit kept; winners ride to flip. SL/TP unchanged, minute-5 ban kept.
Data: engine state only. Harness: engine vs G2 (fee/funding split reported).
Effect: +0.0-0.08%/mo, DD flat/-0.2pp. Prior 9%.
Leak: |w0|,|w| close-known only; fraction frozen; no future signal.
CLOSED rows read first: `oc_bookholdcap` (PLAN/REPORT — FIXED 42-bar same-sign cap,
one-bar flat then resume; NOT PROMISING 2/5 P&L + 2/5 DD; this study exits on
SIGNAL-RELATIVE decay, not a bar count) / `oc_bookexit` (PLAN/REPORT — learned
+1.0 ATR bank on HGB P(reach +1.5 ATR before -1.0 ATR); win rate up but P&L collapse;
this study is a FROZEN FRACTION of entry signal, no model, no price bank).
Distinct per IDEAS8 near-duplicate note. Kept.

## Variants (exactly two + reference + two exposure-matched controls, no others)

- REF = G2 unchanged (v421 R2B1D17BFG2: rule inv, k 1.0, kd 1.7, bear True, G 2.0;
  v216 G2 grid trader on v212 S3 trade params: entry limit max(0.10%,0.25*sigma4h),
  n_valid 2 bars, win_start 5, SL 4 sigma_d market / TP 8 sigma_d limit, be_k 2.0,
  tighten 1.5, max_adds 1 + one 50% reduce, grid band max(0.03,0.40*|tg|), COOL 6 bars,
  THETA 0.05; dip sleeve untouched).
- V1 = REF with ONLY the in-position policy extended by a frozen signal-decay
  full close: frac 0.3 (exit limit maker when |tg| < 0.3*|w0|; sign-flip tighten+close
  kept; winners ride to flip; SL/TP unchanged).
- V2 = same with frac 0.5.
- C_V1 = exposure-matched constant control for V1 (DIAGNOSTIC, in-year, not tradable,
  NOT eligible): per anchor year y, `w_CV1(T) = c_y * w_REF(T)` every bar of that year
  (after bear, before ffill), where `c_y = sum|w_V1proxy| / sum|w_REF|` over that year's
  standard-grid (T,s) cells (gross exposure ratio from the pre-engine proxy simulation
  below; uses test-year data so NOT tradable). Same C_V2 with V2 proxy.
- Claim rule (frozen): V "beats exposure" iff dev4 geometric mean R(V) > R(C)
  AND DDmax(V) <= DDmax(C). A decay exit that trails its control is an exposure story.
- Frozen numbers (never fit): frac 0.3 / 0.5, THETA 0.05, band (0.03,0.40), COOL 6,
  entry/SL/TP/BE/tighten/validity/win_start unchanged. No other threshold/scale.

## Decay rule (frozen, causal, engine-state only)

- Signal definition: `tg` = the policy's book target for the coin at decision `i`
  (post-bear book weight x vol-target x governor, same scaled units G2 sizes on;
  known at the close of bar `i`). `sgn` = sign(tg) if |tg| >= THETA (0.05) else 0
  (same as G2). `|w|` in IDEAS8 = |tg| current; `|w0|` = |tg_entry| at the flat->open
  decision that issued the current position's entry order (frozen for the life of
  the position, never updated on adds; disclosed: vol/governor scaling is part of tg).
- Per-coin state: `w0[a]` (None when flat). Flat decision (st["pos"]==0, no position):
  G2 logic (`open`/`wait`); if returning `open`, set `w0[a] = |tg|` (>0 by THETA);
  if `wait`, keep None. In-position decision (st["pos"]==side != 0):
  1. reversal (`sgn == -side`): `{"tighten":1,"close":1}` if close valid else `tighten`
     (sign-flip exit KEPT, identical to G2).
  2. decay (`|tg| < frac * w0[a]`): `close` if close valid else `hold` (full limit exit,
     maker, same offsets/validity as G2 closes; sgn==0 is a subcase since 0 < frac*w0).
  3. else G2 grid logic unchanged (cooldown, band adds/reduces, hold; BE/tighten/SL/TP
     mechanical paths untouched).
  On position close (cur_q==0 at bar end / SL/TP/close fill), `w0[a]` cleared at the
  next flat decision (None until the next open). Unfilled entry expiry: next flat
  decision overwrites/clears per the same rule (no carry of stale w0).
- Winners ride to flip: a position whose signal stays `|tg| >= frac*w0` is NEVER forced
  out by the decay rule (no clock cap); it rides until flip, signal-gone (subcase),
  SL/TP, or G2 band logic — i.e. decayed losers are cut, live winners are kept
  (the oc_bookholdcap failure mode is avoided by construction).
- Execution of the decay close: identical to a G2 signal-gone limit close (resting limit
  `O0*(1+side*off)`, `off=max(0.001,0.25*s4)`, valid 2 bars, fill only on strict
  1m trade-through from minute 5, maker 0.0002; SL market taker 0.00055 / TP limit maker
  0.0002; stop-first in the shared minute; minute-5 ban kept). SL/TP levels, BE, tighten
  distances, entry offsets/validity, dip sleeve: UNCHANGED.
- Standard-grid proxy for the controls (pre-engine, causal, no fills/SL/TP):
  per coin in grid order on post-bear standard-grid weights with THETA 0.05:
  flat + sgn!=0 -> enter (w0=|tg|, proxy weight = tg); in side + sgn==-side ->
  flip-enter (w0=|tg|, proxy = tg); in side + |tg|<frac*w0 -> flat (proxy 0, clear w0);
  else proxy = tg (hold). Zeros break nothing (proxy follows tg). History continuous
  across year boundaries for state, but `c_y` ratios are per-year sums. Proxy is a
  diagnostic exposure scalar only (engine fills/SL/TP not modelled); disclosed.

## Inputs (read-only, never edited)

- Books: `scripts/forward_v205.py:research_books_d2(eu)` (= 0.8*O1 + 0.2*(D+Dq)/2,
  union index, missing->0.0) from `artifacts/research/engine_real/` member caches
  (read-only; this idea is NOT a retraining idea so no per-anchor training and no
  builder-reproduction check beyond REF==research_books_d2 to <1e-12).
- Opens: `artifacts/research/engine_real/opens_v154.parquet` via `eu.er.v154_books()`
  (4h opens); 1m klines via `pod.minutes()` float32 cube (same as v421).
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-23 may be read (assignment override; all five years are
  research data; any finding needs prospective validation).
- No new data (per IDEAS8; engine state only).

## Engine (fixed: 4-phase, exactly v421 G2 R2B1D17BFG2 + policy patch)

- Byte-logic replica of v421/v421_gross_cap.py::worker for R2B1D17BFG2 (rule inv,
  k 1.0, kd 1.7, bear True, G 2.0): per shift s in {0,1,2,3}: pod.minutes() 1m,
  prep_idx(M, books154.index + s, s, cols), books ffill'd to the shifted clock,
  pipe_setup("v321", hist, v221, v216, idx, cols, True) + corr_size inv/kd=1.7 +
  risk_mult k=1.0 + sleeve_risk_budget 0.26*1.0*1.7 + sleeve_gross_cap 2.0,
  eu.simulate(books_bear, opens, prep, trade=trade, win_start=5, events=ev).
  Books per row: REF/V1/V2 share the SAME post-bear books (policy differs);
  C_V1/C_V2 use REF books x per-year constant `c_y` (after bear, before ffill).
  Trade per row: REF/C_* use v216.grid_policy(0.03,0.40); V1/V2 use
  decay_policy(0.03,0.40,frac) wrapping it (same band/cooldown/THETA, plus the
  decay-close step above). Dip sleeve, governor, agents (R2 tables), funding,
  liquidation, min-notional unchanged.
- Gate costs are the engine's own (unchanged): maker 0.0002 (entries/TP/closes),
  taker 0.00055 (stops/market exits), adverse long funding 0.0001 per 8h settlement
  held / shorts 0, no fill minutes 0-4 after a 4h close, stop-first in the same 1m bar.
- REPRODUCE FIRST: REF must reproduce v421_result R2B1D17BFG2 (R 5.41 / max yearly
  DD 16.91 / full-path DD 16.82, yearly rows
  [(2.588,10.86),(3.282,16.91),(6.045,15.81),(10.677,8.27),(4.648,12.90)])
  to the digit before any other row is scored; if not, STOP and report.
- Rows run (ONLY): dev stage REF+V1+V2+C_V1+C_V2; last stage REF + dev4 pick ONLY
  (controls never run in the last stage; Y4 numbers labelled scored-once).
- Stages: dev [2021-09-24,2025-09-24) for the five rows (REF first); then last
  [2021-09-24,2026-09-23) ONCE for REF + the dev4 robust pick ONLY (every Y4 number
  labelled scored-once). Via heavy_slot, one job at a time; resume-safe caches
  tmp/runs_dev.pkl + tmp/runs_last.pkl (+ tmp/std_books.pkl, tmp/controls.json);
  heartbeat every 600 s; nohup + tmp log.

## Scoring (fixed)

- Anchors Y0..Y4 = 2021..2025-09-24, year = [A, A+365d). Dev4 = Y0..Y3;
  Y4 (2025-09-24..2026-09-23) scored ONCE for REF + dev4 pick only.
- Per row x year: 4-phase reset metric R + yearly DD via
  research/diagnostics/r2_decompose5/reset_metric.py::year_reset (same as v421),
  full-path DD via v388.mix continuous path (max of marked/close, v421 convention).
  Full-path DD one number per row over 2021-09-24..2026-09-23. 5y mean = geometric
  mean of the five yearly R (dev stage: 4y only; last stage: 5y with Y4 labelled).
- Book episodes + fee split: engine events walked as oc_memberagree::book_episodes
  (v213-style book_fill/add/reduce/stop/tp/close + rung tp/sl/timeout): per year book
  episode count + win rate (net of fees), rung count + win rate, fee split = maker fees
  vs taker fees summed over book episodes in that year + engine stats totals
  (fees/funding/fills/stops/tps). Book-only P&L NOT separable from equity (engine stores
  t/eq/eq_min only, same as v421) — reported as not separable.
- Exposure diagnostic per row x year: standard-grid gross ratio
  sum|w_row|/sum|w_REF| (= c_y for C rows by construction; V proxy ratios reported;
  engine time-in-position share reported descriptively).
- Selection: robust criterion on dev4, REF + V1 + V2 only (controls reported, NOT
  eligible): eligible iff DDmax <= 20 and no losing dev year; prefer dev4 mean >= 5 %/mo,
  then highest dev4 WORST-year monthly return, ties -> higher mean. (If none eligible,
  pick = "none-eligible" and the last stage runs REF only.) Y4 never picks.

## Leakage statement (how checked; fixed)

- Feature timing: |w0| and |tg| are close-known policy targets only (bars <= decision);
  shifted clocks use latest standard row r <= t_s (ffill; identity at s=0); proxy uses
  closes <= T only. Truncation-tested in tests/test_oc_decayexit.py (post-window data
  cannot move the decay decision; pre-THETA signals never open).
- Label windows: no labels fit anywhere (exits mechanical decay/flip/SL/TP/timeout).
- Fit windows: none in this study (fractions 0.3/0.5 + THETA/band/COOL frozen ex-ante;
  R2 size/TP agents pre-date anchors; C_* use in-year realised means so labelled
  diagnostic/non-eligible and never picked).
- Fill timing: engine trade-mode (limit trade-through, no fill minutes 0-4, stop-first).
  Gate costs inside every leg. No test-year statistic feeds any choice (dev pick uses
  2021-2024 only; Y4 scored once for REF+pick).
- CLOSED rows oc_bookholdcap/oc_bookexit read; this direction closes in this form
  whatever the outcome.

## Deliverables / resources (fixed)

research/tournament/oc_decayexit/: PLAN.md (this file, BEFORE any outcome),
decayexit_rule.py (pure helpers: sgn, decay_policy, proxy simulation, control_mult;
no I/O), compute_controls.py (REF books + bear + proxy + controls.json; LIGHT),
run_engine.py (per-shift heavy runner + scorer; HEAVY via heavy_slot), analyze.py
(scoring + results.json; LIGHT), results.json, REPORT.md.
Tests: tests/test_oc_decayexit.py (>=1 causality/truncation test + >=1 hand-checked
synthetic case), run with `.venv/Scripts/python.exe -m pytest tests/test_oc_decayexit.py -q`.
HEAVY: `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_decayexit
--min-free-gb 2.0 -- <cmd>` (never --leader); one shift per heavy job preferred,
all five book/policy variants sequentially inside the job reusing one minutes load.
Write ONLY research/tournament/oc_decayexit/ + the test file. No commits.

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original
  row stays and the change is a disclosed extra row.)
