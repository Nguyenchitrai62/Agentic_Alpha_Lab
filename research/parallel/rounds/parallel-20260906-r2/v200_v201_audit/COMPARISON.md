# v200 + v201 blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v200_v201_audit/replication.json
was saved before opening v200/ or v201/ (see Part A script header E1-E9/L1-L4 and the
C1/C2 plus hourly/m_tp asserts). Base: research/parallel/rounds/parallel-20260906-r2/
engine_user/engine_user.py (the gate engine implementing the AGENTS.md 2026-09-27
user goal, gate cost model and current execution assumptions), with the two
conventions adopted from the v188 audit: (1) the 1m-marked DD uses peaks over the
minute path (intrabar highs count), (2) a stop on the held position wins a
same-minute tie with a new book fill (the pending order is cancelled). Leader
files were not edited.

Reported: research/parallel/rounds/parallel-20260906-r2/v200/v200_result.json
from research/parallel/rounds/parallel-20260906-r2/v200/v200_user_tp_sl_range.py,
and research/parallel/rounds/parallel-20260906-r2/v201/v201_result.json
from research/parallel/rounds/parallel-20260906-r2/v201/v201_hourly_ladder_risk_budget.py.
Audit: rows_a1 / rows_a2 in
research/parallel/rounds/parallel-20260906-r2/v200_v201_audit/replication.json
(v197 pipeline v151 = (A+B)/2, books vol target 0.25, per-rung notional fixed at
s g 1.5 0.25/4/1.657 via size_mult = 1.5 on every row regardless of rung count,
sleeve SL 5 sigma_4h, TP L(1 + sigma_4h), book limit (d, W) = (0.001, 239), gap 0.02,
cap 2.0; A1 book (SL, TP) = (2, 4), (2.5, 2.5), (3, 2) plus reference (4, 8);
A2 book fixed at (4, 8), 4h rungs (2.5, 3, 3.5, 4), hourly rungs 2.5/3/3.5/4 sigma_1h
with shared budget X = 0.12 / 0.18).

## Pipeline construction check

v200_user_tp_sl_range.py:38-39 builds v151 = (A+B)/2 on the books154 index
(missing -> 0.0) but prepares with eu.prepare(books154, opens); the audit builds
P2 on the member union index (missing -> 0.0) after checking (A+B+D)/3 ==
books_v154 exactly (max abs diff 0.0, union bars 10950, same 5 majors columns)
and verifies P2 index/columns equal books_v154; shared 1m preparation is
identical for all rows (same idx/cols). As in the v193/v197/v199 audits, prepare
uses books only for idx/cols while vol/s inside simulate is recomputed from the
books argument (P2 == v151), so the driver quirk is immaterial. PASS (same books,
same opens, same cubes). Driver passes m_sleeve_sl = 5.0, d_limit = 0.001,
win_end = 239, sleeve_risk_budget = 0.12, size_mult = 1.5 per row
(v200_user_tp_sl_range.py:45-47) with m_sl/m_tp per variant, and leaves target,
cap, gap, m_sleeve_tp and rungs at engine defaults; engine_user.py:76 target
default 0.25, cap default 2.0, gap default 0.02, m_sleeve_tp default 1.0, rungs
default (2.5, 3, 3.5, 4) match the audit explicit TARGET = 0.25, CAP = 2.0,
GAP = 0.02, TP mult 1.0. The fixed per-rung notional takes the size_mult branch
(engine_user.py:194 rn = s * g * size_mult * 0.25/4/1.657 with the constant divisor
4), so every row carries the same per-rung size. PASS.

v201_hourly_ladder_risk_budget.py:40-42 builds v151 the same way and prepares with
eu.prepare(books154, opens); the audit uses the same P2/prepare path as above.
Driver calls eu.simulate(v151, opens, prep, m_sl = 4.0, m_sleeve_sl = 5.0,
sleeve = True, d_limit = 0.001, win_end = 239, sleeve_risk_budget = x,
size_mult = 1.5, hourly = hourly) without m_tp (v201_hourly_ladder_risk_budget.py:45-46),
so the book TP falls back to 2 * m_sl = 8 sigma_d (engine_user.py:134
mt = 2 * m_sl if m_tp is None else m_tp); the audit passes m_tp = 8.0 explicitly.
Bit-exact equality on every A2 row (below) proves the two spellings are the same
number. Remaining defaults (target, cap, gap, m_sleeve_tp, rungs) match as above. PASS.

