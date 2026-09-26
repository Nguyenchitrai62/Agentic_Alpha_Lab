# v203 blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v203_audit/replication.json
was saved before opening v203/ (see Part A script header E1-E8/L1-L4 and the
C1/C2 convention asserts). Base: research/parallel/rounds/parallel-20260906-r2/
engine_user/engine_user.py (the gate engine implementing the AGENTS.md 2026-09-27
user goal, gate cost model and current execution assumptions), with the two
conventions adopted from the v188 audit: (1) the 1m-marked DD uses peaks over the
minute path (intrabar highs count), (2) a stop on the held position wins a
same-minute tie with a new book fill (the pending order is cancelled). Leader
files were not edited.

Reported: research/parallel/rounds/parallel-20260906-r2/v203/v203_result.json
from research/parallel/rounds/parallel-20260906-r2/v203/v203_retrain_ensemble.py.
Audit: rows key in
research/parallel/rounds/parallel-20260906-r2/v203_audit/replication.json
(books = 0.5 (A+B)/2 annual + 0.5 (Aq+Bq)/2 quarterly, both legs reindexed to
books_v154 with missing -> 0, under the v197 rules: book SL/TP m = 4, rung SL 5
sigma_4h, TP L(1 + sigma_4h), book limit (d, W) = (0.001, 239), target 0.25,
cap 2.0, gap 0.02, size_mult 1.5, stop-risk budget X = 0.12, rungs
(2.5, 3, 3.5, 4)).

## Pipeline construction check

v203_retrain_ensemble.py:30-36 loads books154/opens via eu.er.v154_books, takes
A/B from members_v154.parquet and Aq/Bq from members_quarterly.parquet, each
reindexed to the books154 index with fillna 0.0 and the books154 columns, then
annual = (A+B)/2, quarterly = (Aq+Bq)/2; the audit does the same reindex/column
selection explicitly and verifies the blend identity (max abs diff of blend vs
(annual+quarterly)/2 is 0.0, books index length 10950, same 5 majors columns).
Quarterly cache has 6 extra bars on 2024-09-23 absent from books_v154; both
driver and audit drop them by the reindex (audit logs extra dropped = 6,
missing filled 0 = 0). PASS (same books, same opens, same cubes).

Both paths share one preparation: eu.prepare(books154, opens) for idx/cols plus
the 1m cube/sigma/settlement arrays (v203_retrain_ensemble.py:37; audit prep on
books154). As in the v199/v202 audits, prepare uses books only for idx/cols
while vol/s inside simulate is recomputed from the books argument, so the shared
prep is identical for both rows. Driver kw (line 38) is m_sl = 4.0,
m_sleeve_sl = 5.0, sleeve True, d_limit = 0.001, win_end = 239,
sleeve_risk_budget = 0.12, size_mult = 1.5 with engine defaults target 0.25,
cap 2.0, gap 0.02, m_sleeve_tp 1.0, rungs (2.5, 3, 3.5, 4); the audit passes the
same values explicitly (M_SL 4.0, M_SLEEVE_SL 5.0, TP mult 1.0, TARGET 0.25,
CAP 2.0, GAP 0.02, SIZE_MULT 1.5, X 0.12, RUNGS (2.5, 3, 3.5, 4)). The fixed
per-rung notional takes the size_mult branch (engine_user.py:194
rn = s * g * size_mult * 0.25/4/1.657 with the constant divisor 4), identical on
both rows — the registered v203 design (ensemble averages model schedules, no
new size parameter). PASS.

Conventions C1/C2 are present in the engine and asserted by the audit script
(inspect of eu.simulate / eu.summarize): seg_end = fill_min + 1, i.e. the held
position is checked over [0, fill_min + 1) with fill cancellation on a held
stop/TP at or before the fill minute (engine_user.py:165-169); simulate tracks
eq_max per bar (line 261) and summarize peaks over maximum(e, ex) with troughs
over minimum(e, em) (lines 289, 295-297). PASS — audit and driver run the same
corrected engine.

