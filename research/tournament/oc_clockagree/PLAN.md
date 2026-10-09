# oc_clockagree PLAN (FROZEN before any outcome — 2026-10-08)

Source: `docs/opencode/OPENCODE_W_oc_clockagree.md` (= IDEAS8 §5, rank 5) +
`docs/opencode/OPENCODE_W_COMMON_20261007.md` + AGENTS.md +
`docs/opencode/OPENCODE_VF_COMMON.md` + `docs/opencode/IDEAS8_20261008.md` §5.
Write ONLY `research/tournament/oc_clockagree/` + `tests/test_oc_clockagree.py`.
Engine / heavy 1m work via `scripts/heavy_slot.py` (one job at a time, never
`--leader`); long shifts via `nohup ... > tmp/<log> 2>&1 &` + poll the log.
Heartbeat / progress print at least every 10 min. Scratch only under
`research/tournament/oc_clockagree/tmp/`, never the system temp folder.
GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/
rebase/merge. No orders, no authenticated endpoints, no Kaggle uploads.
No inspection outside the workspace (no /proc). CPU only (no GPU).

## Why (IDEAS8 §5, rank 5, prior 10%)

Singles disperse 3.10–6.92 %/mo (`oc_phasedisp`); clocks 1–3 trade stale
phase-0 book (`oc_nativeclock`: NATIVE == REF bit-exact, staleness 100% of
shifted bars, timing value untestable without per-anchor persistence — so
staleness is free signal diversity, not a rebuild case). Size by cross-clock
consensus, no retraining.
CLOSED rows read first: `oc_clockweights` (yearly CAPITAL share by trailing
DD/Sharpe; V2 sharpe dev4 +0.169pp, 5y +0.140, DD −0.2, but y4 4.677 < 5 FAILS
gate — this study sizes per-BAR by sign consensus, not yearly capital share);
`oc_nativeclock` (fresh MODELS per clock, not executable without retraining —
this study re-USES one frozen model at 4 closes for sizing only, no new fits).
`oc_phasedisp` mix (4×1/4 diversifies; no single clock dominates) is the
motivation, not a variant.

## Question (fixed)

Does scaling the frozen G2 book by per-coin cross-clock sign agreement raise
net return / cut DD beyond a pure exposure cut?

## Rows (ONLY these five; frozen)

Book weights = `scripts/forward_v205.py:research_books_d2(eu)` =
0.8 × O1 + 0.2 × (D+Dq)/2 with O1 = (A+Aq+B+Bq)/4 (same 6 cached members as
`oc_memberagree`: A = member_A_O1_orders, Aq = member_Aq_O1_orders,
B = member_B_tv, Bq = member_Bq_tv, D = members_v154[D], Dq =
members_quarterly_D), union index, missing → 0.0, on the `books154` standard
grid. Builder check: rebuilt REF must equal `research_books_d2` to <1e-12 max
abs diff (same check as `oc_memberagree`; sizing-only so no retraining and no
member-builder check beyond this replica assert).

Sign: sgn(x) = 1 if x > 0, −1 if x < 0, 0 if x == 0 (exact float compare).

Cross-clock values (literal ffill operationalisation, causal, frozen): for
each standard-grid bar T (T in books154.index) and each coin c, with
w = w_ens[T,c] (pre-bear ensemble, NaN→0.0):
- v0(T,c) = w[T,c] (phase-0 clock close = T itself).
- v1(T,c) = w[T1,c] where T1 = latest standard bar ≤ (T − 3h) (phase-1 clock's
  latest 4h close ≤ T, i.e. its bar closing at T−3h wall time; ffill source).
- v2(T,c) = w[T2,c], T2 = latest standard bar ≤ (T − 2h).
- v3(T,c) = w[T3,c], T3 = latest standard bar ≤ (T − 1h).
If no standard bar exists ≤ the clock close (warm-up), that v_s = 0.0 (same
fillna(0.0) convention as the engine). All four values use only standard rows
with bar time ≤ their clock close ≤ T (never future).