Conventions C1/C2 are present in the engine and asserted by the audit script
(inspect of eu.simulate / eu.summarize / eu.prepare): seg_end = fill_min + 1, i.e.
the held position is checked over [0, fill_min + 1) with fill cancellation on a held
stop/TP at or before the fill minute (engine_user.py:165-169); simulate tracks eq_max
per bar (line 261) and summarize peaks over maximum(e, ex) with troughs over
minimum(e, em) (lines 289, 294-297). Hourly support asserted too: prepare builds
sig1h from 1m opens at minutes 0/60/120/180 over 1440 hours with min 480 and shifts
by one holding bar so it is known before the bar (engine_user.py:68-72); simulate
uses base = 1m open of minute 60h, bids 16..57 (h = 0) else 60h+4..60h+57, exits
strictly after the fill minute before minute 60(h+1) else market at that open
(h = 3: o2 with funding if settlement), shared risk rn * (5 sigma + gap) with each
rung's own sigma, order (minute, 4h first, rung, asset) (lines 204-226). PASS —
audit and drivers run the same corrected engine.

## v200 (v197 pipeline with closer book SL/TP, fixed per-rung size x1.5, X = 0.12)

| row | monthly dev4 % | monthly 5y % | last-year monthly % | gate DD % | yearly nets % |
| --- | --- | --- | --- | --- | --- |
| reported A_sl2_tp4 | 4.958 | 4.425 | 2.319 | 21.28 | 35.75 / 38.78 / 138.78 / 126.82 / 31.67 |
| audit SL2_TP4 | 4.958 | 4.425 | 2.319 | 21.28 | 35.75 / 38.78 / 138.78 / 126.82 / 31.67 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported B_sl2.5_tp2.5 | 4.840 | 4.447 | 2.889 | 24.75 | 42.22 / 22.80 / 149.04 / 122.30 / 40.75 |
| audit SL2p5_TP2p5 | 4.840 | 4.447 | 2.889 | 24.75 | 42.22 / 22.80 / 149.04 / 122.30 / 40.75 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported C_sl3_tp2 | 4.719 | 4.276 | 2.520 | 24.41 | 38.06 / 27.64 / 138.43 / 117.71 / 34.80 |
| audit SL3_TP2 | 4.719 | 4.276 | 2.520 | 24.41 | 38.06 / 27.64 / 138.43 / 117.71 / 34.80 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported ref_v197_sl4_tp8 | 5.562 | 4.996 | 2.761 | 19.72 | 40.67 / 51.32 / 147.63 / 154.98 / 38.66 |
| audit REF_4_8 | 5.562 | 4.996 | 2.761 | 19.72 | 40.67 / 51.32 / 147.63 / 154.98 / 38.66 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |

Yearly legs match in full (net/monthly/dd_1m/mean_g per anchor verified equal
as dicts, not just nets); dd_4h/dd_1m match (A 20.35 / 21.28; B 24.53 / 24.75;
C 24.18 / 24.41; ref 19.07 / 19.72).

Stats are bit-exact on every row (fills/unfilled/stops/tps/rungs/rung_stops/
rung_tps/liq/fees/funding/gross_sum/gross_max/bars, e.g. A 39739 / 4043 / 563 /
225 / 5006 / 191 / 2719 / 0 / 0.1401 / 0.1757 / 5241.4808 / 2.291 / 10944;
B 39627 / 3992 / 406 / 581 / 5007 / 192 / 2719 / 0 / 0.1453 / 0.1740 /
5269.4553 / 2.291 / 10944; C 39489 / 4009 / 278 / 831 / 5008 / 192 / 2718 / 0 /
0.1490 / 0.1714 / 5217.3696 / 2.291 / 10944; ref 40078 / 4079 / 76 / 48 / 5004 /
191 / 2717 / 0 / 0.0968 / 0.1817 / 5362.3762 / 2.291 / 10944). Book stops/TPs in
the audit equal stats stops/tps (A 563/225; B 406/581; C 278/831; ref 76/48):
tightening the book SL/TP multiplies stop/TP events ~10x while the sleeve legs
stay flat (rungs ~5004-5008, rung stops/TPs ~191-192 / ~2717-2719). Mean/max gross
book exposure (sum |target weight|) match the driver gross_mean_pct/gross_max_pct
exactly after x100 (A 47.9 / 229.1; B 48.1 / 229.1; C 47.7 / 229.1;
ref 49.0 / 229.1; audit gross_book_mean 0.478936 / 0.481493 / 0.476733 / 0.489983,
gross_max 2.291 on every row).

Reference row re-scores v197 under the corrected engine exactly: REF_4_8
nets/stats equal the v199 LADDER_4 anchor (nets 40.67 / 51.32 / 147.63 / 154.98 /
38.66; stats 40078 / 4079 / 76 / 48 / 5004 / 191 / 2717 / 0 / 0.0968 / 0.1817)
with gate DD 19.72. PASS — the required v197 anchor holds, so the v200 sweep is
a pure book-SL/TP experiment.

