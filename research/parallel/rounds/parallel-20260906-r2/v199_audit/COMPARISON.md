# v199 blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v199_audit/replication.json
was saved before opening v199/ (see Part A script header E1-E8/L1-L4 and the
C1/C2 convention asserts). Base: research/parallel/rounds/parallel-20260906-r2/
engine_user/engine_user.py (the gate engine implementing the AGENTS.md 2026-09-27
user goal, gate cost model and current execution assumptions), UPDATED to the two
conventions adopted from the v188 audit: (1) the 1m-marked DD uses peaks over the
minute path (intrabar highs count), (2) a stop on the held position wins a
same-minute tie with a new book fill (the pending order is cancelled). Leader
files were not edited.

Reported: research/parallel/rounds/parallel-20260906-r2/v199/v199_result.json
from research/parallel/rounds/parallel-20260906-r2/v199/v199_ladder_depth.py.
Audit: rows key in
research/parallel/rounds/parallel-20260906-r2/v199_audit/replication.json
(v197 pipeline v151 = (A+B)/2, books vol target 0.25, per-rung notional fixed at
s g 1.5 0.25/4/1.657 via size_mult = 1.5 on every row regardless of rung count,
stop-risk budget X = 0.12 on every row; book SL/TP m = 4, rung SL 5 sigma_4h,
TP L(1 + sigma_4h), book limit (d, W) = (0.001, 239), gap 0.02, cap 2.0;
ladders LADDER_4 = (2.5, 3, 3.5, 4), LADDER_6 = (2.5, 3, 3.5, 4, 5, 6),
LADDER_3456 = (3, 4, 5, 6)).

## Pipeline construction check

v199_ladder_depth.py:36-37 builds v151 = (A+B)/2 on the books154 index
(missing -> 0.0) but prepares with eu.prepare(books154, opens); the audit builds
P2 on the member union index (missing -> 0.0) after checking (A+B+D)/3 ==
books_v154 exactly (max abs diff 0.0, union bars 10950, same 5 majors columns)
and verifies P2 index/columns equal books_v154; shared 1m preparation is
identical for all rows (same idx/cols). As in the v193/v197/v198 audits, prepare
uses books only for idx/cols while vol/s inside simulate is recomputed from the
books argument (P2 == v151), so the driver quirk is immaterial. PASS (same books,
same opens, same cubes). Driver passes sleeve_risk_budget = 0.12 and
size_mult = 1.5 per row (v199_ladder_depth.py:41-42) with rungs = rg per variant,
and leaves target, cap, gap, m_sleeve_tp and rung_scale_fixed at engine defaults;
engine_user.py:71 target default 0.25, cap default 2.0, gap default 0.02,
m_sleeve_tp default 1.0, rung_scale_fixed default None match the audit explicit
TARGET = 0.25, CAP = 2.0, GAP = 0.02, TP mult 1.0, s-scaled notional. The fixed
per-rung notional takes the size_mult branch (engine_user.py:188
rn = s * g * size_mult * 0.25/4/1.657 with the constant divisor 4, not the rung
count), so all three ladders carry the same per-rung size — the registered v199
design (deeper rungs add capital only in deep drops). The driver docstring states
the same ("Per-rung size is unchanged (x1.5 of 0.25/4 before scaling)").

Conventions C1/C2 are present in the engine and asserted by the audit script
(inspect of eu.simulate / eu.summarize): seg_end = fill_min + 1, i.e. the held
position is checked over [0, fill_min + 1) with fill cancellation on a held
stop/TP at or before the fill minute (engine_user.py:159-162, 803-826);
simulate tracks eq_max per bar (line 240) and summarize peaks over
maximum(e, ex) with troughs over minimum(e, em) (lines 264, 270-272). The driver
ENGINE NOTE (v199_ladder_depth.py:10-11) states it runs on engine_user after the
v188-audit fix and that the reference row re-scores v197 under the stricter DD.
PASS — audit and driver run the same corrected engine.

## v199 (v197 pipeline with ladder depth variants, fixed per-rung size x1.5, X = 0.12)

