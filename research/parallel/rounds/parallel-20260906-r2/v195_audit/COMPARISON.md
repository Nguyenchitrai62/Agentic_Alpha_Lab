# v195 blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v195_audit/replication.json
was saved before opening v195/ (see Part A script header E1-E8/L1-L4).
Base: research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py
(the gate engine implementing the AGENTS.md 2026-09-27 user goal, gate cost model
and current execution assumptions). Leader files were not edited.

Reported: research/parallel/rounds/parallel-20260906-r2/v195/v195_result.json
from research/parallel/rounds/parallel-20260906-r2/v195/v195_risk_allocation.py.
Audit: rows key in
research/parallel/rounds/parallel-20260906-r2/v195_audit/replication.json
(v193 pipeline P2 = (A+B)/2 with (books vol target, sleeve stop-risk budget X)
= (0.25, 0.08), (0.20, 0.12), (0.15, 0.16); the vol target changes
s = min(target/vol, 2) everywhere, books and rung notional; book SL/TP m = 4,
rung SL 5 sigma_4h, TP L(1 + sigma_4h), book limit (d, W) = (0.001, 239),
gap 0.02, cap 2.0).

## Pipeline construction check

v195_risk_allocation.py:31-36 builds v151 = (A+B)/2 on the books154 index
(missing -> 0.0) but prepares with eu.prepare(books154, opens); the audit builds
P2 on the member union index (missing -> 0.0) after checking (A+B+D)/3 ==
books_v154 exactly (max abs diff 0.0, union bars 10950) and verifies P2
index/columns equal books_v154; shared 1m preparation is identical for all rows
(same idx/cols). As in the v193 audit, prepare uses books only for idx/cols
while vol/s inside simulate is recomputed from the books argument (P2 == v151),
so the driver quirk is immaterial. PASS (same books, same opens, same cubes).
Driver passes target = tg and sleeve_risk_budget = x per row and leaves gap,
cap and m_sleeve_tp at engine defaults; engine_user.py:71 gap default 0.02,
cap default 2.0, m_sleeve_tp default 1.0 match the audit explicit gap = 0.02,
cap = 2.0, TP mult 1.0. The paired target changes s = min(target/vol, 2) on
both legs (engine_user.py:80 s; line 98 books tgt = 0.8 s B g; line 187 rung
rn = s g 0.25/4/1.657), so lowering the target shrinks books and sleeve
together and the budget X is what moves the sleeve — the manifest design
caveat.

## v195 (paired target/X sweep)

| row | monthly dev4 % | monthly 5y % | last-year monthly % | gate DD % | yearly nets % |
| --- | --- | --- | --- | --- | --- |
| reported t0.25_x0.08 | 5.046 | 4.603 | 2.847 | 19.33 | 34.58 / 54.37 / 122.74 / 129.58 / 40.05 |
| audit P2_T250_X080 | 5.046 | 4.603 | 2.847 | 19.33 | 34.58 / 54.37 / 122.74 / 129.58 / 40.05 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported t0.2_x0.12 | 4.514 | 4.136 | 2.634 | 16.85 | 38.41 / 50.91 / 95.05 / 104.36 / 36.62 |
| audit P2_T200_X120 | 4.514 | 4.136 | 2.634 | 16.85 | 38.41 / 50.91 / 95.05 / 104.36 / 36.62 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported t0.15_x0.16 | 3.622 | 3.320 | 2.118 | 15.00 | 40.05 / 36.67 / 67.69 / 71.89 / 28.60 |
| audit P2_T150_X160 | 3.622 | 3.320 | 2.118 | 15.00 | 40.05 / 36.67 / 67.69 / 71.89 / 28.60 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |

(0.25, 0.08) equals the v193 X = 0.08 row bit-exact as required (dev4 5.046,
5y 4.603, last 2.847, DD 19.33, nets 34.58 / 54.37 / 122.74 / 129.58 /
40.05, stats 39882 / 4063 / 76 / 49 / 5001 / 191 / 2714 / liq 0 /
fees 0.098 / funding 0.1844).

Stats are bit-exact on every row (fills/unfilled/stops/tps/rungs/rung_stops/
rung_tps/liq/fees/funding, e.g. T250_X080 39882 / 4063 / 76 / 49 / 5001 / 191 /
2714 / 0 / 0.098 / 0.1844; T200_X120 39117 / 3998 / 76 / 49 / 5157 / 200 /
2810 / 0 / 0.0853 / 0.1588; T150_X160 37601 / 3840 / 76 / 52 / 5163 / 200 /
2813 / 0 / 0.067 / 0.1234). dd_4h/dd_1m match (T250 19.13 / 19.33; T200 16.65 /
16.85; T150 14.88 / 15.00). Yearly legs match in full
(net/monthly/dd_1m/mean_g per anchor). Lower target + higher budget -> gate DD
falls (19.33 -> 16.85 -> 15.00) while dev4 falls faster (5.046 -> 4.514 ->
3.622); rung count rises then plateaus (5001 -> 5157 -> 5163) while book fills
fall with the smaller scale (39882 -> 39117 -> 37601) and fees/funding fall
(0.098/0.1844 -> 0.0853/0.1588 -> 0.067/0.1234); the book stop count is flat
(76) with tps 49/49/52.

