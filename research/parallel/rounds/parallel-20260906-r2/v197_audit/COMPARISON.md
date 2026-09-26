# v197 blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v197_audit/replication.json
was saved before opening v197/ (see Part A script header E1-E8/L1-L4).
Base: research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py
(the gate engine implementing the AGENTS.md 2026-09-27 user goal, gate cost model
and current execution assumptions). Leader files were not edited.

Reported: research/parallel/rounds/parallel-20260906-r2/v197/v197_result.json
from research/parallel/rounds/parallel-20260906-r2/v197/v197_sleeve_rung_size.py.
Audit: rows key in
research/parallel/rounds/parallel-20260906-r2/v197_audit/replication.json
(v193 pipeline P2 = (A+B)/2, books vol target 0.25, rung notional
rn = s g mult 0.25/4/1.657 via size_mult = mult with mult in (1, 1.5, 2),
stop-risk budget X = 0.08 * mult in (0.08, 0.12, 0.16); book SL/TP m = 4,
rung SL 5 sigma_4h, TP L(1 + sigma_4h), book limit (d, W) = (0.001, 239),
gap 0.02, cap 2.0). Selected-mult diagnostics (10 worst 1m-marked bars,
stop gaps, liquidation-check margin) are in the replication.json
selected_diagnostics block, from a line-exact instrumented copy of
engine_user.simulate that reproduces the simulate stats exactly.

## Pipeline construction check

v197_sleeve_rung_size.py:30-35 builds v151 = (A+B)/2 on the books154 index
(missing -> 0.0) but prepares with eu.prepare(books154, opens); the audit builds
P2 on the member union index (missing -> 0.0) after checking (A+B+D)/3 ==
books_v154 exactly (max abs diff 0.0, union bars 10950, same 5 majors columns)
and verifies P2 index/columns equal books_v154; shared 1m preparation is
identical for all rows (same idx/cols). As in the v193/v196 audits, prepare uses
books only for idx/cols while vol/s inside simulate is recomputed from the books
argument (P2 == v151), so the driver quirk is immaterial. PASS (same books, same
opens, same cubes). Driver passes sleeve_risk_budget = 0.08 * mult and
size_mult = mult per row (v197_sleeve_rung_size.py:37-39) and leaves target,
cap, gap and m_sleeve_tp at engine defaults; engine_user.py:71 target default
0.25, cap default 2.0, gap default 0.02, m_sleeve_tp default 1.0 match the audit
explicit TARGET = 0.25, CAP = 2.0, GAP = 0.02, TP mult 1.0. The scaled rung
notional takes the size_mult branch (engine_user.py:187
rn = s * g * mult * 0.25/4/1.657), so both the per-rung size and the stop-risk
budget scale with mult — the registered v197 design.

## v197 (rung size x mult with budget 0.08 x mult)

| row | monthly dev4 % | monthly 5y % | last-year monthly % | gate DD % | yearly nets % |
| --- | --- | --- | --- | --- | --- |
| reported 1.0 | 5.046 | 4.603 | 2.847 | 19.33 | 34.58 / 54.37 / 122.74 / 129.58 / 40.05 |
| audit P2_M100 | 5.046 | 4.603 | 2.847 | 19.33 | 34.58 / 54.37 / 122.74 / 129.58 / 40.05 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported 1.5 | 5.562 | 4.996 | 2.761 | 19.32 | 40.67 / 51.32 / 147.63 / 154.98 / 38.66 |
| audit P2_M150 | 5.562 | 4.996 | 2.761 | 19.32 | 40.67 / 51.32 / 147.63 / 154.98 / 38.66 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported 2.0 | 5.935 | 5.192 | 2.273 | 24.27 | 48.70 / 40.55 / 169.43 / 182.72 / 30.96 |
| audit P2_M200 | 5.935 | 5.192 | 2.273 | 24.27 | 48.70 / 40.55 / 169.43 / 182.72 / 30.96 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |

Yearly legs match in full (net/monthly/dd_1m/mean_g per anchor verified equal
as dicts, not just nets).