| row | monthly dev4 % | monthly 5y % | last-year monthly % | gate DD % | yearly nets % |
| --- | --- | --- | --- | --- | --- |
| reported ref_2.5-4 | 5.562 | 4.996 | 2.761 | 19.72 | 40.67 / 51.32 / 147.63 / 154.98 / 38.66 |
| audit LADDER_4 | 5.562 | 4.996 | 2.761 | 19.72 | 40.67 / 51.32 / 147.63 / 154.98 / 38.66 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported to6_six | 5.713 | 5.098 | 2.675 | 20.27 | 43.18 / 60.54 / 137.68 / 163.43 / 37.26 |
| audit LADDER_6 | 5.713 | 5.098 | 2.675 | 20.27 | 43.18 / 60.54 / 137.68 / 163.43 / 37.26 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported deep_3-6 | 4.824 | 4.484 | 3.137 | 18.38 | 35.24 / 60.90 / 86.22 / 136.80 / 44.87 |
| audit LADDER_3456 | 4.824 | 4.484 | 3.137 | 18.38 | 35.24 / 60.90 / 86.22 / 136.80 / 44.87 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |

Yearly legs match in full (net/monthly/dd_1m/mean_g per anchor verified equal
as dicts, not just nets).

Stats are bit-exact on every row (fills/unfilled/stops/tps/rungs/rung_stops/
rung_tps/liq/fees/funding, e.g. ref/LADDER_4 40078 / 4079 / 76 / 48 / 5004 /
191 / 2717 / 0 / 0.0968 / 0.1817; to6/LADDER_6 40178 / 4074 / 75 / 47 / 5368 /
227 / 2996 / 0 / 0.0954 / 0.1806; deep/LADDER_3456 39826 / 4049 / 74 / 48 /
2466 / 139 / 1561 / 0 / 0.096 / 0.1834). dd_4h/dd_1m match (ref 19.07 / 19.72;
to6 18.74 / 20.27; deep 18.19 / 18.38). Adding the two deep rungs (4 -> 6
rungs) adds +364 rung takes (+36 rung stops, +279 rung TPs) while dropping the
shallow 2.5 rung (deep_3-6) more than halves takes (5004 -> 2466) with fewer
stops (191 -> 139).

Reference row re-scores v197 under the stricter DD exactly as the driver
announces: LADDER_4 nets/stats equal the v197 selected row P2_M150 exactly
(nets 40.67 / 51.32 / 147.63 / 154.98 / 38.66; stats 40078 / 4079 / 76 / 48 /
5004 / 191 / 2717 / 0 / 0.0968 / 0.1817) while gate DD moves 19.32 -> 19.72
(+0.40pp from the C1 minute-path peaks; dd_4h unchanged at 19.07). The C2
stop-wins-tie convention leaves the book counts untouched here (fills/stops/TPs
identical to v197). PASS — the required v197 anchor holds under the corrected
engine, so the v199 sweep is a pure ladder-depth experiment.

## Selection uses no last-year statistic

v199_ladder_depth.py:46-48: ok = rows with gate_dd <= 20 and all
yearly[:4] net_pct >= 0; pool = ok or all rows; sel = max monthly_dev4 over
pool; final_score_selected reports monthly_5y/monthly_last_year/losing_years/
gate_dd/gate_pass once for the winner. monthly_dev4 in
research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py is the
geometric mean of years[:4] only. The last-year monthly (2.761 for the winner)
is reported, never ranked on. PASS.

Eligibility note: to6_six (dev4 5.713, the plain max-dev4 row) is correctly
excluded by gate_dd 20.27 > 20, so ok = {ref_2.5-4, deep_3-6}; the winner
ref_2.5-4 (dev4 5.562 > 4.824) is the plain max-dev4 eligible row. Audit
eligible [LADDER_3456, LADDER_4], selection LADDER_4 maps to reported selected
ref_2.5-4; final score selected is identical (5y 4.996 / last 2.761 / DD 19.72).

## Look-ahead check

