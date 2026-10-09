# oc_memberdrop PLAN (pre-registered BEFORE any outcome is computed, 2026-10-07)

## Status

DIAGNOSTIC for operations + runbook. NO selection is made here, the deployed
config does not change. All five anchor years are scored descriptively only
(dev4 Y0..Y3 + the most recent year Y4, labelled). The robust selection
criterion (AGENTS.md) is NOT applied. Any guidance needs prospective
confirmation before real money.

## Question (fixed here)

The deployed book is a blend (scripts/forward_v205.py `research_books_d2`,
confirmed in v421's worker `research_books_d2 / pipe_setup`):
`o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`, `d2 = 0.8*o1 + 0.2*(D+Dq)/2`, union index,
missing -> 0.0, where A = `member_A_O1_orders` (annual order-level whale
flow), Aq = `member_Aq_O1_orders` (quarterly order-level whale flow),
B = `member_B_tv`, Bq = `member_Bq_tv` (TradingView members),
D = `members_v154[D]` (annual Coinbase-premium member),
Dq = `members_quarterly_D` (quarterly Coinbase-premium member).
Implicit FULL weights: A 0.2, B 0.2, Aq 0.2, Bq 0.2, D 0.1, Dq 0.1 (sum 1.0).
Live, A/Aq depend on the Binance aggTrades order-level feed, D/Dq on the
Coinbase spot feed. Which member carries G2's timing, and how much does the
bot lose if a feed dies for days?

## Rows (ONLY these four; fixed here)

- FULL: G2 as deployed (`d2` above + v421 x0.5 bear filter below).
- NO_FLOW: book WITHOUT the whale-flow members A and Aq. The blend code has
  NO absent-member path (it does `fillna(0.0)`), so per the assignment the
  remaining members' blend is rescaled to sum to 1 (stated here): remaining
  original weights B 0.2 + Bq 0.2 + D 0.1 + Dq 0.1 = 0.6; rescaled:
  B 1/3, Bq 1/3, D 1/6, Dq 1/6. I.e. `(0.4*(B+Bq)/2 + 0.2*(D+Dq)/2)/0.6`.
- NO_CB: book WITHOUT the Coinbase-premium members D and Dq, same rule:
  remaining A/Aq/B/Bq each 0.2 (sum 0.8); rescaled 0.25 each = exactly `o1`.
- STALE_FLOW (outage stress): FULL weights, but the flow members A and Aq are
  frozen at their last standard-grid value for 72 h starting at each of 10
  fixed, pre-registered UTC timestamps per year, then resume; B/Bq/D/Dq and
  all weights unchanged; the bear filter below still applies on the blended
  book.

STALE timestamps (fixed formula, persisted verbatim in results.json):
`S(y,k) = Ay + 10d + k*36.5d`, k = 0..9,
Ay in {2021,2022,2023,2024,2025}-09-24 00:00 UTC.
Last start = Ay+338.5d, window ends Ay+341.5d < Ay+365d (inside the year).
Freeze rule (causal): let `a-(S)` = the last standard-grid book row with
timestamp strictly `< S`. For every standard-grid row `t` with
`S <= t < S+72h`, use `A(t) = A(a-(S))`, `Aq(t) = Aq(a-(S))`
(if no row `< S` exists, use 0.0). If S falls exactly on a grid row, that
row is already frozen (strict `<`). After `S+72h`, actual values resume.
Overlapping windows (none by construction: starts 36.5d apart) would keep
the earliest frozen value; disclosed if ever triggered.

## Bear filter (fixed, all rows)

v421 x0.5 bear rule on the blended standard-grid book BEFORE the shifted
ffill: `bear[T] = BTC_open[T] < mean(BTC_open[T-1199..T])`
(`rolling(1200, min_periods=600)` on `opens_v154` BTCUSDT, NaN -> False);
`w[T,s] = 0.5*w[T,s]` iff `bear[T] and w[T,s] > 0`, else unchanged. Same mask
for all four rows (computed from opens only, never from books).

## Engine (fixed: 4-phase, exactly v421 G2)

Byte-logic replica of `v421/v421_gross_cap.py::worker` for
`R2B1D17BFG2` (rule inv, k 1.0, kd 1.7, bear True, G 2.0):
per shift s in {0..3}: `pod.minutes()` 1m, `prep_idx(M, books154.index + s,
s, cols)`, books ffill'd to the shifted clock (STALE already applied on the
standard grid, so the ffill carries frozen values causally), bear mask as
above, `hist.R2_TABLE = v376/tables_hidden/r2_table_s{s}.parquet` (agents ON,
R2 tables), `pipe_setup("v321", hist, v221, v216, idx, cols, True)` +
`corr_size` inv/kd=1.7 + `risk_mult` k=1.0 +
`sleeve_risk_budget 0.26*1.0*1.7` + `sleeve_gross_cap 2.0`,
`eu.simulate(books_bear, opens, prep, trade=trade, win_start=5, events=ev)`.
Gate costs are the engine's own (unchanged from v421): maker 0.0002
(entries/TP), taker 0.00055 (stops/market exits), adverse long funding
0.0001 per 8h settlement held / shorts 0, no fill minutes 0-4 after a 4h
close, stop-first in the same 1m bar.
REPRODUCE FIRST: FULL must reproduce v421_result `R2B1D17BFG2`
(R 5.41 / max yearly DD 16.91 / full-path DD 16.82, yearly rows
[(2.588,10.86),(3.282,16.91),(6.045,15.81),(10.677,8.27),(4.648,12.90)])
to the digit before any other row is scored; if not, stop and report.

