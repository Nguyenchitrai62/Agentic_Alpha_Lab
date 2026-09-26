# v194 blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v194_audit/replication.json
was saved before opening v194/ (see Part A script header E1-E8/L1-L4).
Base: research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py
(the gate engine implementing the AGENTS.md 2026-09-27 user goal, gate cost model
and current execution assumptions). Leader files were not edited.

Reported: research/parallel/rounds/parallel-20260906-r2/v194/v194_result.json
from research/parallel/rounds/parallel-20260906-r2/v194/v194_sleeve_tp_width.py.
Audit: rows key in
research/parallel/rounds/parallel-20260906-r2/v194_audit/replication.json
(v193 with X = 0.08, varying only the rung take-profit TP = L (1 + k sigma_4h),
k = 1, 1.5, 2; P2 = (A+B)/2 books, book limits 10 bps resting minutes 2..238,
book SL/TP m = 4, rung SL L (1 - 5 sigma_4h)).

## Pipeline construction check

v194_sleeve_tp_width.py:28-38 reindexes members A/B to the books154
index (missing -> 0.0) and builds v151 = (A+B)/2; prep is built once from
books154/opens and simulate is called with m_sl = 4.0, m_sleeve_sl = 5.0,
d_limit = 0.001, win_end = 239, sleeve_risk_budget = 0.08 per row with
m_sleeve_tp = k in (1.0, 1.5, 2.0). Audit builds P2 on the member union
index (missing -> 0.0) after checking (A+B+D)/3 == books_v154 exactly
(max abs diff 0.0, union bars 10950) and verifies P2 index/columns equal
books_v154; shared 1m preparation is identical for all rows (same idx/cols).
PASS (same books, same opens, same cubes).

## v194 (P2 X=0.08, rung TP sweep k = 1, 1.5, 2)

| row | monthly dev4 % | monthly 5y % | last-year monthly % | gate DD % | yearly nets % |
| --- | --- | --- | --- | --- | --- |
| reported 1.0 | 5.046 | 4.603 | 2.847 | 19.33 | 34.58 / 54.37 / 122.74 / 129.58 / 40.05 |
| audit P2_X080_TP100 | 5.046 | 4.603 | 2.847 | 19.33 | 34.58 / 54.37 / 122.74 / 129.58 / 40.05 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported 1.5 | 4.968 | 4.541 | 2.849 | 20.10 | 30.28 / 48.53 / 130.49 / 129.80 / 40.09 |
| audit P2_X080_TP150 | 4.968 | 4.541 | 2.849 | 20.10 | 30.28 / 48.53 / 130.49 / 129.80 / 40.09 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported 2.0 | 4.911 | 4.478 | 2.766 | 21.69 | 28.55 / 42.26 / 132.03 / 135.35 / 38.73 |
| audit P2_X080_TP200 | 4.911 | 4.478 | 2.766 | 21.69 | 28.55 / 42.26 / 132.03 / 135.35 / 38.73 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |

k = 1 equals the v193 X = 0.08 row bit-exact as required (dev4 5.046,
5y 4.603, last 2.847, DD 19.33, nets 34.58 / 54.37 / 122.74 / 129.58 /
40.05, stats 39882 / 4063 / 76 / 49 / 5001 / 191 / 2714 / liq 0 /
fees 0.098 / funding 0.1844).

Stats are bit-exact on every row (fills/unfilled/stops/tps/rungs/rung_stops/
rung_tps/liq/fees/funding, e.g. k=1.0 39882 / 4063 / 76 / 49 / 5001 / 191 /
2714 / 0 / 0.098 / 0.1844; k=1.5 39720 / 4042 / 76 / 49 / 4949 / 238 /
1753 / 0 / 0.0975 / 0.183; k=2.0 39601 / 4029 / 76 / 49 / 4925 / 257 /
1111 / 0 / 0.0971 / 0.1823). dd_4h/dd_1m match (k=1.0 19.13 / 19.33;
k=1.5 19.58 / 20.10; k=2.0 20.40 / 21.69). Yearly legs match in full
(net/monthly/dd_1m/mean_g per anchor). Wider TP -> fewer rung TPs
(2714 -> 1753 -> 1111) and more rung stops (191 -> 238 -> 257); rung
count eases slightly (5001 -> 4949 -> 4925) while the book leg is flat
(stops 76, tps 49 on all three; fills 39882 -> 39720 -> 39601 move only
via the equity-linked min-notional filter).

