# v192 blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v192_audit/replication.json
was saved before opening v192/ (see Part A script header E1-E8/L1-L4).
Base: research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py
(the gate engine implementing the AGENTS.md 2026-09-27 user goal, gate cost model
and current execution assumptions). Leader files were not edited.

Reported: research/parallel/rounds/parallel-20260906-r2/v192/v192_result.json
from research/parallel/rounds/parallel-20260906-r2/v192/v192_book_limit_orders.py.
Audit: rows key in
research/parallel/rounds/parallel-20260906-r2/v192_audit/replication.json
(P2 = (A+B)/2 with the dip sleeve, rung stop L(1 - 5 sigma_4h), TP
L(1 + sigma_4h) unchanged, book SL/TP m = 4, book limit (d, W) =
(0.001, 60), (0.001, 239), (0.0003, 239)).

## Pipeline construction check

v192_book_limit_orders.py:31-36 reindexes members A/B to the books154
index (missing -> 0.0) and builds v151 = (A+B)/2; prep is built once from
books154/opens and simulate is called with m_sl = 4.0, m_sleeve_sl = 5.0,
d_limit = d, win_end = W per row. Audit builds P2 on the member union
index (missing -> 0.0) after checking (A+B+D)/3 == books_v154 exactly
(max abs diff 0.0, union bars 10950) and verifies P2 index/columns equal
books_v154; shared 1m preparation is identical for all rows (same idx/cols).
PASS (same books, same opens, same cubes).

## v192 (P2+sleeve k=5 under engine_user, book m = 4, limit (d, W) sweep)

| row | monthly dev4 % | monthly 5y % | last-year monthly % | gate DD % | yearly nets % |
| --- | --- | --- | --- | --- | --- |
| reported 10bps_60m | 4.054 | 3.732 | 2.454 | 19.08 | 24.04 / 47.80 / 91.40 / 91.98 / 33.76 |
| audit P2_d0010_W060 | 4.054 | 3.732 | 2.454 | 19.08 | 24.04 / 47.80 / 91.40 / 91.98 / 33.76 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported 10bps_bar | 4.069 | 3.761 | 2.541 | 19.18 | 24.76 / 47.78 / 87.81 / 95.86 / 35.14 |
| audit P2_d0010_W239 | 4.069 | 3.761 | 2.541 | 19.18 | 24.76 / 47.78 / 87.81 / 95.86 / 35.14 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported 3bps_bar | 3.922 | 3.610 | 2.371 | 19.23 | 23.51 / 43.98 / 85.90 / 91.75 / 32.47 |
| audit P2_d0003_W239 | 3.922 | 3.610 | 2.371 | 19.23 | 23.51 / 43.98 / 85.90 / 91.75 / 32.47 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |

Stats are bit-exact on every row (fills/unfilled/stops/tps/rungs/rung_stops/
rung_tps/fees/funding, e.g. 10bps_60m 35301 / 8283 / 74 / 51 / 2253 / 72 /
1105 / 0.0964 / 0.1844; 10bps_bar 39269 / 4004 / 76 / 50 / 2254 / 72 /
1106 / 0.0980 / 0.1838; 3bps_bar 40966 / 2085 / 75 / 49 / 2259 / 72 /
1109 / 0.0985 / 0.1835). dd_4h/dd_1m match (10bps_60m 18.88 / 19.08;
10bps_bar 18.96 / 19.18; 3bps_bar 18.97 / 19.23). Longer resting window
-> more fills and fewer expiries (8283 -> 4004 at 10 bps); tighter 3 bps
offset at the full-bar window -> still more fills (40966) and fewest
expiries (2085). Sleeve leg is flat across rows (rung_stops 72 on all
three; rung_tps 1105 / 1106 / 1109); only the book leg moves.
(0.001, 60) equals v191 k=5 bit-exact (dev4 4.054, 5y 3.732, last
2.454, DD 19.08, nets 24.04 / 47.80 / 91.40 / 91.98 / 33.76, stats
35301 / 8283 / 74 / 51 / 2253 / 72 / 1105).