## Scoring (fixed; descriptive, no selection)

- Anchors Y0..Y4 = 2021..2025-09-24, year = [A, A+365d). Dev4 = Y0..Y3; Y4
  (2025-09-24..2026-09-23) is scored ONCE per row and labelled
  "most-recent, descriptive".
- Per row x year: 4-phase reset metric R + yearly DD via
  `research/diagnostics/r2_decompose5/reset_metric.py::year_reset`
  (same as v421), full-path DD via `v388.mix` continuous path
  (max of marked/close, v421 convention). Full-path DD is one number per
  row over 2021-09-24..2026-09-23.
- Book-only share: the engine stores t/eq/eq_min only (as v421), so book
  P&L is NOT separable from equity — reported as not separable (no extra
  sleeve-off runs; out of scope). Context instead: per row, trade counts
  and win rates from captured events (book episodes via the
  v213-style book_fill/add/reduce/stop/tp/close walk + rung tp/sl/timeout).
- Verdict: which feed is critical (NO_FLOW vs NO_CB drop on dev4 mean R and
  worst-year R), and the expected cost of a 3-day outage (mean per-episode
  R drag of STALE_FLOW vs FULL annualised from the 10 episodes/year), in 3
  lines of Vietnamese for the runbook.

## Leakage statement (how checked; fixed)

Member parquets are research fits frozen before each anchor year (same
provenance as the deployed book). No test-year or most-recent-year
statistic enters any weight, threshold or choice (weights fixed above;
STALE starts are calendar formula, not data-dependent). Feature timing:
standard-grid book row t uses member values at t (known at t's close);
shifted clocks use latest standard row r <= t_s (ffill; identity at s=0);
STALE frozen values use rows strictly `< S`. Fills: engine trade-mode
(limit trade-through, no fill minutes 0-4, stop-first). Fit windows: none
in this study (books read-only). Tests cover causality/truncation +
hand-checked synthetic blend/freeze cases.

## Deliverables / resources (fixed)

`research/tournament/oc_memberdrop/`: PLAN.md (this file),
`run_memberdrop.py` (books builder + per-shift heavy runner + scorer),
`tmp/` (per-shift pickles, scratch only), `results.json`, `REPORT.md`.
Tests: `tests/test_oc_memberdrop.py` (>=1 causality/truncation test + >=1
hand-checked synthetic case), run with
`.venv/Scripts/python.exe -m pytest tests/test_oc_memberdrop.py -q`.
HEAVY (4-phase engine, full 1m OHLC): every engine run via
`.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_memberdrop
--min-free-gb 2.0 -- <cmd>` (never `--leader`); one shift per heavy job,
four book variants simulated sequentially inside the job reusing one
minutes load. Progress printed per shift/variant (>= every 10 min).
Write ONLY `research/tournament/oc_memberdrop/` + the test file. No
commits. No selection, no deployment change.

## Post-hoc log

- (none yet; filled only if definitions change after outcomes are seen)
