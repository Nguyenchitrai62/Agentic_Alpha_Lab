# v205 blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v205_audit/replication.json
was saved before opening v205/ (see Part A script header E1-E8/L1-L4 and the
C1/C2 convention asserts). Base: research/parallel/rounds/parallel-20260906-r2/
engine_user/engine_user.py (the gate engine implementing the AGENTS.md 2026-09-27
user goal, gate cost model and current execution assumptions), with the two
conventions adopted from the v188 audit: (1) the 1m-marked DD uses peaks over the
minute path (intrabar highs count), (2) a stop on the held position wins a
same-minute tie with a new book fill (the pending order is cancelled), plus the
v204 align branch (directional rung sizing on decision-known tgt). Leader
files were not edited.

Reported: research/parallel/rounds/parallel-20260906-r2/v205/v205_result.json
from research/parallel/rounds/parallel-20260906-r2/v205/v205_ensemble_books_aligned_sleeve.py.
Audit: rows key in
research/parallel/rounds/parallel-20260906-r2/v205_audit/replication.json
(books = 0.5 (A+B)/2 annual + 0.5 (Aq+Bq)/2 quarterly, both legs reindexed to
books_v154 with missing -> 0, sleeve aligned with the book direction m_long 1.5 /
m_other 0.5 on top of the x1.5 rung size, under the v204 rules: book SL/TP m = 4,
rung SL 5 sigma_4h, TP L(1 + sigma_4h), book limit (d, W) = (0.001, 239),
target 0.25, cap 2.0, gap 0.02, size_mult 1.5, stop-risk budget X = 0.12, rungs
(2.5, 3, 3.5, 4)).

## Pipeline construction check

v205_ensemble_books_aligned_sleeve.py:32-38 loads books154/opens via eu.er.v154_books,
takes A/B from members_v154.parquet and Aq/Bq from members_quarterly.parquet, each
reindexed to the books154 index with fillna 0.0 and the books154 columns, then
annual = (A+B)/2, quarterly = (Aq+Bq)/2; the audit does the same reindex/column
selection explicitly and verifies the blend identity (max abs diff of blend vs
(annual+quarterly)/2 is 0.0, books index length 10950, same 5 majors columns).
Quarterly cache has 6 extra bars absent from books_v154; both driver and audit drop
them by the reindex (audit logs extra dropped = 6, missing filled 0 = 0). PASS
(same books, same opens, same cubes).

Both paths share one preparation: eu.prepare(books154, opens) for idx/cols plus
the 1m cube/sigma/settlement arrays (v205_ensemble_books_aligned_sleeve.py:39; audit
prep on books154). As in the v199/v202/v203/v204 audits, prepare uses books only
for idx/cols while vol/s inside simulate is recomputed from the books argument, so
the shared prep is identical for both rows. Driver kw (line 40) is m_sl = 4.0,
m_sleeve_sl = 5.0, sleeve True, d_limit = 0.001, win_end = 239,
sleeve_risk_budget = 0.12, size_mult = 1.5, align = (1.5, 0.5) with engine defaults
target 0.25, cap 2.0, gap 0.02, m_sleeve_tp 1.0, rungs (2.5, 3, 3.5, 4); the audit
passes the same values explicitly (M_SL 4.0, M_SLEEVE_SL 5.0, TP mult 1.0,
TARGET 0.25, CAP 2.0, GAP 0.02, SIZE_MULT 1.5, X 0.12, RUNGS (2.5, 3, 3.5, 4),
ALIGN (1.5, 0.5)). The per-rung notional takes the size_mult branch with the
align multiplier (engine_user.py:194 rn_base then line 220
rn = rn_base * (align[0] if tgt[a] > 0 else align[1]), m = 0 skipped), identical on
both rows — the registered v205 design (ensemble books + aligned sleeve, no new
size parameter). PASS.

Conventions C1/C2 plus the align branch are present in the engine and asserted by
the audit script (inspect of eu.simulate / eu.summarize): seg_end = fill_min + 1,
i.e. the held position is checked over [0, fill_min + 1) with fill cancellation on
a held stop/TP at or before the fill minute (engine_user.py:165-169); simulate
tracks eq_max per bar (line 261) and summarize peaks over maximum(e, ex) with
troughs over minimum(e, em) (lines 289, 293, 299-301); align reads tgt[a] computed
at the decision (lines 104, 220). PASS — audit and driver run the same corrected
engine.

## v205 (v204 annual reference vs annual+quarterly ensemble, both with aligned sleeve)