## Selection uses no last-year statistic

v192_book_limit_orders.py:42-44: eligible = rows with gate_dd <= 20 and
all yearly[:4] net_pct >= 0; selected = max monthly_dev4 over eligible
(fallback all rows); final_score_selected reports monthly_5y/
monthly_last_year/losing_years/gate_dd/gate_pass once for the winner.
monthly_dev4 in
research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py:267
is the geometric mean of years[:4] only. The last-year monthly (2.541 for
the winner) is reported, never ranked on. PASS.

Eligibility note: all three audit rows have gate_dd <= 20 and zero losing
years in the first four (in fact zero losing years overall), so the DD and
losing-year filters do not discriminate; the winner 10bps_bar (dev4 4.069)
is the plain max-dev4 row. Extending the window at 10 bps improves dev4
slightly (4.054 -> 4.069) while raising gate DD slightly (19.08 -> 19.18);
tightening to 3 bps at the full window lowers dev4 (4.069 -> 3.922).

## Look-ahead check

engine_user.py plus the v192 driver:

- Feature timing: target uses books[t], s[t], g[t] at the decision
  (engine_user.py:89-98); sigma_d/sigma_4h are rolling windows ending at t
  (prepare sig4, line 99 sd = sig4*sqrt(6)); cubes row i is the holding bar
  T = t+4h (prepare via v172.cube_ohlc). Member books are causal inputs by
  construction; P2 = (A+B)/2 is an algebraic mix at bar t only. PASS.
- Label windows: no forward return is read; PnL comes only from 1m fills,
  SL/TP exits during T, and the T+4h exit/settlement prices. PASS.
- Fit windows: no statistic is fit on any test year in this path; vol and
  the governor are running causal filters (vol from books.shift(2) returns,
  governor from eq at i-2 over the trailing 540 bars); (d, W) in
  ((0.001, 60), (0.001, 239), (0.0003, 239)) was pre-registered for this
  direction, not tuned here; selection uses first-four-years metrics only.
  PASS.
- Fill timing: book limit d better than minute-0, minutes 2..W-1 strict
  trade-through with expiry (engine_user.py:111-118, d_limit/win_end per
  row); SL/TP checked from minute 0 on the held position and from the fill
  minute on the new position, stop-first in one minute, flat afterwards
  with the pending order cancelled (lines 125-176); sleeve trigger minutes
  16..238 strict with exits strictly after the fill minute in (minute,
  rung, asset) budget order (lines 186-230); sleeve SL uses m_sleeve_sl =
  5 per row, TP at L(1 + sigma_4h) unchanged. PASS.

Fee/funding arithmetic: maker 0.0002 on book entries and TP, taker 0.00055
on stops/market exits, longs pay 0.0001 at 00/08/16 UTC settlements, shorts
zero, no carry (engine_user.py:33-36,169-180, funds in sleeve exit). This is
the AGENTS.md gate cost model. tests/test_engine_user.py covers limit fill
+ TP, stop through a gap (fills at minute open), unfilled-limit expiry, and
long funding at settlement on synthetic bars. PASS.

## Verdict

- Engineering REPRODUCED bit-exact on all three rows (dev4/5y/last-year,
  gate DD, yearly nets, stats).
- (0.001, 60) equals v191 k=5 bit-exact as required.
- Look-ahead PASS (decision-known features/sigma/scale/governor, no label
  or fit leakage, causal fill/stop/sleeve timing, first-four-years
  selection only).
- Gate: every row fails monthly >= 5% (best dev4 4.069 10bps_bar, best 5y
  3.761, best last-year 2.541 10bps_bar) while passing DD <= 20% with no
  losing year. Selected 10bps_bar final 5y 3.761 / last 2.541 / DD
  19.18 -> gate fails. Manifest (status rejected, live_approved false,
  audit passed/replay_complete false awaiting audit) must stay
  non-live_approved.