Agreement: k(T,c) = #{s in 0..3 : sgn(v_s) == sgn(v0)} (includes s=0, so
k ≥ 1). If sgn(v0) == 0: scale = 1.0 by convention (weight stays 0 either way;
keeps the scale distribution clean; same convention as `oc_memberagree`).
Direction unchanged in all rows (sign of w kept; scales ≥ 0; phase-0 sign
decides per IDEAS8).

- REF: G2 as deployed = w_ens + v421 ×0.5 bear filter (below).
- V1 (IDEAS8 §5 V1 exact): scale 1.0 if k==4, 0.75 if k==3, else 0.5 (k≤2).
  w_V1 = w_ens × scale_V1.
- V2 (IDEAS8 §5 V2 exact): scale 1.0 if k>=3 else 0.5. w_V2 = w_ens × scale_V2.
- C_V1 (exposure-matched control for V1, diagnostic, NOT tradable, NOT
  eligible): per anchor year y, c_y = sum|w_V1| / sum|w_ens| over that year's
  standard-grid (T,c) cells (gross exposure ratio, in-year realised; uses
  test-year data so NOT tradable); w_CV1[T,c] = c_y × w_ens[T,c] for T in
  year y. Same C_V2 with V2. Per the assignment + `oc_premexpo` lesson
  (in-year-average-exposure control); isolates consensus TIMING from a mere
  exposure cut.

Pre-registered degeneracy note (frozen expectation, not a change): because
the standard grid steps 4h, for every T past warm-up T1=T2=T3=T−1bar, hence
v1==v2==v3 and k ∈ {1,4} on rows with sgn(v0)≠0 (k==3 never occurs; V1 and V2
coincide on every non-zero row: 1.0 on persistence, 0.5 on flips). The code
asserts this structure and reports the realised k-histogram (share k=1/4,
k==3 count must be 0 past warm-up, zero-row convention share). V1/V2 are
still run and scored separately as pre-registered; identical outcomes are a
valid finding (persistence sizing), judged against their exposure controls.

Bear filter (fixed, all five rows, v421 rule on the standard grid BEFORE
shifted ffill): bear[T] = BTC_open[T] < mean(BTC_open[T−1199..T])
(rolling(1200, min_periods=600) on opens_v154 BTCUSDT, NaN → False);
w[T,c] = 0.5×w[T,c] iff bear[T] and w[T,c] > 0 else unchanged. Same mask for
all rows (opens only). Scale and bear commute (both non-negative
multiplicative; verified in tests); agreement signs are identical pre/post
bear (halving never flips a sign).

## Engine (fixed: 4-phase, exactly v421 G2 R2B1D17BFG2)