## v201 (v197 pipeline plus hourly ladder, shared stop-risk budget)

| row | monthly dev4 % | monthly 5y % | last-year monthly % | gate DD % | yearly nets % |
| --- | --- | --- | --- | --- | --- |
| reported ref_hourly_off | 5.562 | 4.996 | 2.761 | 19.72 | 40.67 / 51.32 / 147.63 / 154.98 / 38.66 |
| audit HOURLY_OFF | 5.562 | 4.996 | 2.761 | 19.72 | 40.67 / 51.32 / 147.63 / 154.98 / 38.66 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported hourly_on_b0.12 | 3.622 | 2.918 | 0.150 | 39.69 | 34.02 / -24.55 / 138.54 / 128.70 / 1.81 |
| audit HOURLY_012 | 3.622 | 2.918 | 0.150 | 39.69 | 34.02 / -24.55 / 138.54 / 128.70 / 1.81 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported hourly_on_b0.18 | 3.333 | 2.709 | 0.252 | 39.66 | 44.38 / -26.01 / 100.83 / 124.90 / 3.06 |
| audit HOURLY_018 | 3.333 | 2.709 | 0.252 | 39.66 | 44.38 / -26.01 / 100.83 / 124.90 / 3.06 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |

Yearly legs match in full (net/monthly/dd_1m/mean_g per anchor verified equal
as dicts); dd_4h/dd_1m match (off 19.07 / 19.72; b0.12 38.27 / 39.69;
b0.18 38.45 / 39.66).

Stats are bit-exact on every row (off 40078 / 4079 / 76 / 48 / 5004 / 191 /
2717 / 0 / 0.0968 / 0.1817; b0.12 32875 / 3341 / 67 / 41 / 22703 / 1125 / 11705 /
0 / 0.0756 / 0.1498; b0.18 32293 / 3261 / 67 / 43 / 23404 / 1207 / 12132 / 0 /
0.0714 / 0.1430; gross_sum/gross_max/bars equal too). Turning the hourly ladder
on adds ~17-18k rung takes (5004 -> 22703 / 23404, +934/+1016 rung stops,
+8988/+9415 rung TPs) while book fills drop (40078 -> 32875 / 32293) because the
governor de-risks on the hourly-driven drawdown (mean_g 2022 collapses
0.935 -> 0.554 / 0.518). The m_tp = None vs 8.0 spelling is proven immaterial by
the exact match. The driver reference assert
(v201_hourly_ladder_risk_budget.py:51 dev4 5.562 / DD 19.72) passes in the audit
too (HOURLY_OFF == v197 anchor and == A1 REF_4_8 bit-exact).

## Selection uses no last-year statistic

v200_user_tp_sl_range.py:54-58: cand = rows except ref; ok = rows with gate_dd
<= 20 and all yearly[:4] net_pct >= 0; pool = ok or cand; sel = max monthly_dev4
over pool; final_score_selected reports monthly_5y/monthly_last_year/losing_years/
gate_dd/gate_pass once for the winner. monthly_dev4 in
research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py is the
geometric mean of years[:4] only. The last-year monthly is reported, never ranked
on. PASS.

Eligibility note v200: all three pre-registered variants breach the DD gate
(A 21.28, B 24.75, C 24.41 > 20), so ok is empty and the driver correctly falls
back to pool = cand with winner A_sl2_tp4 (dev4 4.958 > 4.840 > 4.719). The audit
eligible_a1 = [REF_4_8] is the same rule including the non-selectable reference;
restricted to the selectable A/B/C the audit agrees ok is empty and the fallback
winner is SL2_TP4. Audit eligible_a1/selection_a1 (REF_4_8) maps to reported
selected A_sl2_tp4 under the documented reference-excluded rule; final score
selected is identical (5y 4.425 / last 2.319 / DD 21.28).

v201_hourly_ladder_risk_budget.py:52-54: ok = rows with gate_dd <= 20 and all
yearly[:4] net_pct >= 0; pool = ok or rows; sel = max monthly_dev4 over pool.
Only ref_hourly_off passes (hourly rows lose 2022 and breach DD 39.69 / 39.66),
so ok = {ref} and winner ref_hourly_off. Audit eligible_a2 [HOURLY_OFF],
selection_a2 HOURLY_OFF maps to reported selected ref_hourly_off; final score
selected is identical (5y 4.996 / last 2.761 / DD 19.72).

## Look-ahead check

engine_user.py plus the two drivers:

