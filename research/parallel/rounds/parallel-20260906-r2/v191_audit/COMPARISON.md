# v191 blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v191_audit/replication.json
was saved before opening v191/ (see Part A script header E1-E8/L1-L4).
Base: research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py
(the gate engine implementing the OPENCODE_V188_AUDIT.md spec from AGENTS.md
2026-09-27 user goal, gate cost model and current execution assumptions).
Leader files were not edited.

Reported: research/parallel/rounds/parallel-20260906-r2/v191/v191_result.json
from research/parallel/rounds/parallel-20260906-r2/v191/v191_sleeve_stop_width.py.
Audit: rows key in
research/parallel/rounds/parallel-20260906-r2/v191_audit/replication.json
(P2 = (A+B)/2 with the dip sleeve, book SL/TP m = 4, sleeve rung stop
L(1 - k sigma_4h) for k = 2, 3, 5, TP L(1 + sigma_4h) unchanged).

## Pipeline construction check

v191_sleeve_stop_width.py:31-34 reindexes members A/B to the books154
index (missing -> 0.0) and builds v151 = (A+B)/2; prep is built once from
books154/opens and simulate is called with m_sl = 4.0, m_sleeve_sl = k
per row. Audit builds P2 on the member union index (missing -> 0.0) after
checking (A+B+D)/3 == books_v154 exactly (max abs diff 0.0, union bars
10950) and verifies P2 index/columns equal books_v154; shared 1m
preparation is identical for all k (same idx/cols). PASS (same books,
same opens, same cubes).

## v191 (P2+sleeve under engine_user, book m = 4, sleeve stop k sweep)

| row | monthly dev4 % | monthly 5y % | last-year monthly % | gate DD % | yearly nets % |
| --- | --- | --- | --- | --- | --- |
| reported 2.0 | 3.896 | 3.584 | 2.342 | 19.41 | 23.37 / 52.50 / 86.27 / 78.73 / 32.02 |
| audit P2_sleeve_k2 | 3.896 | 3.584 | 2.342 | 19.41 | 23.37 / 52.50 / 86.27 / 78.73 / 32.02 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported 3.0 | 3.935 | 3.593 | 2.236 | 19.35 | 24.27 / 49.03 / 86.52 / 84.62 / 30.40 |
| audit P2_sleeve_k3 | 3.935 | 3.593 | 2.236 | 19.35 | 24.27 / 49.03 / 86.52 / 84.62 / 30.40 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported 5.0 | 4.054 | 3.732 | 2.454 | 19.08 | 24.04 / 47.80 / 91.40 / 91.98 / 33.76 |
| audit P2_sleeve_k5 | 4.054 | 3.732 | 2.454 | 19.08 | 24.04 / 47.80 / 91.40 / 91.98 / 33.76 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |

Stats are bit-exact on every row (fills/unfilled/stops/tps/rungs/rung_stops/
rung_tps/fees/funding, e.g. k2 35288 / 8296 / 74 / 51 / 2571 / 432 /
1214 / 0.0960 / 0.1835; k3 35260 / 8285 / 74 / 51 / 2361 / 212 /
1142 / 0.0961 / 0.1834; k5 35301 / 8283 / 74 / 51 / 2253 / 72 /
1105 / 0.0964 / 0.1844). dd_4h/dd_1m match (k2 19.38 / 19.41; k3
19.22 / 19.35; k5 18.88 / 19.08). Book fills/stops/tps are flat across
k (74 / 51) as the book leg is unchanged; only the sleeve leg moves.
Wider sleeve stop -> fewer rung stops (432 -> 212 -> 72) and fewer rung
TPs (1214 -> 1142 -> 1105) with fewer taken rungs (2571 -> 2361 -> 2253).
k = 2 equals v189 P2_v151+sleeve bit-exact (dev4 3.896, 5y 3.584, last
2.342, DD 19.41, nets 23.37 / 52.50 / 86.27 / 78.73 / 32.02).

## Selection uses no last-year statistic

v191_sleeve_stop_width.py:41-43: eligible = rows with gate_dd <= 20 and
all yearly[:4] net_pct >= 0; selected = max monthly_dev4 over eligible;
final_score_selected reports monthly_5y/monthly_last_year/losing_years/
gate_dd/gate_pass once for the winner. monthly_dev4 in
research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py:267
is the geometric mean of years[:4] only. The last-year monthly (2.454 for
the winner) is reported, never ranked on. PASS.

Eligibility note: all three audit rows have gate_dd <= 20 and zero losing
years in the first four (in fact zero losing years overall), so the DD and
losing-year filters do not discriminate; the winner k = 5 (dev4 4.054) is
the plain max-dev4 row. Wider stops monotonically improve dev4 here
(3.896 -> 3.935 -> 4.054) while lowering gate DD (19.41 -> 19.35 -> 19.08).

## Look-ahead check

engine_user.py plus the v191 driver:

- Feature timing: target uses books[t], s[t], g[t] at the decision
  (engine_user.py:89-98); sigma_d/sigma_4h are rolling windows ending at t
  (prepare sig4, line 99 sd = sig4*sqrt(6)); cubes row i is the holding bar
  T = t+4h (prepare via v172.cube_ohlc). Member books are causal inputs by
  construction; P2 = (A+B)/2 is an algebraic mix at bar t only. PASS.
- Label windows: no forward return is read; PnL comes only from 1m fills,
  SL/TP exits during T, and the T+4h exit/settlement prices. PASS.
- Fit windows: no statistic is fit on any test year in this path; vol and
  the governor are running causal filters (vol from books.shift(2) returns,
  governor from eq at i-2 over the trailing 540 bars); k in (2, 3, 5) was
  pre-registered for this direction, not tuned here; selection uses
  first-four-years metrics only. PASS.
- Fill timing: book limit 10 bps, minutes 2..59 strict trade-through with
  expiry (engine_user.py:111-118); SL/TP checked from minute 0 on the held
  position and from the fill minute on the new position, stop-first in one
  minute, flat afterwards with the pending order cancelled (lines 125-176);
  sleeve trigger minutes 16..238 strict with exits strictly after the fill
  minute in (minute, rung, asset) budget order (lines 186-230); sleeve SL
  uses m_sleeve_sl = k per row, TP at L(1 + sigma_4h) unchanged. PASS.

Fee/funding arithmetic: maker 0.0002 on book entries and TP, taker 0.00055
on stops/market exits, longs pay 0.0001 at 00/08/16 UTC settlements, shorts
zero, no carry (engine_user.py:33-36,169-180, funds in sleeve exit). This is
the AGENTS.md gate cost model. tests/test_engine_user.py covers limit fill
+ TP, stop through a gap (fills at minute open), unfilled-limit expiry, and
long funding at settlement on synthetic bars. PASS.

## Verdict

- Engineering REPRODUCED bit-exact on all three rows (dev4/5y/last-year,
  gate DD, yearly nets, stats).
- k = 2 equals v189 P2_v151+sleeve bit-exact as required.
- Look-ahead PASS (decision-known features/sigma/scale/governor, no label
  or fit leakage, causal fill/stop/sleeve timing, first-four-years
  selection only).
- Gate: every row fails monthly >= 5% (best dev4 4.054 k5, best 5y
  3.732, best last-year 2.454 k5) while passing DD <= 20% with no
  losing year. Selected k = 5 final 5y 3.732 / last 2.454 / DD
  19.08 -> gate fails. Manifest (status rejected, live_approved false,
  audit passed/replay_complete false awaiting audit) must stay
  non-live_approved.
