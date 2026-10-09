# oc_spotlongs2 — PLAN (pre-registered 2026-10-08, BEFORE any outcome)

Assignment: `docs/opencode/OPENCODE_W_oc_spotlongs2.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md read; `research/tournament/oc_spotlongs/` V1 read).
Write ONLY `research/tournament/oc_spotlongs2/` + `tests/test_oc_spotlongs2.py`.
Engine runs via heavy_slot (one job at a time; RAM tight). Heartbeat print every
600 s. Scratch only under `research/tournament/oc_spotlongs2/tmp/`.

## Question (follow-up to oc_spotlongs V1)

oc_spotlongs V1 routed every book long to spot-margin at PERP fees
(maker 0.0002 in/out) and measured a +0.230 pp/mo dev4 net funding save
(5y +0.228, Y4 +0.228) with DD flat-to-better. Bybit spot VIP0 fees are
~0.1% maker AND taker; the program convention for spot legs is 0.001
(carry sleeve, AGENTS.md). The funding saving may disappear once the spot
legs pay honest fees.

## Hypothesis (fixed here)

Repricing the spot-routed book-long legs at honest spot fees (0.001 both
sides; sensitivity 0.0006) wipes out most or all of the V1 funding edge on
the dev4 window, because book turnover pays the higher fee on every spot
entry, take-profit, scale and stop. Any clean failure is a valid result.

## Frozen mechanism (exact copy of oc_spotlongs base, ONE change)

- 4 phases (shifts 0..3, 4h grid opens at s, s+4, ... UTC); pipe v321 via
  phase_offset_full.pipe_setup; corr-aware dip sizes mult 1/(1+n)*1.7*tilt*base
  (n = coins with C<=O*(1-2.5*sig); tilt=1 here); risk_mult 1.0;
  sleeve_risk_budget 0.26*1*1.7; sleeve_gross_cap G=2.0; bear books
  (BTC 4h open < 1200-bar mean halves LONG targets; standard rows, before
  shifted-clock ffill).
- Gate costs inside the engine for PERP legs: maker 0.0002, taker 0.00055
  (stops/market taker), longs pay 0.0001/8h, shorts 0. Limit orders fill only
  on 1m trade-through, strictly through the price; no fill in the first 5
  minutes after a 4h close (win_start=5). Stop-first in a shared 1m bar.
- Every book position keeps limit entry + market SL + limit TP, stop-first
  (user rule; NOT a stop-entry order, so entries stay limit).
- Fill basis from minute data (same 1m cube as base; spot-perp basis assumed 0,
  labelled assumption, no close-sample claim).
- Funding: book longs that are spot-routed pay 0 (saved tracked); all other
  book longs pay FUND_LONG when settle; dip sleeve untouched (perp, pays gate
  funding on timeouts as base).
- Borrow (unchanged from V1, frozen ex-ante): per holding bar, after the
  engine steps quantities, borrowed notional B_bar = max(0,
  long_notional_spot_end - equity_start), long_notional_spot_end = sum over
  spot-routed coins of max(q_end_a, 0) * o2[i][a]; hourly rate APR/8760
  applied per 4h bar as B_bar * APR * (4/8760), APR = 10% for ALL spot rows
  (no stress row here; V1 showed APR15-APR10 = -0.002 pp/mo, immaterial).
- THE ONE CHANGE vs oc_spotlongs: the spot-routed book-LONG legs pay honest
  SPOT fees instead of perp fees. Routing is unconditional (V1 = all book
  longs spot), so the rule is simply: a book leg on the LONG side
  (entry of a new long, TP/SL/partial/scale of a held long) pays the spot
  rate; a book leg on the SHORT side stays perp (gate rate). Dip sleeve legs
  are untouched (perp rates, implicit in rung returns). Concretely, in the
  patched `_trade_bar` (trade mode, the only mode this pipe uses):
  entry fill of ps>0, stop exits of cur_q>0, TP exits of cur_q>0, scale
  adds/reduces/partials of side>0 use spot_maker (limit legs) /
  spot_taker (market stop legs); everything else uses MAKER/TAKER.
  The non-trade branch (`trade=None`) is never executed by this pipe and is
  left byte-identical (stated limitation).

## Variants (ONLY these; no selection beyond the frozen robust rule, no tuning)

- REF = G2 unchanged (R2B1D17BFG2: rule inv, k 1.0, kd 1.7, bear True, G 2.0).
  In-engine this is the V0 gate (spot_route=None, gate fees) which must
  reproduce v421 dev years 0..3 to the digit; the full-window REF numbers in
  the report are the STORED v421 row (labelled, never recomputed).
- SPOT_F10 = V1 routing (ALL book longs spot, borrow APR 10%) with honest
  spot fees spot_maker = spot_taker = 0.001. The spot SL as a market sell
  pays 0.001. This is the candidate.
- SPOT_F06 = same routing and borrow as SPOT_F10 with spot_maker =
  spot_taker = 0.0006 (higher-VIP-tier sensitivity, labelled; never picked).
- S5_BYBIT row: for the dev4 robust pick + REF only, rerun on Bybit 1m
  (S5 harness of oc_c2bybit: bybit_minutes() from
  data/raw/bybit_linear_1m_20261004, live0 = 2021-11-15 + shift, standard index
  filtered to >= 2021-11-15 before shift, win_start=5). Year 2021 is a SHORT
  window (labelled). If Bybit files missing/unreadable, S5 = not reproducible.
- Cost stress S1 NOT rerun (fee question is orthogonal; gate + spot rows only).

## Book turnover + fee/funding split (frozen definitions)

Per holding bar (fractions of bar-start equity, same convention as the
engine's funding/borrow legs), recorded in bars_lite for every simulated bar:
- turnover_bar: sum of abs(notional) over every book fill/exit/add/reduce/
  partial in the bar (entry fills, SL/TP exits, scale adds/reduces, partials).
- spot_fee_bar / perp_fee_bar: abs(notional)*rate split by the leg rule above.
- funding_saved_bar: gate funding zeroed on spot-routed longs (as V1).
- funding_paid_bar: gate funding actually charged on book longs after zeroing.
- borrow_bar: USDT interest as defined above.
Aggregation per anchor year y and shift s: sum of per-bar terms over holding
bars with open T in [A_y+4h, A_y+365d+4h); reported as the MEAN across the 4
shifts (x equity/year), plus fee/funding totals in the same units. Dip-sleeve
fees stay implicit in rung returns (engine convention, labelled); dip funding
on timeouts is included in the engine stats but not split out here.

## Windows / metrics (fixed)

- Anchors 2021..2025-09-24; dev4 = years 0..3 ([A,A+365d)); Y4 = 2025-09-24..
  2026-09-23 scored ONCE, only for the dev4 robust pick + REF, labelled
  DIAGNOSTIC (oc_spotlongs already scored this year once for V1; this re-score
  with honest fees is never a selection input); 5y = years 0..4 (context).
- Per-year 4-phase reset %/mo + DD via reset_metric.year_reset; dev4/5y geo
  mean, W (worst-year R), max yearly DD, losing count; full-path DD via
  v388.mix equal-1/4 mix from 2021-09-24 (max of reset DDs and full-path for
  the gate); pooled book/rung/all win rates + fills/year (same collection as
  oc_spotlongs run_engine).
- Reproduction gate (STOP if failed): REF/V0 dev years 0..3 R/DD ==
  v421_result.json G2 R2B1D17BFG2 [(2.588/10.86),(3.282/16.91),(6.045/15.81),
  (10.677/8.27)] to the digit, 5y 5.410, max yearly DD 16.91,
  full-path DD 16.82.
- Robust pick (dev4 ONLY, among REF / SPOT_F10 only; SPOT_F06 is sensitivity
  and can never be picked): among the eligible (full-path DD <= 20 and no
  losing dev year), prefer dev4 mean >= 5 %/mo, then highest dev4 WORST-year
  monthly return, ties -> higher mean. If neither is eligible, pick by the
  same rule over both anyway and label the breach.
- Gate read-out for the pick (labelled): (a) 5y >= 5, (b) Y4 >= 5, (c) no
  losing year, DD <= 20. Expectation (not a selection input): leg (b) already
  failed for fee-free V1 (4.876 < 5); honest fees can only lower it.

## Feasibility check (fixed method)

Bybit spot TP/SL order types for an attached stop + take-profit on a spot
long: read the PUBLIC Bybit API docs only (no keys, no authenticated calls,
no orders). Cite the exact doc pages and state whether a spot long can carry
an exchange-native attached stop-loss (market) and take-profit (limit) with
stop-first semantics, or whether the SL/TP must be emulated (e.g. conditional
orders / TP/SL mode), and what that implies for the simulation's stop-first
assumption. Web search + WebFetch of the public docs; URLs cited in REPORT.

## Leakage / contamination (pre-registered checks, stated in REPORT)

- Feature timing: books known at close of T, held over [T,T+1); no funding
  signal is used here (unconditional V1 routing — no F7, no medians, no fit
  of any kind in this study); borrow uses only this bar's end quantities and
  bar-start equity. Truncation test: recompute from a truncated panel —
  identical on the kept prefix (inherited from oc_spotlongs spot_rule).
- Label windows: no label fit here; engine uses the realised 1m path.
- Fit windows: NOTHING is fit in this study (no medians, no thresholds;
  borrow APR and spot fees fixed ex-ante). No test-year statistic feeds any
  choice.
- Fill timing: win_start=5 asserted (no fill minutes 0-4); limits fill only on
  1m trade-through strictly through the price; stop-first asserted; spot fills
  use the same minute cube (basis 0 labelled).
- Contamination: dev years were available when IDEAS10/oc_spotlongs were
  written (post-hoc direction); Y4 was scored once for V1 in oc_spotlongs and
  is re-scored here ONCE for the frozen pick only as a labelled diagnostic;
  S5 is an unseen price path on the same years (diagnostic, never selection).

## Compute plan (heavy_slot, resume-safe)

- `spot_rule2.py`: verbatim copy of oc_spotlongs/spot_rule.py pure helpers
  (F7/med/route/borrow, kept for the truncation test and borrow math) PLUS
  the frozen spot-fee constants SPOT_F10/SPOT_F06 (no logic change).
- `spot_patch2.py`: verbatim engine_user.simulate + SPOT-FEE PATCH (asserted
  anchors; defaults spot_route=None/spot_maker=MAKER/spot_taker=TAKER reproduce
  the audited engine bit-exact): P1 signature + spot_maker/spot_taker; P2 book
  funding zeroing (as V1); P3 borrow (as V1); P4 bars record turnover /
  spot-perp fee split / funding paid+saved / borrow; P5 book fee-rate switch
  (long legs -> spot rate, short legs -> gate rate) with turnover/fee-split
  accumulators.
- `compute_spotlongs2_engine.py`: sequential shifts 0..3 per variant (one heavy
  process at a time), heartbeat print every 600 s, caches
  `tmp/runs_<stage>_<fric>.pkl` (resume-safe: skip cached shifts). Invoked as
  `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_spotlongs2_eng
  --min-free-gb 2.0 -- .venv/Scripts/python.exe
  research/tournament/oc_spotlongs2/compute_spotlongs2_engine.py
  [--stage dev|last] [--fric base|S5] [--shifts ...] [--rows ...]`.
  Rows: dev base REF,SPOT_F10,SPOT_F06; last base pick-only; dev S5 pick-only.
  Long runs: nohup + log under tmp/ (never system temp; never /proc or folders
  outside the workspace).
- `analyze_spotlongs2.py`: CPU-only scoring (reset metric + v388.mix + wins +
  turnover/fee-split aggregation) -> `tmp/spotlongs2_table.json`; REPORT.md +
  results.json written from that table only.
- Deliverables: PLAN.md (this file), spot_rule2.py, spot_patch2.py,
  compute_spotlongs2_engine.py, analyze_spotlongs2.py, results.json, REPORT.md,
  tests/test_oc_spotlongs2.py.

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the
  original row stays and the change is a disclosed extra row.)