## Selection uses no last-year statistic

v195_risk_allocation.py:45-47: ok = rows with gate_dd <= 20 and all
yearly[:4] net_pct >= 0; pool = ok or all rows; sel = max monthly_dev4 over
pool; final_score_selected reports monthly_5y/monthly_last_year/losing_years/
gate_dd/gate_pass once for the winner. monthly_dev4 in
research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py:267-268
is the geometric mean of years[:4] only. The last-year monthly (2.847 for
the winner) is reported, never ranked on. PASS.

Eligibility note: all three rows have gate_dd <= 20 (19.33 / 16.85 / 15.00)
with zero losing years in the first four (in fact zero losing years overall),
so ok is all three rows; the winner (0.25, 0.08) is the plain max-dev4 row
(5.046 > 4.514 > 3.622). Audit eligible [P2_T150_X160, P2_T200_X120,
P2_T250_X080], selection P2_T250_X080 maps to reported selected t0.25_x0.08;
final score selected is identical (5y 4.603 / last 2.847 / DD 19.33).

## Look-ahead check

engine_user.py plus the v195 driver:

- Feature timing: target uses books[t], s[t], g[t] at the decision
  (engine_user.py:89-98); sigma_d/sigma_4h are rolling windows ending at t
  (prepare sig4, line 63 sd = sig4*sqrt(6)); cubes row i is the holding bar
  T = t+4h (prepare via v172.cube_ohlc). Member books are causal inputs by
  construction; P2 = (A+B)/2 is an algebraic mix at bar t only. The paired
  target only rescales the causal s = min(target/vol, 2) with vol from
  books.shift(2) returns. PASS.
- Label windows: no forward return is read; PnL comes only from 1m fills,
  SL/TP exits during T, and the T+4h exit/settlement prices. TP uses
  m_sleeve_tp = 1.0 on all rows (line 209 tp = lv * (1 + k sig4)), SL at
  5 sigma_4h unchanged. PASS.
- Fit windows: no statistic is fit on any test year in this path; vol and
  the governor are running causal filters (vol from books.shift(2) returns,
  governor from eq at i-2 over the trailing 540 bars); (target, X) in
  ((0.25, 0.08), (0.20, 0.12), (0.15, 0.16)) was pre-registered for this
  direction, not tuned here; selection uses first-four-years metrics only. PASS.
- Fill timing: book limit 10 bps better than minute-0, minutes 2..238 strict
  trade-through with expiry (engine_user.py:111-118, d_limit/win_end per
  row); SL/TP checked from minute 0 on the held position and from the fill
  minute on the new position, stop-first in one minute, flat afterwards
  with the pending order cancelled (lines 125-176); sleeve trigger minutes
  16..238 strict with exits strictly after the fill minute in (minute,
  rung, asset) budget order with risk budget X per row and gap 0.02
  (lines 186-228); sleeve SL uses m_sleeve_sl = 5 per row, rung notional
  rn = s g 0.25/4/1.657 uses the same per-row s as the books leg. PASS.

Fee/funding arithmetic: maker 0.0002 on book entries and TP, taker 0.00055
on stops/market exits, longs pay 0.0001 at 00/08/16 UTC settlements, shorts
zero, no carry (engine_user.py:33-36,169-180, funds in sleeve exit). This is
the AGENTS.md gate cost model. tests/test_engine_user.py covers limit fill
+ TP, stop through a gap (fills at minute open), unfilled-limit expiry, and
long funding at settlement on synthetic bars. PASS.

## Verdict

- Engineering REPRODUCED bit-exact on all three rows (dev4/5y/last-year,
  gate DD, yearly nets, stats).
- (0.25, 0.08) equals the v193 X = 0.08 row bit-exact as required.
- Look-ahead PASS (decision-known features/sigma/scale/governor, no label
  or fit leakage, causal fill/stop/sleeve timing, first-four-years
  selection only).
- Gate: every row fails monthly >= 5% on 5y/last-year (best dev4 5.046 on
  (0.25, 0.08), best 5y 4.603, best last-year 2.847) with no losing year;
  all three pass DD <= 20% (19.33 / 16.85 / 15.00). Selected (0.25, 0.08)
  final 5y 4.603 / last 2.847 / DD 19.33 -> gate fails. Manifest (status
  rejected, live_approved false, audit passed/replay_complete false awaiting
  audit) must stay non-live_approved.
