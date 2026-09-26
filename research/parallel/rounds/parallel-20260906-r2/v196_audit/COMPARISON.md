# v196 blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v196_audit/replication.json
was saved before opening v196/ (see Part A script header E1-E8/L1-L4).
Base: research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py
(the gate engine implementing the AGENTS.md 2026-09-27 user goal, gate cost model
and current execution assumptions). Leader files were not edited.

Reported: research/parallel/rounds/parallel-20260906-r2/v196/v196_result.json
from research/parallel/rounds/parallel-20260906-r2/v196/v196_decoupled_allocation.py.
Audit: rows key in
research/parallel/rounds/parallel-20260906-r2/v196_audit/replication.json
(v193 pipeline P2 = (A+B)/2 with (books vol target, sleeve stop-risk budget X)
= (0.25, 0.08), (0.20, 0.12), (0.15, 0.16); the books vol target changes
s = min(target/vol, 2) on the books leg only, while the rung notional is
decoupled: rn = 1.497 * g * 0.25/4/1.657 via rung_scale_fixed = 1.497;
book SL/TP m = 4, rung SL 5 sigma_4h, TP L(1 + sigma_4h), book limit
(d, W) = (0.001, 239), gap 0.02, cap 2.0).

## Pipeline construction check

v196_decoupled_allocation.py:31-37 builds v151 = (A+B)/2 on the books154 index
(missing -> 0.0) but prepares with eu.prepare(books154, opens); the audit builds
P2 on the member union index (missing -> 0.0) after checking (A+B+D)/3 ==
books_v154 exactly (max abs diff 0.0, union bars 10950) and verifies P2
index/columns equal books_v154; shared 1m preparation is identical for all rows
(same idx/cols). As in the v193/v195 audits, prepare uses books only for idx/cols
while vol/s inside simulate is recomputed from the books argument (P2 == v151),
so the driver quirk is immaterial. PASS (same books, same opens, same cubes).
Driver passes target = tg, sleeve_risk_budget = x and rung_scale_fixed = S_FIX
= 1.497 per row (v196_decoupled_allocation.py:27-28,41-42) and leaves gap, cap
and m_sleeve_tp at engine defaults; engine_user.py:71 gap default 0.02, cap
default 2.0, m_sleeve_tp default 1.0 match the audit explicit gap = 0.02,
cap = 2.0, TP mult 1.0. The decoupled rung notional takes the
rung_scale_fixed branch (engine_user.py:187 rn = 1.497 * g * 0.25/4/1.657),
so lowering the books target shrinks the books leg only; the sleeve size is
fixed and only the budget X moves it — the registered repair of the v195
design flaw.

## v196 (decoupled target/X sweep, rung scale 1.497)

| row | monthly dev4 % | monthly 5y % | last-year monthly % | gate DD % | yearly nets % |
| --- | --- | --- | --- | --- | --- |
| reported t0.25_x0.08 | 4.972 | 4.558 | 2.919 | 19.44 | 32.39 / 56.53 / 121.24 / 123.97 / 41.24 |
| audit P2_T250_X080 | 4.972 | 4.558 | 2.919 | 19.44 | 32.39 / 56.53 / 121.24 / 123.97 / 41.24 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported t0.2_x0.12 | 4.590 | 4.216 | 2.733 | 17.28 | 37.09 / 51.72 / 103.90 / 103.24 / 38.21 |
| audit P2_T200_X120 | 4.590 | 4.216 | 2.733 | 17.28 | 37.09 / 51.72 / 103.90 / 103.24 / 38.21 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported t0.15_x0.16 | 3.945 | 3.615 | 2.302 | 15.79 | 41.32 / 38.60 / 82.66 / 79.07 / 31.41 |
| audit P2_T150_X160 | 3.945 | 3.615 | 2.302 | 15.79 | 41.32 / 38.60 / 82.66 / 79.07 / 31.41 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |

Yearly legs match in full (net/monthly/dd_1m/mean_g per anchor verified equal
as dicts, not just nets).

Stats are bit-exact on every row (fills/unfilled/stops/tps/rungs/rung_stops/
rung_tps/liq/fees/funding, e.g. T250_X080 39861 / 4066 / 75 / 49 / 5086 / 197 /
2765 / 0 / 0.0978 / 0.1843; T200_X120 39162 / 4002 / 76 / 49 / 5162 / 200 /
2812 / 0 / 0.0849 / 0.1583; T150_X160 37898 / 3859 / 76 / 51 / 5163 / 200 /
2813 / 0 / 0.0666 / 0.123). dd_4h/dd_1m match (T250 19.23 / 19.44; T200 17.02 /
17.28; T150 15.71 / 15.79). Lower books target + higher budget -> gate DD
falls (19.44 -> 17.28 -> 15.79) while dev4 falls (4.972 -> 4.590 -> 3.945);
rung count rises then plateaus (5086 -> 5162 -> 5163) while book fills fall
with the smaller books scale (39861 -> 39162 -> 37898) and fees/funding fall
(0.0978/0.1843 -> 0.0849/0.1583 -> 0.0666/0.123).