- Feature timing: target uses books[t], s[t], g[t] at the decision
  (engine_user.py:83-97, 104); sigma_d/sigma_4h are rolling windows ending at t
  (prepare sig4; sd = sig4*sqrt(6)), sigma_1h is the trailing-1440h std shifted so
  only hours ending with the last hour of the previous holding bar are known
  (engine_user.py:68-72, sig1h[1:] = sig_h[:-1, 3, :]); cubes row i is the holding
  bar T = t+4h (prepare via v172.cube_ohlc). Member books are causal inputs by
  construction; P2 = (A+B)/2 is an algebraic mix at bar t only. Book (SL, TP)
  multipliers and hourly rungs/budgets are pre-registered constants, none fit on
  any test year. PASS.
- Label windows: no forward return is read; PnL comes only from 1m fills,
  SL/TP exits during T, hourly exits at intrabar opens 60(h+1) or o2, and the
  T+4h exit/settlement prices. TP uses m_sleeve_tp = 1.0 and rung SL 5 on every
  row; hourly TP/SL use the rung's own sigma_1h. PASS.
- Fit windows: no statistic is fit on any test year in this path; vol and
  the governor are running causal filters (vol from books.shift(2) returns,
  governor from eq at i-2 over the trailing 540 bars); book grids
  ((2, 4), (2.5, 2.5), (3, 2), reference (4, 8)) and hourly budgets (off / 0.12 /
  0.18) were pre-registered for these directions (at most 3 selectable variants
  each), not tuned here; selections use first-four-years metrics only. PASS.
- Fill timing: book limit 10 bps better than minute-0, minutes 2..238 strict
  trade-through with expiry and no fallback (engine_user.py:117-124, d_limit /
  win_end per row); held SL/TP checked from minute 0 over [0, fill_min + 1) so a
  held stop wins a same-minute tie with the new fill and cancels the pending
  order, stop-first in one minute, flat afterwards (lines 131-169, 180-182);
  4h sleeve trigger minutes 16..238 strict with exits strictly after the fill
  minute in (minute, rung, asset) budget order (lines 196-203, 218-257); hourly
  bids 16..57 (h = 0) else 60h+4..60h+57 strict with exits strictly after the
  fill minute before 60(h+1) in (minute, 4h first, rung, asset) shared-budget
  order with per-rung sigma risk (lines 204-226); h = 3 market exit at the next
  4h open with funding only if that is a settlement (lines 245-248). PASS.

Fee/funding arithmetic: maker 0.0002 on book entries and TP, taker 0.00055
on stops/market exits, longs pay 0.0001 at 00/08/16 UTC settlements, shorts
zero, no carry (engine_user.py:34-36, funds in book/sleeve exits). This is
the AGENTS.md gate cost model. tests/test_engine_user.py covers limit fill
+ TP, stop through a gap (fills at minute open), unfilled-limit expiry, and
long funding at settlement on synthetic bars. PASS.

## Verdict

- Engineering REPRODUCED bit-exact on all seven rows (dev4/5y/last-year,
  gate DD, yearly legs, stats including gross exposure).
- v197 anchor CONFIRMED under the corrected engine twice: A1 REF_4_8 and A2
  HOURLY_OFF both equal 5.562 / 19.72 with identical nets/stats (40078 / 4079 /
  76 / 48 / 5004 / 191 / 2717 / 0 / 0.0968 / 0.1817); the m_tp None vs 8.0
  spelling is immaterial.
- Look-ahead PASS (decision-known features/sigma/scale/governor, no label
  or fit leakage, causal fill/stop/sleeve/hourly/budget timing, first-four-years
  selection only; grids and budgets pre-registered, not test-fit).
- Direction results: v200 closer book SL/TP lowers dev4 (5.562 -> 4.958 / 4.840 /
  4.719) and breaches the DD gate on every selectable variant (21.28 / 24.75 /
  24.41 > 20), so the fallback winner is A_sl2_tp4; v201 hourly ladder collapses
  dev4 (5.562 -> 3.622 / 3.333), adds a 2022 losing year (-24.55 / -26.01) and
  breaches DD (39.69 / 39.66), so the winner stays the reference (off).
- Gate: v200 selected A_sl2_tp4 fails (dev4 4.958 < 5, 5y 4.425 < 5, last 2.319
  < 5, DD 21.28 > 20; nets 35.75 / 38.78 / 138.78 / 126.82 / 31.67); v201
  selected ref_hourly_off is the v197 config and still fails the gate
  (5y 4.996 < 5 by 0.004, last 2.761 < 5; nets 40.67 / 51.32 / 147.63 / 154.98 /
  38.66; DD 19.72 passes). Manifests (status rejected, live_approved false,
  audit passed/replay_complete false awaiting audit) must stay non-live_approved.
