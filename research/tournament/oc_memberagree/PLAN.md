# oc_memberagree PLAN (pre-registered BEFORE any outcome is computed, 2026-10-08)

Source: docs/opencode/IDEAS8_20261008.md idea #3 (Member-agreement confidence
sizing, rank 3) + docs/opencode/OPENCODE_W_oc_memberagree.md +
docs/opencode/OPENCODE_W_COMMON_20261007.md + AGENTS.md. CLOSED rows read
first: oc_bookthresh (|w|<walk-forward-q25 -> 0, NOT PROMISING 1/5) and
oc_bookcorr (continuous corr scaling clip(1.5-rho,0.5,1.0), NOT PROMISING) —
this study sizes on SIGN COUNT (calibration-free integers), not magnitude,
no quantile fit. Related provenance: oc_memberdrop (members redundant:
dropping either feed moves dev4 mean +0.01/+0.02pp; blend FULL = d2 below;
4-phase engine replica + scorer reused byte-for-byte).

## Status

Pre-registered, frozen. No outcome has been computed. Compare and choose
ONLY on the four dev years (anchors 2021/2022/2023/2024-09-24, each year =
[A, A+365d)). Robust pick among REF + variants only (controls reported, NOT
eligible): DD <= 20 and no losing dev year; prefer dev4 mean >= 5 %/mo,
then highest dev4 WORST-year monthly return, ties -> higher mean. The most
recent year 2025-09-24..2026-09-23 is scored ONCE, only for REF and the
frozen dev4 pick, labelled REF. If anything changes after an outcome is
seen, the original row stays and the change is added as a disclosed extra
row. Post-hoc log at the bottom (empty now).

## Question (fixed)

Members are redundant (oc_memberdrop) so disagreement is noise and
agreement is the signal; |w| drifts with calibration but sign agreement is
calibration-free. Does scaling the frozen book by per-coin member sign
agreement raise net return / cut DD beyond a pure exposure cut?

## Rows (ONLY these; frozen)

Members (cached, read-only, no retraining): A = member_A_O1_orders, Aq =
member_Aq_O1_orders, B = member_B_tv, Bq = member_Bq_tv, D =
members_v154[D], Dq = members_quarterly_D (same 6 as oc_memberdrop).
Ensemble (per 4h bar T, per coin s, on the standard books154 grid):
o1 = 0.25*(A+B+Aq+Bq), cb = 0.5*(D+Dq), w_ens = 0.8*o1 + 0.2*cb
(union index, missing -> 0.0; == forward_v205.research_books_d2;
builder check: FULL must equal research_books_d2 to <1e-12 max abs diff).

Sign: sgn(x) = 1 if x > 0, -1 if x < 0, 0 if x == 0 (exact float compare;
NaN impossible after fillna, if one occurred it counts as disagree).
Per (T,s) with w_ens[T,s] != 0: a[T,s] = #{m in 6: sgn(m[T,s]) ==
sgn(w_ens[T,s])} (member == 0 counts as disagree). If w_ens[T,s] == 0:
a[T,s] = 6 and scale = 1.0 (weight stays 0 either way; convention only,
keeps scale distribution clean).