## Selection uses no last-year statistic

v194_sleeve_tp_width.py:42-44: eligible = rows with gate_dd <= 20 and
all yearly[:4] net_pct >= 0; selected = max monthly_dev4 over eligible
(fallback all rows); final_score_selected reports monthly_5y/
monthly_last_year/losing_years/gate_dd/gate_pass once for the winner.
monthly_dev4 in
research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py:267
is the geometric mean of years[:4] only. The last-year monthly (2.847 for
the winner) is reported, never ranked on. PASS.

Eligibility note: only k = 1.0 has gate_dd <= 20 (19.33) with zero losing
years in the first four (in fact zero losing years overall on all rows),
so the DD filter alone selects the winner; k = 1.5 (DD 20.10) and k = 2.0
(DD 21.69) are excluded by DD <= 20. The winner k = 1.0 is also the plain
max-dev4 row (5.046 > 4.968 > 4.911), so widening the TP lowers dev4 while
raising gate DD. Audit selection P2_X080_TP100 maps to reported selected
1.0; final score selected is identical (5y 4.603 / last 2.847 / DD 19.33).

## Look-ahead check

engine_user.py plus the v194 driver:

- Feature timing: target uses books[t], s[t], g[t] at the decision
  (engine_user.py:89-98); sigma_d/sigma_4h are rolling windows ending at t
  (prepare sig4, line 99 sd = sig4*sqrt(6)); cubes row i is the holding bar
  T = t+4h (prepare via v172.cube_ohlc). Member books are causal inputs by
  construction; P2 = (A+B)/2 is an algebraic mix at bar t only. PASS.
- Label windows: no forward return is read; PnL comes only from 1m fills,
  SL/TP exits during T, and the T+4h exit/settlement prices. TP uses
  m_sleeve_tp = k per row (line 209 tp = lv * (1 + k sig4)), SL unchanged
  at 5 sigma_4h. PASS.
- Fit windows: no statistic is fit on any test year in this path; vol and
  the governor are running causal filters (vol from books.shift(2) returns,
  governor from eq at i-2 over the trailing 540 bars); k in (1, 1.5, 2.0)
  was pre-registered for this direction, not tuned here; selection uses
  first-four-years metrics only. PASS.
- Fill timing: book limit 10 bps better than minute-0, minutes 2..238 strict
  trade-through with expiry (engine_user.py:111-118, d_limit/win_end per
  row); SL/TP checked from minute 0 on the held position and from the fill
  minute on the new position, stop-first in one minute, flat afterwards
  with the pending order cancelled (lines 125-176); sleeve trigger minutes
  16..238 strict with exits strictly after the fill minute in (minute,
  rung, asset) budget order with risk budget X = 0.08 and gap 0.02
  (lines 186-228); sleeve SL uses m_sleeve_sl = 5 per row, TP at
  L (1 + k sigma_4h) varies per row. PASS.

Fee/funding arithmetic: maker 0.0002 on book entries and TP, taker 0.00055
on stops/market exits, longs pay 0.0001 at 00/08/16 UTC settlements, shorts
zero, no carry (engine_user.py:33-36,169-180, funds in sleeve exit). This is
the AGENTS.md gate cost model. tests/test_engine_user.py covers limit fill
+ TP, stop through a gap (fills at minute open), unfilled-limit expiry, and
long funding at settlement on synthetic bars. PASS.

## Verdict

- Engineering REPRODUCED bit-exact on all three rows (dev4/5y/last-year,
  gate DD, yearly nets, stats).
- k = 1 equals the v193 X = 0.08 row bit-exact as required.
- Look-ahead PASS (decision-known features/sigma/scale/governor, no label
  or fit leakage, causal fill/stop/sleeve timing, first-four-years
  selection only).
- Gate: every row fails monthly >= 5% on 5y/last-year (best dev4 5.046 k=1.0,
  best 5y 4.603, best last-year 2.849 k=1.5) with no losing year; only k=1.0
  passes DD <= 20% (19.33 vs 20.10 / 21.69). Selected k=1.0 final 5y 4.603 /
  last 2.847 / DD 19.33 -> gate fails. Manifest (status rejected,
  live_approved false, audit passed/replay_complete false awaiting audit)
  must stay non-live_approved.