engine_user.py plus the v199 driver:

- Feature timing: target uses books[t], s[t], g[t] at the decision
  (engine_user.py:89-99); sigma_d/sigma_4h are rolling windows ending at t
  (prepare sig4; sd = sig4*sqrt(6)); cubes row i is the holding bar
  T = t+4h (prepare via v172.cube_ohlc). Member books are causal inputs by
  construction; P2 = (A+B)/2 is an algebraic mix at bar t only. The ladder
  choice only changes which trigger levels L = open(T)(1 - k sigma_4h(t)) are
  armed — all decision-known — and the per-rung size multiplier 1.5 and budget
  X = 0.12 are pre-registered constants, none fit on any test year. PASS.
- Label windows: no forward return is read; PnL comes only from 1m fills,
  SL/TP exits during T, and the T+4h exit/settlement prices. TP uses
  m_sleeve_tp = 1.0 on all rows, SL at 5 sigma_4h unchanged. PASS.
- Fit windows: no statistic is fit on any test year in this path; vol and
  the governor are running causal filters (vol from books.shift(2) returns,
  governor from eq at i-2 over the trailing 540 bars); ladders
  ((2.5,3,3.5,4), (2.5,3,3.5,4,5,6), (3,4,5,6)) with fixed per-rung notional
  were pre-registered for this direction (at most 3 variants), not tuned
  here; selection uses first-four-years metrics only. PASS.
- Fill timing: book limit 10 bps better than minute-0, minutes 2..238 strict
  trade-through with expiry and no fallback (engine_user.py:111-120,
  d_limit/win_end per row); held SL/TP checked from minute 0 over
  [0, fill_min + 1) so a held stop wins a same-minute tie with the new fill
  and cancels the pending order, stop-first in one minute, flat afterwards
  (lines 159-176); sleeve trigger minutes 16..238 strict with exits strictly
  after the fill minute in (minute, rung, asset) budget order with risk
  budget X = 0.12 per row and gap 0.02 (lines 186-236); sleeve SL uses
  m_sleeve_sl = 5 per row, rung notional rn = s * g * 1.5 * 0.25/4/1.657 on
  every row. PASS.

Fee/funding arithmetic: maker 0.0002 on book entries and TP, taker 0.00055
on stops/market exits, longs pay 0.0001 at 00/08/16 UTC settlements, shorts
zero, no carry (engine_user.py:33-36, funds in sleeve exit). This is
the AGENTS.md gate cost model. tests/test_engine_user.py covers limit fill
+ TP, stop through a gap (fills at minute open), unfilled-limit expiry, and
long funding at settlement on synthetic bars. PASS.

## Verdict

- Engineering REPRODUCED bit-exact on all three rows (dev4/5y/last-year,
  gate DD, yearly legs, stats).
- v197 anchor CONFIRMED under the corrected engine: reference nets/stats exact,
  DD 19.32 -> 19.72 from minute-path peaks only (C1); book fills/stops
  unchanged (C2 binds on no bar here).
- Look-ahead PASS (decision-known features/sigma/scale/governor, no label
  or fit leakage, causal fill/stop/sleeve/budget timing, first-four-years
  selection only; ladders/size/budget pre-registered, not test-fit).
- Direction result: extending the ladder to 6 sigma raises dev4 (5.562 ->
  5.713) and 5y (4.996 -> 5.098) but breaches the DD gate (20.27 > 20) and is
  correctly excluded; dropping the shallow rung lowers dev4 (4.824) at DD
  18.38. Selected = reference (the v197 config).
- Gate: selected ref_2.5-4/LADDER_4 is the best dev4 under the DD gate
  (dev4 5.562 >= 5, DD 19.72 <= 20, no losing year) but the gate still fails:
  5y 4.996 < 5 (by 0.004) and the most recent year 2.761 < 5 (nets 40.67 /
  51.32 / 147.63 / 154.98 / 38.66). Manifest (status rejected,
  live_approved false, audit passed/replay_complete false awaiting audit)
  must stay non-live_approved.