- REF: G2 as deployed = w_ens + v421 x0.5 bear filter (below).
- V1 (IDEAS8 #3 V1 exact): scale x1.0 if a >= 5, x0.5 if a <= 3, else x0.75.
  w_V1 = w_ens * scale_V1.
- V2 (IDEAS8 #3 V2 exact): scale x1.0 if a == 6, x0.5 if a <= 4, else x0.75
  (i.e. a == 5 -> x0.75). w_V2 = w_ens * scale_V2.
- C08 (IDEAS8 constant control, fixed 0.8): w_C08 = 0.8 * w_ens.
- C_V1 (exposure-matched control for V1, diagnostic, NOT eligible):
  per anchor year y, c_y = sum|w_V1| / sum|w_ens| over that year's
  standard-grid (T,s) cells (gross exposure ratio, in-year realised;
  uses test-year data so NOT tradable, NOT eligible); w_CV1[T,s] =
  c_y * w_ens[T,s] for T in year y.
- C_V2: same with V2 (d_y = sum|w_V2| / sum|w_ens| per year).

Direction unchanged in all rows (sign of w_ens kept; scale >= 0).
Bear filter (fixed, all six rows, v421 rule on the standard grid BEFORE
shifted ffill): bear[T] = BTC_open[T] < mean(BTC_open[T-1199..T])
(rolling(1200, min_periods=600) on opens_v154 BTCUSDT, NaN -> False);
w[T,s] = 0.5*w[T,s] iff bear[T] and w[T,s] > 0 else unchanged. Same mask
for all rows (opens only). Scale and bear commute (both multiplicative).

## Engine (fixed: 4-phase, exactly v421 G2 R2B1D17BFG2)

Byte-logic replica of v421/v421_gross_cap.py::worker for R2B1D17BFG2
(rule inv, k 1.0, kd 1.7, bear True, G 2.0): per shift s in {0..3}:
pod.minutes() 1m, prep_idx(M, books154.index + s, s, cols), books ffill'd
to the shifted clock, pipe_setup("v321", hist, v221, v216, idx, cols,
True) + corr_size inv/kd=1.7 + risk_mult k=1.0 + sleeve_risk_budget
0.26*1.0*1.7 + sleeve_gross_cap 2.0, eu.simulate(books_bear, opens, prep,
trade=trade, win_start=5, events=ev). Gate costs are the engine's own
(unchanged): maker 0.0002 (entries/TP), taker 0.00055 (stops/market
exits), adverse long funding 0.0001 per 8h settlement held / shorts 0,
no fill minutes 0-4 after a 4h close, stop-first in the same 1m bar.
REPRODUCE FIRST: REF must reproduce v421_result R2B1D17BFG2 (R 5.41 /
max yearly DD 16.91 / full-path DD 16.82, yearly rows
[(2.588,10.86),(3.282,16.91),(6.045,15.81),(10.677,8.27),(4.648,12.90)])
to the digit before any other row is scored; if not, stop and report.
This study is sizing-only (no retraining), so no member-builder check
applies; cached members are read-only.

## Scoring (fixed)

- Anchors Y0..Y4 = 2021..2025-09-24, year = [A, A+365d). Dev4 = Y0..Y3;
  Y4 (2025-09-24..2026-09-23) scored ONCE for REF + dev4 pick only.
- Per row x year: 4-phase reset metric R + yearly DD via
  research/diagnostics/r2_decompose5/reset_metric.py::year_reset (same as
  v421), full-path DD via v388.mix continuous path (max of marked/close,
  v421 convention). Full-path DD one number per row over
  2021-09-24..2026-09-23. 5y mean = geometric mean of the five yearly R.
- Book episodes + fee split: captured events walked exactly as
  oc_memberdrop::book_episodes (v213-style book_fill/add/reduce/stop/tp/
  close + rung tp/sl/timeout): per year book episode count + win rate
  (net of fees), rung count + win rate, fee split = maker fees (fill/add/
  reduce/partial/tp/close legs x0.0002) vs taker fees (stop legs x0.00055)
  summed over book episodes in that year. Book-only P&L NOT separable from
  equity (engine stores t/eq/eq_min only, same as v421) — reported as not
  separable; trade counts/win rates are the decomposition.
- Exposure diagnostic per row x year: mean scale (mean of scale over
  standard-grid (T,s) cells; REF = 1.0 by definition), gross ratio
  sum|w_row|/sum|w_ens| (= c_y/d_y for C rows by construction), agreement
  histogram (share of cells with a = 0..6).
- Selection: robust criterion above on dev4, REF + V1 + V2 only.

## Leakage statement (how checked; fixed)

Cached members are research fits frozen before each anchor (deployed
provenance, same as oc_memberdrop). No test-year or most-recent-year
statistic enters any weight, threshold or choice (scales are frozen
integers 6/5/4/3 on close-known signs; C08 = frozen 0.8; C_Vx use in-year
realised means so they are labelled diagnostic/non-eligible and never
picked). Feature timing: standard-grid (T,s) uses member values at T
(known at T's close); shifted clocks use latest standard row r <= t_s
(ffill; identity at s=0). Fills: engine trade-mode (limit trade-through,
no fill minutes 0-4, stop-first). Fit windows: none in this study (books
read-only; agreement is a frozen count, no fit). Tests cover
causality/truncation + hand-checked synthetic scale cases.

## Deliverables / resources (fixed)

research/tournament/oc_memberagree/: PLAN.md (this file),
run_memberagree.py (books builder + per-shift heavy runner + scorer),
tmp/ (per-shift pickles, scratch only), results.json, REPORT.md.
Tests: tests/test_oc_memberagree.py (>=1 causality/truncation test + >=1
hand-checked synthetic case), run with
.venv/Scripts/python.exe -m pytest tests/test_oc_memberagree.py -q.
HEAVY (4-phase engine, full 1m OHLC): every engine run via
.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_memberagree
--min-free-gb 2.0 -- <cmd> (never --leader); one shift per heavy job,
all six book variants simulated sequentially inside the job reusing one
minutes load. Progress printed per shift/variant (>= every 10 min).
Write ONLY research/tournament/oc_memberagree/ + the test file. No
commits. Single CPU job at a time.

## Post-hoc log

- (none yet; filled only if definitions change after outcomes are seen)