Stats are bit-exact on every row (fills/unfilled/stops/tps/rungs/rung_stops/
rung_tps/liq/fees/funding, e.g. M100 39882 / 4063 / 76 / 49 / 5001 / 191 /
2714 / 0 / 0.098 / 0.1844; M150 40078 / 4079 / 76 / 48 / 5004 / 191 / 2717 /
0 / 0.0968 / 0.1817; M200 39762 / 4026 / 74 / 47 / 5010 / 192 / 2721 / 0 /
0.0919 / 0.1739). dd_4h/dd_1m match (M100 19.13 / 19.33; M150 19.07 / 19.32;
M200 24.22 / 24.27). Larger mult -> gate DD rises (19.33 -> 19.32 -> 24.27)
while dev4 rises (5.046 -> 5.562 -> 5.935); rung count is nearly flat
(5001 -> 5004 -> 5010) because the budget scales with the size, so the same
candidate rungs pass the proportionally larger budget while each rung carries
more notional.

Mult 1.0 equals the v193 X = 0.08 row exactly (dev4 5.046, 5y 4.603, last
2.847, gate DD 19.33, nets 34.58 / 54.37 / 122.74 / 129.58 / 40.05, stats
39882 / 4063 / 76 / 49 / 5001 / 191 / 2714 / 0 / 0.098 / 0.1844). PASS — the
required anchor holds, so the v197 sweep is a pure size x budget scaling on top
of the audited v193 selection.

## Selection uses no last-year statistic

v197_sleeve_rung_size.py:43-45: ok = rows with gate_dd <= 20 and all
yearly[:4] net_pct >= 0; pool = ok or all rows; sel = max monthly_dev4 over
pool; final_score_selected reports monthly_5y/monthly_last_year/losing_years/
gate_dd/gate_pass once for the winner. monthly_dev4 in
research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py:267-268
is the geometric mean of years[:4] only. The last-year monthly (2.761 for the
winner) is reported, never ranked on. PASS.

Eligibility note: mult 2.0 (dev4 5.935, the plain max-dev4 row) is correctly
excluded by gate_dd 24.27 > 20, so ok = {1.0, 1.5}; the winner 1.5
(dev4 5.562 > 5.046) is the plain max-dev4 eligible row. Audit eligible
[P2_M100, P2_M150], selection P2_M150 maps to reported selected 1.5;
final score selected is identical (5y 4.996 / last 2.761 / DD 19.32).

## Selected-mult (1.5) diagnostics

Instrumented line-exact copy of engine_user.simulate reproduces the P2_M150
simulate stats exactly (fills/unfilled/stops/tps/rungs/rung_stops/rung_tps/liq
40078 / 4079 / 76 / 48 / 5004 / 191 / 2717 / 0; fees/funding equal after
round-to-4).

10 worst 1m-marked bars (path_min = start-equity fraction at the worst minute,
with book/sleeve split at that minute; net/book/sleeve are bar totals):

| date (UTC bar) | path_min | min | book_at_min | sleeve_at_min | bar net |
| --- | --- | --- | --- | --- | --- |
| 2025-09-25 12:00 | -0.08559 | 117 | -0.07581 | -0.00978 | -0.04405 |
| 2023-08-17 16:00 | -0.08372 | 193 | +0.00284 | -0.08656 | -0.08028 |
| 2023-12-10 20:00 | -0.08370 | 132 | -0.03567 | -0.04803 | -0.04907 |
| 2026-08-22 00:00 | -0.07694 | 71 | -0.03711 | -0.03984 | -0.05847 |
| 2024-03-05 12:00 | -0.07651 | 236 | -0.08687 | +0.01036 | -0.06186 |
| 2022-11-11 08:00 | -0.07477 | 150 | -0.01283 | -0.06194 | +0.00684 |
| 2024-08-04 20:00 | -0.07446 | 70 | +0.02792 | -0.10239 | -0.06845 |
| 2026-01-31 12:00 | -0.07268 | 163 | +0.00477 | -0.07745 | -0.06160 |
| 2025-02-02 20:00 | -0.07202 | 115 | -0.01106 | -0.06096 | -0.03590 |
| 2024-01-03 08:00 | -0.07042 | 19 | -0.02555 | -0.04487 | -0.02602 |

The worst intrabar dip (-0.08559) is book-led (~89% book); the tail list mixes
book-led and sleeve-led bars (e.g. 2023-08-17 and 2024-08-04 are sleeve-led),
so the larger rungs do show up in the tail even though the gate DD still binds
at 19.32. Gate DD (max of 4h-close and 1m-marked full-path DD) binds on the 1m
mark on the selected row (dd_4h 19.07 vs dd_1m 19.32).

Stop gaps (selected 1.5): book stops 0 gap fills — every book stop filled
exactly at the stop. Sleeve rung stops 7 gaps; max gap 3.62% of L; total equity
drag 0.00930 of starting equity summed over the full 5-year path, max
single-gap drag 0.00262. The 2% gap allowance in the budget
(rn * (5 sigma_4h + 0.02)) covers the observed gap scale with margin; gap
slippage does not move any headline number.