## v203 (annual reference vs 50/50 annual+quarterly ensemble, v197 rules)

| row | monthly dev4 % | monthly 5y % | last-year monthly % | gate DD % | yearly nets % |
| --- | --- | --- | --- | --- | --- |
| reported ref_annual_v151 | 5.562 | 4.996 | 2.761 | 19.72 | 40.67 / 51.32 / 147.63 / 154.98 / 38.66 |
| audit REF_ANNUAL | 5.562 | 4.996 | 2.761 | 19.72 | 40.67 / 51.32 / 147.63 / 154.98 / 38.66 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported ensemble_annual_quarterly | 5.516 | 5.170 | 3.795 | 19.86 | 47.06 / 61.03 / 116.87 / 156.28 / 56.36 |
| audit BLEND_50_50 | 5.516 | 5.170 | 3.795 | 19.86 | 47.06 / 61.03 / 116.87 / 156.28 / 56.36 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |

Yearly legs match in full (net/monthly/dd_1m/mean_g per anchor verified equal
as dicts, not just nets).

Stats are bit-exact on both rows (fills/unfilled/stops/tps/rungs/rung_stops/
rung_tps/liq/fees/funding/gross_sum/gross_max/bars, e.g. ref/REF_ANNUAL 40078 /
4079 / 76 / 48 / 5004 / 191 / 2717 / 0 / 0.0968 / 0.1817 / 5362.3762 / 2.291 /
10944; ensemble/BLEND_50_50 41501 / 4238 / 85 / 51 / 5003 / 192 / 2714 / 0 /
0.0951 / 0.1804 / 5306.0254 / 2.3084 / 10944). dd_4h/dd_1m match (ref 19.07 /
19.72; ensemble 17.74 / 19.86). The blend adds +1423 book fills (+9 stops,
+3 TPs) while rung takes are flat (5004 -> 5003, +1 stop, -3 TPs), and cuts
dd_4h (19.07 -> 17.74) with gate DD set by the 1m leg on both rows.

Reference row re-anchors v197/v199/v202 under the corrected engine exactly:
REF_ANNUAL nets/stats equal the v199 LADDER_4 row and the v202 ref_annual_v151
row (nets 40.67 / 51.32 / 147.63 / 154.98 / 38.66; stats 40078 / 4079 / 76 /
48 / 5004 / 191 / 2717 / 0). PASS — the v203 sweep is a pure ensemble-weight
experiment on frozen books.

## Selection uses no last-year statistic

v203_retrain_ensemble.py:44-46: ok = rows with gate_dd <= 20 and all
yearly[:4] net_pct >= 0; pool = ok or all rows; sel = max monthly_dev4 over
pool; final_score_selected reports monthly_5y/monthly_last_year/losing_years/
gate_dd/gate_pass once for the winner. monthly_dev4 in
research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py is the
geometric mean of years[:4] only. The last-year monthly (2.761 for the winner)
is reported, never ranked on. PASS.

Eligibility note: both rows pass the gate filter (ref DD 19.72, ensemble DD
19.86, no losing year in the first four), so ok = both rows; the winner
ref_annual_v151 (dev4 5.562 > 5.516) is the plain max-dev4 eligible row. Audit
eligible [BLEND_50_50, REF_ANNUAL], selection REF_ANNUAL maps to reported
selected ref_annual_v151; final score selected is identical (5y 4.996 /
last 2.761 / DD 19.72).

## Look-ahead check

engine_user.py plus the v203 driver:

- Feature timing: target uses books[t], s[t], g[t] at the decision
  (engine_user.py:104); sigma_d/sigma_4h are rolling windows ending at t
  (prepare sig4; sd = sig4*sqrt(6)); cubes row i is the holding bar
  T = t+4h (prepare via v172.cube_ohlc). Member books are causal inputs by
  construction (annual members per-anchor yearly retrain, quarterly members
  per-quarter retrain with per-target cutoffs = anchor - embargo as audited in
  v92/v94/v103/v129); the 50/50 average is an algebraic mix at bar t only, and
  the quarterly leg is reindexed to the annual books index (extra 2024-09-23
  bars dropped, no forward fill). The blend weight 0.5/0.5 and size_mult 1.5
  with budget X = 0.12 are pre-registered constants, none fit on any test
  year. PASS.
- Label windows: no forward return is read; PnL comes only from 1m fills,
  SL/TP exits during T, and the T+4h exit/settlement prices. TP uses
  m_sleeve_tp = 1.0 on both rows, SL at 5 sigma_4h unchanged. PASS.
- Fit windows: no statistic is fit on any test year in this path; vol and
  the governor are running causal filters (vol from books.shift(2) returns,
  governor from eq at i-2 over the trailing 540 bars); the ensemble weight
  was pre-registered for this direction (at most 2 variants), not tuned
  here; selection uses first-four-years metrics only. Quarterly retraining
  itself was the v202 direction and is a cached input here, not refit. PASS.
- Fill timing: book limit 10 bps better than minute-0, minutes 2..238 strict
  trade-through with expiry and no fallback (engine_user.py:117-124,
  d_limit/win_end per row); held SL/TP checked from minute 0 over
  [0, fill_min + 1) so a held stop wins a same-minute tie with the new fill
  and cancels the pending order, stop-first in one minute, flat afterwards
  (lines 165-190); sleeve trigger minutes 16..238 strict with exits strictly
  after the fill minute in (minute, rung, asset) budget order with risk
  budget X = 0.12 per row and gap 0.02 (lines 194-257); sleeve SL uses
  m_sleeve_sl = 5 on both rows, rung notional rn = s * g * 1.5 * 0.25/4/1.657
  on both rows. PASS.

Fee/funding arithmetic: maker 0.0002 on book entries and TP, taker 0.00055
on stops/market exits, longs pay 0.0001 at 00/08/16 UTC settlements, shorts
zero, no carry (engine_user.py:34-36, funds in book/sleeve exits). This is
the AGENTS.md gate cost model. tests/test_engine_user.py covers limit fill
+ TP, stop through a gap (fills at minute open), unfilled-limit expiry, and
long funding at settlement on synthetic bars. PASS.

## Verdict

- Engineering REPRODUCED bit-exact on both rows (dev4/5y/last-year,
  gate DD, yearly legs, stats).
- v197 anchor CONFIRMED: reference nets/stats exact vs v199 LADDER_4 and v202
  ref_annual_v151, so the v203 sweep is a pure ensemble experiment.
- Look-ahead PASS (decision-known features/sigma/scale/governor, no label
  or fit leakage, causal fill/stop/sleeve/budget timing, first-four-years
  selection only; 50/50 weight/size/budget pre-registered, not test-fit).
- Direction result: the 50/50 annual+quarterly ensemble lowers dev4 (5.562 ->
  5.516) but raises 5y (4.996 -> 5.170) and the most recent year (2.761 ->
  3.795) at DD 19.86 (still <= 20, no losing year); under the registered
  first-four-years rule the winner stays the annual reference.
- Gate: selected ref_annual_v151/REF_ANNUAL is the best dev4 under the DD gate
  (dev4 5.562 >= 5, DD 19.72 <= 20, no losing year) but the gate still fails:
  5y 4.996 < 5 and the most recent year 2.761 < 5 (nets 40.67 / 51.32 /
  147.63 / 154.98 / 38.66). The ensemble also fails the gate (5y 5.170 >= 5
  but last year 3.795 < 5). Manifest (status rejected, live_approved false,
  audit passed/replay_complete false awaiting audit) must stay
  non-live_approved.