Note vs the coupled v195 audit: decoupling (fixed 1.497 rung scale) moves the
top row dev4 5.046 -> 4.972 with rungs 5001 -> 5086; the bottom two rows keep
5163/5162-5163 rungs, i.e. at X = 0.16 essentially all 5163 candidate rungs are
taken and the sleeve is capacity-limited by rung size, not by the budget
(consistent with the manifest note).

## Selection uses no last-year statistic

v196_decoupled_allocation.py:46-48: ok = rows with gate_dd <= 20 and all
yearly[:4] net_pct >= 0; pool = ok or all rows; sel = max monthly_dev4 over
pool; final_score_selected reports monthly_5y/monthly_last_year/losing_years/
gate_dd/gate_pass once for the winner. monthly_dev4 in
research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py:267-268
is the geometric mean of years[:4] only. The last-year monthly (2.919 for
the winner) is reported, never ranked on. PASS.

Eligibility note: all three rows have gate_dd <= 20 (19.44 / 17.28 / 15.79)
with zero losing years in the first four (in fact zero losing years overall),
so ok is all three rows; the winner (0.25, 0.08) is the plain max-dev4 row
(4.972 > 4.590 > 3.945). Audit eligible [P2_T150_X160, P2_T200_X120,
P2_T250_X080], selection P2_T250_X080 maps to reported selected t0.25_x0.08;
final score selected is identical (5y 4.558 / last 2.919 / DD 19.44).

## Look-ahead check

engine_user.py plus the v196 driver:

- Feature timing: target uses books[t], s[t], g[t] at the decision
  (engine_user.py:89-98); sigma_d/sigma_4h are rolling windows ending at t
  (prepare sig4, line 63; sd = sig4*sqrt(6)); cubes row i is the holding bar
  T = t+4h (prepare via v172.cube_ohlc). Member books are causal inputs by
  construction; P2 = (A+B)/2 is an algebraic mix at bar t only. The paired
  target only rescales the causal s = min(target/vol, 2) on the books leg,
  with vol from books.shift(2) returns; the fixed rung scale 1.497 is a
  pre-registered constant (mean scale of the v176-v183 runs per the driver
  docstring), not fit on any test year, and the rung notional still uses the
  causal governor g[t]. PASS.
- Label windows: no forward return is read; PnL comes only from 1m fills,
  SL/TP exits during T, and the T+4h exit/settlement prices. TP uses
  m_sleeve_tp = 1.0 on all rows (line 209 tp = lv * (1 + k sig4)), SL at
  5 sigma_4h unchanged. PASS.
- Fit windows: no statistic is fit on any test year in this path; vol and
  the governor are running causal filters (vol from books.shift(2) returns,
  governor from eq at i-2 over the trailing 540 bars); (target, X) in
  ((0.25, 0.08), (0.20, 0.12), (0.15, 0.16)) with rung_scale_fixed 1.497 was
  pre-registered for this direction, not tuned here; selection uses
  first-four-years metrics only. PASS.
- Fill timing: book limit 10 bps better than minute-0, minutes 2..238 strict
  trade-through with expiry (engine_user.py:111-118, d_limit/win_end per
  row); SL/TP checked from minute 0 on the held position and from the fill
  minute on the new position, stop-first in one minute, flat afterwards
  with the pending order cancelled (lines 125-176); sleeve trigger minutes
  16..238 strict with exits strictly after the fill minute in (minute,
  rung, asset) budget order with risk budget X per row and gap 0.02
  (lines 186-228); sleeve SL uses m_sleeve_sl = 5 per row, rung notional
  rn = 1.497 * g * 0.25/4/1.657 on every row. PASS.

Fee/funding arithmetic: maker 0.0002 on book entries and TP, taker 0.00055
on stops/market exits, longs pay 0.0001 at 00/08/16 UTC settlements, shorts
zero, no carry (engine_user.py:33-36,169-180, funds in sleeve exit). This is
the AGENTS.md gate cost model. tests/test_engine_user.py covers limit fill
+ TP, stop through a gap (fills at minute open), unfilled-limit expiry, and
long funding at settlement on synthetic bars. PASS.

## Verdict

- Engineering REPRODUCED bit-exact on all three rows (dev4/5y/last-year,
  gate DD, yearly legs, stats).
- Look-ahead PASS (decision-known features/sigma/scale/governor, no label
  or fit leakage, causal fill/stop/sleeve timing, first-four-years
  selection only; S_FIX 1.497 is a pre-registered constant, not a test-fit
  statistic).
- Gate: every row fails monthly >= 5% on dev4/5y/last-year (best dev4 4.972
  on (0.25, 0.08), best 5y 4.558, best last-year 2.919) with no losing year;
  all three pass DD <= 20% (19.44 / 17.28 / 15.79). Selected (0.25, 0.08)
  final 5y 4.558 / last 2.919 / DD 19.44 -> gate fails. Manifest (status
  rejected, live_approved false, audit passed/replay_complete false awaiting
  audit) must stay non-live_approved.