Liquidation-check margin at the worst minute (2025-09-25 12:00, minute 117):
gross = 2.35114 (book gross + N_MAX 0.166667), threshold MMR * gross = 0.023511
with MMR 0.01, 1 + path_min = 0.91441, margin = +0.89090, liq_flag false.
All 10 worst bars have liq_flag false with margins >= +0.89; the full-path
liquidation count is 0 on all three rows. The cross-margin check never binds.

## Look-ahead check

engine_user.py plus the v197 driver:

- Feature timing: target uses books[t], s[t], g[t] at the decision
  (engine_user.py:89-98); sigma_d/sigma_4h are rolling windows ending at t
  (prepare sig4, line 63; sd = sig4*sqrt(6)); cubes row i is the holding bar
  T = t+4h (prepare via v172.cube_ohlc). Member books are causal inputs by
  construction; P2 = (A+B)/2 is an algebraic mix at bar t only. The mult
  scaling only multiplies the causal s * g rung notional by the pre-registered
  constant mult, and the budget X = 0.08 * mult is the same pre-registered
  constant — neither is fit on any test year. PASS.
- Label windows: no forward return is read; PnL comes only from 1m fills,
  SL/TP exits during T, and the T+4h exit/settlement prices. TP uses
  m_sleeve_tp = 1.0 on all rows (line 209 tp = lv * (1 + k sig4)), SL at
  5 sigma_4h unchanged. PASS.
- Fit windows: no statistic is fit on any test year in this path; vol and
  the governor are running causal filters (vol from books.shift(2) returns,
  governor from eq at i-2 over the trailing 540 bars); (mult, X) in
  ((1, 0.08), (1.5, 0.12), (2, 0.16)) was pre-registered for this direction,
  not tuned here; selection uses first-four-years metrics only. PASS.
- Fill timing: book limit 10 bps better than minute-0, minutes 2..238 strict
  trade-through with expiry and no fallback (engine_user.py:111-118,
  d_limit/win_end per row); SL/TP checked from minute 0 on the held position
  and from the fill minute on the new position, stop-first in one minute, flat
  afterwards with the pending order cancelled (lines 125-176); sleeve trigger
  minutes 16..238 strict with exits strictly after the fill minute in (minute,
  rung, asset) budget order with risk budget X per row and gap 0.02
  (lines 186-228); sleeve SL uses m_sleeve_sl = 5 per row, rung notional
  rn = s * g * mult * 0.25/4/1.657 on every row. PASS.

Fee/funding arithmetic: maker 0.0002 on book entries and TP, taker 0.00055
on stops/market exits, longs pay 0.0001 at 00/08/16 UTC settlements, shorts
zero, no carry (engine_user.py:33-36,169-180, funds in sleeve exit). This is
the AGENTS.md gate cost model. tests/test_engine_user.py covers limit fill
+ TP, stop through a gap (fills at minute open), unfilled-limit expiry, and
long funding at settlement on synthetic bars. PASS.

## Verdict

- Engineering REPRODUCED bit-exact on all three rows (dev4/5y/last-year,
  gate DD, yearly legs, stats).
- Mult 1.0 == v193 X = 0.08 anchor CONFIRMED exact.
- Look-ahead PASS (decision-known features/sigma/scale/governor, no label
  or fit leakage, causal fill/stop/sleeve/budget timing, first-four-years
  selection only; mult/X scaling is pre-registered, not test-fit).
- Selected-mult tail PASS with notes: worst 1m dip -0.08559 (book-led),
  mixed book/sleeve tail, 0 book stop gaps, 7 sleeve stop gaps (0.0093 total
  equity drag), liquidation margin +0.89 at the worst minute, liq count 0.
- Gate: selected 1.5 is the best dev4 under the DD gate so far (dev4 5.562
  >= 5, DD 19.32 <= 20, no losing year) but the gate still fails: 5y 4.996
  < 5 (by 0.004) and the most recent year 2.761 < 5 (nets 40.67 / 51.32 /
  147.63 / 154.98 / 38.66). Mult 2.0 reaches dev4 5.935 / 5y 5.192 but is
  correctly excluded by DD 24.27 > 20. Manifest (status rejected,
  live_approved false, audit passed/replay_complete false awaiting audit)
  must stay non-live_approved.