Byte-logic replica of `v421/v421_gross_cap.py::worker` for R2B1D17BFG2
(rule inv, k 1.0, kd 1.7, bear True, G 2.0), same as
`oc_memberagree/run_memberagree.py::cmd_shift`: per shift s in {0..3}:
`pod.minutes()` 1m, `prep_idx(M, books154.index + s, s, cols)`, scaled+bear
books ffill'd to the shifted clock, `pipe_setup("v321", hist, v221, v216,
idx, cols, True)` + corr_size inv/kd=1.7 + risk_mult k=1.0 +
sleeve_risk_budget 0.26×1.0×1.7 + sleeve_gross_cap 2.0,
`eu.simulate(books_bear, opens, prep, trade=trade, win_start=5, events=ev)`.
Gate costs are the engine's own (unchanged): maker 0.0002 (entries/TP),
taker 0.00055 (stops/market exits), adverse long funding 0.0001 per 8h
settlement held / shorts 0, no fill minutes 0–4 after a 4h close, stop-first
in the same 1m bar.
REPRODUCE FIRST: REF must reproduce `v421_result` R2B1D17BFG2 (R 5.41 /
max yearly DD 16.91 / full-path DD 16.82, yearly rows
[(2.588,10.86),(3.282,16.91),(6.045,15.81),(10.677,8.27),(4.648,12.90)])
to the digit before any other row is scored; if not, stop and report.
Sizing-only (no retraining), so no per-anchor training and no member-builder
check beyond the REF replica assert above; cached members read-only.

## Scoring (fixed)

- Anchors Y0..Y4 = 2021..2025-09-24, year = [A, A+365d). Dev4 = Y0..Y3;
  Y4 (2025-09-24..2026-09-23) scored ONCE for REF + dev4 pick only; loser
  rows' Y4 = NOT_SCORED (v287/shortmember convention).
- Per row × year: 4-phase reset metric R + yearly DD via
  `research/diagnostics/r2_decompose5/reset_metric.py::year_reset` (same as
  v421), full-path DD via `v388.mix` continuous path (max of marked/close,
  v421 convention from 2021-09-24). 5y mean = geometric mean of the five
  yearly R (dev4 + scored Y4).
- Book episodes + fee split: captured events walked exactly as
  `oc_memberagree::book_episodes` (v213-style book_fill/add/reduce/stop/tp/
  close + rung tp/sl/timeout): per year book episode count + win rate (net of
  fees), rung count + win rate, fee split = maker legs (fill/add/reduce/
  partial/tp/close ×0.0002) vs taker legs (stop ×0.00055) summed over book
  episodes in that year. Book-only P&L NOT separable from equity (engine
  stores t/eq/eq_min only, same as v421) — reported as not separable; trade
  counts/win rates are the decomposition.
- Exposure diagnostic per row × year: mean scale (mean of scale over
  standard-grid (T,c) cells; REF = 1.0), gross ratio sum|w_row|/sum|w_ens|
  (= c_y for C rows by construction), k-histogram (share k=1..4 + zero-row
  share, must show k==3 ≈ 0 past warm-up).
- Selection: robust criterion on dev4, REF + V1 + V2 only (controls reported,
  NOT eligible): eligible = dev DD ≤ 20 every year AND no losing dev year;
  prefer dev4 mean ≥ 5 %/mo; among those highest dev4 WORST-year monthly;
  ties → higher mean. If none eligible, pick = "none-eligible" and the last
  stage runs REF only.

## Leakage statement (how checked; fixed)

Cached members are research fits frozen before each anchor (deployed
provenance, same as `oc_memberagree`/`oc_memberdrop`). No test-year or
most-recent-year statistic enters any weight, threshold or choice (scales are
frozen 4/3/2-count thresholds 1.0/0.75/0.5; C_Vx use in-year realised means so
they are labelled diagnostic/non-eligible and never picked). Feature timing:
v_s use standard rows with bar time ≤ their clock close ≤ T (ffill; identity
at s=0); shifted clocks use latest standard row r ≤ t_s (ffill). Direction =
phase-0 sign only. Fills: engine trade-mode (limit trade-through, no fill
minutes 0–4, stop-first). Fit windows: none in this study (books read-only;
agreement is a frozen count, no fit). Tests cover causality/truncation +
hand-checked synthetic scale cases (incl. the k∈{1,4} degeneracy and
bear/scale commutation).

## Deliverables / resources (fixed)

`research/tournament/oc_clockagree/`: PLAN.md (this file, frozen),
`run_clockagree.py` (books builder + per-shift heavy runner + scorer),
`tmp/` (per-shift pickles + logs, scratch only), `results.json`, `REPORT.md`.
Tests: `tests/test_oc_clockagree.py` (≥1 causality/truncation test + ≥1
hand-checked synthetic case), run with
`.venv/Scripts/python.exe -m pytest tests/test_oc_clockagree.py -q`.
HEAVY (4-phase engine, full 1m OHLC): every engine run via
`.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_clockagree
--min-free-gb 2.0 -- <cmd>` (never `--leader`); one shift per heavy job, all
five book variants simulated sequentially inside the job reusing one minutes
load; nohup + log under `tmp/` for long jobs. Progress printed per
shift/variant (≥ every 10 min). Write ONLY `research/tournament/oc_clockagree/`
+ the test file. No commits. Single CPU job at a time.

## Post-hoc log

- (none yet; filled only if definitions change after outcomes are seen)