| row | monthly dev4 % | worst first-four monthly % | monthly 5y % | last-year monthly % | gate DD % | yearly nets % |
| --- | --- | --- | --- | --- | --- | --- |
| reported ref_v204_annual | 5.872 | 2.945 | 5.334 | 3.212 | 19.46 | 41.66 / 49.19 / 181.38 / 160.10 / 46.13 |
| audit REF_ANNUAL | 5.872 | 2.945 | 5.334 | 3.212 | 19.46 | 41.66 / 49.19 / 181.38 / 160.10 / 46.13 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported ensemble_annual_quarterly | 5.824 | 3.410 | 5.488 | 4.152 | 19.76 | 49.54 / 54.51 / 147.19 / 165.05 / 62.93 |
| audit BLEND_50_50 | 5.824 | 3.410 | 5.488 | 4.152 | 19.76 | 49.54 / 54.51 / 147.19 / 165.05 / 62.93 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |

Yearly legs match in full (net/monthly/dd_1m/mean_g per anchor verified equal
as dicts, not just nets; yearly monthly legs ref 2.945 / 3.390 / 9.004 / 8.292 /
3.212 and ensemble 3.410 / 3.692 / 7.833 / 8.462 / 4.152; yearly 1m DDs ref 19.46 /
17.42 / 16.55 / 9.55 / 15.83 and ensemble 19.51 / 17.93 / 19.76 / 9.94 / 15.89).

Stats are bit-exact on both rows (fills/unfilled/stops/tps/rungs/rung_stops/
rung_tps/liq/fees/funding/gross_sum/gross_max/bars, e.g. ref/REF_ANNUAL 40205 /
4094 / 75 / 49 / 5010 / 193 / 2706 / 0 / 0.0976 / 0.1833 / 5412.4424 / 2.291 /
10944; ensemble/BLEND_50_50 41670 / 4256 / 85 / 52 / 4999 / 187 / 2702 / 0 /
0.0959 / 0.1812 / 5345.2583 / 2.3084 / 10944). dd_4h/dd_1m match (ref 17.99 /
19.46; ensemble 16.88 / 19.76). The blend adds +1465 book fills (+10 stops,
+3 TPs) while rung takes are flat (5010 -> 4999, -6 stops, -4 TPs), and cuts
dd_4h (17.99 -> 16.88) with gate DD set by the 1m leg on both rows.

Reference row re-anchors v204 under the corrected engine exactly:
REF_ANNUAL nets/stats equal the v204 ALIGN_150_05 row (nets 41.66 / 49.19 /
181.38 / 160.10 / 46.13; stats 40205 / 4094 / 75 / 49 / 5010 / 193 / 2706 / 0),
and the driver asserts this anchor (v205_ensemble_books_aligned_sleeve.py:49
abs dev4 - 5.872 < 0.002). PASS — the v205 sweep is a pure book-ensemble
experiment on the frozen aligned sleeve.

## Selection uses no last-year statistic

v205_ensemble_books_aligned_sleeve.py:50-55: sel = v204.robust_select(rows);
final_score_selected reports monthly_5y/monthly_last_year/losing_years/gate_dd/
gate_pass once for the winner. v204.robust_select (v204_sleeve_book_alignment.py:
35-40): ok = rows with gate_dd <= 20 and all yearly[:4] net_pct >= 0; pool = ok or
rows; five = pool with monthly_dev4 >= 5; pool = five or pool; winner = max by
(round(worst_month, 4), monthly_dev4) where worst_month is the min over yearly[:4]
only. monthly_dev4 in research/parallel/rounds/parallel-20260906-r2/engine_user/
engine_user.py is the geometric mean of years[:4] only. The last-year monthly
(4.152 for the winner) is reported, never ranked on. PASS.

Eligibility note: both rows pass the gate filter (ref DD 19.46, ensemble DD 19.76,
no losing year in the first four; both dev4 >= 5), so ok = both rows and five =
both rows; the winner ensemble_annual_quarterly has the higher worst first-four
monthly (3.410 > 2.945) despite the lower mean (5.824 < 5.872) — exactly the
robust criterion. Audit eligible [BLEND_50_50, REF_ANNUAL], selection BLEND_50_50
maps to reported selected ensemble_annual_quarterly; final score selected is
identical (5y 5.488 / last 4.152 / DD 19.76).

## Look-ahead check

engine_user.py plus the v205 driver:

- Feature timing: target uses books[t], s[t], g[t] at the decision
  (engine_user.py:104); sigma_d/sigma_4h are rolling windows ending at t
  (prepare sig4; sd = sig4*sqrt(6)); cubes row i is the holding bar
  T = t+4h (prepare via v172.cube_ohlc). The align multiplier uses tgt[a] =
  0.8 s B[t] g at the decision only (engine_user.py:104 computed at i, read at
  line 220 tgt[a] > 0), so the book direction used is known at the decision —
  the v204 assignment question is answered in code. Member books are causal
  inputs by construction (annual members per-anchor yearly retrain, quarterly
  members per-quarter retrain with per-target cutoffs = anchor - embargo as
  audited in v92/v94/v103/v129); the 50/50 average is an algebraic mix at bar t
  only, and the quarterly leg is reindexed to the annual books index (extra bars
  dropped, no forward fill). The blend weight 0.5/0.5, size_mult 1.5, align
  (1.5, 0.5) with budget X = 0.12 are pre-registered constants, none fit on any
  test year. PASS.
- Label windows: no forward return is read; PnL comes only from 1m fills,
  SL/TP exits during T, and the T+4h exit/settlement prices. TP uses
  m_sleeve_tp = 1.0 on both rows, SL at 5 sigma_4h unchanged. PASS.
- Fit windows: no statistic is fit on any test year in this path; vol and
  the governor are running causal filters (vol from books.shift(2) returns,
  governor from eq at i-2 over the trailing 540 bars); the ensemble weight and
  the align pair were pre-registered for this direction (at most 2 variants),
  not tuned here; selection uses first-four-years metrics only. Quarterly
  retraining itself was the v202 direction and is a cached input here, not
  refit. PASS.
- Fill timing: book limit 10 bps better than minute-0, minutes 2..238 strict
  trade-through with expiry and no fallback (engine_user.py:117-124,
  d_limit/win_end per row); held SL/TP checked from minute 0 over
  [0, fill_min + 1) so a held stop wins a same-minute tie with the new fill
  and cancels the pending order, stop-first in one minute, flat afterwards
  (lines 165-190); sleeve trigger minutes 16..238 strict with exits strictly
  after the fill minute in (minute, rung, asset) budget order with risk
  budget X = 0.12 per row and gap 0.02 (lines 194-257); sleeve SL uses
  m_sleeve_sl = 5 on both rows, per-rung notional rn = rn_base * m with rn_base
  = s * g * 1.5 * 0.25/4/1.657 and m = 1.5 if tgt > 0 else 0.5 on both rows,
  risk per open rung = own rn * (5 sigma_4h + 0.02). PASS.

Fee/funding arithmetic: maker 0.0002 on book entries and TP, taker 0.00055
on stops/market exits, longs pay 0.0001 at 00/08/16 UTC settlements, shorts
zero, no carry (engine_user.py:34-36, funds in book/sleeve exits). This is
the AGENTS.md gate cost model. tests/test_engine_user.py covers limit fill
+ TP, stop through a gap (fills at minute open), unfilled-limit expiry, and
long funding at settlement on synthetic bars. PASS.

## Verdict

- Engineering REPRODUCED bit-exact on both rows (dev4/worst-first-four/5y/
  last-year, gate DD, yearly legs, stats).
- v204 anchor CONFIRMED: reference nets/stats exact vs v204 ALIGN_150_05, so the
  v205 sweep is a pure book-ensemble experiment on the frozen aligned sleeve.
- Look-ahead PASS (decision-known features/sigma/scale/governor plus
  decision-known tgt direction for the align multiplier, no label or fit
  leakage, causal fill/stop/sleeve/budget timing, first-four-years selection
  only; 50/50 weight/size/align/budget pre-registered, not test-fit).
- Direction result: the 50/50 annual+quarterly ensemble with the aligned sleeve
  lowers dev4 (5.872 -> 5.824) but raises the worst first-four monthly
  (2.945 -> 3.410), 5y (5.334 -> 5.488) and the most recent year (3.212 ->
  4.152) at DD 19.76 (still <= 20, no losing year); under the registered robust
  criterion the winner flips from the annual reference (v203 max-mean rule) to
  the ensemble.
- Gate: selected ensemble_annual_quarterly/BLEND_50_50 passes dev4 (5.824 >= 5),
  5y (5.488 >= 5), no losing year and DD (19.76 <= 20) but the gate still fails:
  the most recent year 4.152 < 5 (nets 49.54 / 54.51 / 147.19 / 165.05 / 62.93).
  The reference also fails the gate (5y 5.334 >= 5 but last year 3.212 < 5).
  Manifest (status rejected, live_approved false, audit passed/replay_complete
  false awaiting audit) must stay non-live_approved.
