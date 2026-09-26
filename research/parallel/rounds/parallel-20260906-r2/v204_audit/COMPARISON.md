# v204 blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v204_audit/replication.json
was saved before opening v204/ (see Part A script header E1-E8/L1-L4 and the
C1/C2 convention plus align-branch asserts). Base: research/parallel/rounds/parallel-20260906-r2/
engine_user/engine_user.py (the gate engine implementing the AGENTS.md 2026-09-27
user goal, gate cost model and current execution assumptions), with the two
conventions adopted from the v188 audit: (1) the 1m-marked DD uses peaks over the
minute path (intrabar highs count), (2) a stop on the held position wins a
same-minute tie with a new book fill (the pending order is cancelled). Leader
files were not edited.

Reported: research/parallel/rounds/parallel-20260906-r2/v204/v204_result.json
from research/parallel/rounds/parallel-20260906-r2/v204/v204_sleeve_book_alignment.py.
Audit: rows key in
research/parallel/rounds/parallel-20260906-r2/v204_audit/replication.json
(v197 pipeline v151 = (A+B)/2, books vol target 0.25, base per-rung notional
rn_base = s g 1.5 0.25/4/1.657 via size_mult = 1.5 on every row, directional
multiplier m = m_long if tgt > 0 else m_other with aligns (1, 1), (1.5, 0.5),
(2, 0), stop-risk budget X = 0.12 on every row summing each open rung own
notional * (5 sigma_4h + 0.02); book SL/TP m = 4, rung SL 5 sigma_4h,
TP L(1 + sigma_4h), book limit (d, W) = (0.001, 239), gap 0.02, cap 2.0;
ladder (2.5, 3, 3.5, 4) on every row; selection = robust criterion).

## Pipeline construction check

v204_sleeve_book_alignment.py:44-50 builds v151 = (A+B)/2 on the books154 index
(missing -> 0.0) but prepares with eu.prepare(books154, opens); the audit builds
P2 on the member union index (missing -> 0.0) after checking (A+B+D)/3 ==
books_v154 exactly (max abs diff 0.0, union bars 10950, same 5 majors columns)
and verifies P2 index/columns equal books_v154; shared 1m preparation is
identical for all rows (same idx/cols). As in the v193/v197/v198/v199 audits,
prepare uses books only for idx/cols while vol/s inside simulate is recomputed
from the books argument (P2 == v151), so the driver quirk is immaterial. PASS
(same books, same opens, same cubes). Driver passes sleeve_risk_budget = 0.12
and size_mult = 1.5 on every row (v204_sleeve_book_alignment.py:50) with
align = None / (1.5, 0.5) / (2.0, 0.0) per variant (line 28), and leaves target,
cap, gap and m_sleeve_tp at engine defaults; engine_user.py:71 target default
0.25, cap default 2.0, gap default 0.02, m_sleeve_tp default 1.0 match the audit
explicit TARGET = 0.25, CAP = 2.0, GAP = 0.02, TP mult 1.0. The directional rung
notional takes the align branch (engine_user.py:194 rn_base = s * g * size_mult
* 0.25/4/1.657 with the constant divisor 4, line 220 rn = rn_base * (align[0]
if tgt[a] > 0 else align[1]), rn <= 0 -> rung skipped), and the risk budget sums
each open rung own notional (engine_user.py:228 risk_open = sum(t[7] *
(m_sleeve_sl * t[6] + gap) for taken if still open), checked against X = 0.12)
— exactly the registered v204 design (per-rung size rn * m, budget over own
notionals). The reference align None and the audit ALIGN_11 (1, 1) are the same
path (rn_base * 1); the only code difference is the rn <= 0 skip, which binds on
no bar here (rung counts identical, see below). PASS — audit and driver run the
same engine with the same books, opens, sizes and budget.

Book direction known at the decision: tgt is computed at the top of the bar loop
from decision-known quantities only (engine_user.py:104 tgt = 0.8 * s[i] * B[i]
* g[i], with B = books at t, s[i] from the causal vol filter, g[i] from equity
at i-2), and the align branch reads tgt[a] at the fill loop for the same bar i
(engine_user.py:220). The sign of tgt[a] equals the sign of books[t, a] whenever
s[i] * g[i] > 0 (both non-negative by construction); when g[i] = 0 every tgt is
0 and the (m_long vs m_other) choice falls to m_other, still decision-known. No
forward price, return, sigma or fill outcome enters the direction. PASS.

## v204 (directional dip-sleeve size by book direction, own-notional budget)

| row | monthly dev4 % | worst first-4 yr %/mo | monthly 5y % | last-year monthly % | gate DD % | yearly nets % |
| --- | --- | --- | --- | --- | --- | --- |
| reported ref_1_1 | 5.562 | 2.885 | 4.996 | 2.761 | 19.72 | 40.67 / 51.32 / 147.63 / 154.98 / 38.66 |
| audit ALIGN_11 | 5.562 | 2.885 | 4.996 | 2.761 | 19.72 | 40.67 / 51.32 / 147.63 / 154.98 / 38.66 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported align_1.5_0.5 | 5.872 | 2.945 | 5.334 | 3.212 | 19.46 | 41.66 / 49.19 / 181.38 / 160.10 / 46.13 |
| audit ALIGN_150_05 | 5.872 | 2.945 | 5.334 | 3.212 | 19.46 | 41.66 / 49.19 / 181.38 / 160.10 / 46.13 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported align_2_0 | 5.767 | 2.661 | 5.215 | 3.035 | 20.55 | 37.04 / 40.15 / 204.48 / 152.23 / 43.16 |
| audit ALIGN_20 | 5.767 | 2.661 | 5.215 | 3.035 | 20.55 | 37.04 / 40.15 / 204.48 / 152.23 / 43.16 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |

Yearly legs match in full (net/monthly/dd_1m/mean_g per anchor verified equal
as dicts, not just nets; dd_4h matches too: ref 19.07, 1.5/0.5 17.99, 2/0 17.22).

Stats are bit-exact on every row including the full dict (fills/unfilled/stops/
tps/rungs/rung_stops/rung_tps/liq/fees/funding/gross_sum/gross_max/bars, e.g.
ref/ALIGN_11 40078 / 4079 / 76 / 48 / 5004 / 191 / 2717 / 0 / 0.0968 / 0.1817 /
5362.3762 / 2.291 / 10944; 1.5/0.5 40205 / 4094 / 75 / 49 / 5010 / 193 / 2706 /
0 / 0.0976 / 0.1833; 2/0 40092 / 4078 / 75 / 47 / 2421 / 71 / 1345 / 0 / 0.0981 /
0.1838). Tilting size toward book-long dips (1.5, 0.5) adds only +6 rung takes
(+2 rung stops, -11 rung TPs) while lifting dev4 (5.562 -> 5.872), worst-year
(2.885 -> 2.945) and 5y (4.996 -> 5.334) at lower DD (19.72 -> 19.46); the
long-only (2, 0) variant more than halves takes (5004 -> 2421, stops 191 -> 71,
TPs 2717 -> 1345) and breaches the DD gate (20.55 > 20).

Reference row re-scores v197 under the stricter engine exactly as the driver
asserts (v204_sleeve_book_alignment.py:59): ref nets/stats equal the v197
selected row P2_M150 and the v199 LADDER_4 row (nets 40.67 / 51.32 / 147.63 /
154.98 / 38.66; stats 40078 / 4079 / 76 / 48 / 5004 / 191 / 2717 / 0 / 0.0968 /
0.1817; DD 19.72). PASS — the required v197 anchor holds, so the v204 sweep is
a pure directional-size experiment.

## Selection uses no last-year statistic (robust criterion)

v204_sleeve_book_alignment.py:31-40: worst_month over yearly[:4] only; ok = rows
with gate_dd <= 20 and all yearly[:4] net_pct >= 0; pool = ok or rows; five =
pool rows with monthly_dev4 >= 5; pool = five or pool; sel = max (round(
worst_month, 4), monthly_dev4). monthly_dev4 in
research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py is the
geometric mean of years[:4] only. The last-year monthly (3.212 for the winner)
is reported in final_score_selected, never ranked on. PASS.

Eligibility note: align_2_0 (dev4 5.767) is correctly excluded by gate_dd 20.55
> 20, so ok = {ref_1_1, align_1.5_0.5}; both clear dev4 >= 5, so the robust pool
is both rows and the winner is the highest worst-year monthly: align_1.5_0.5
(2.945 > 2.885; tie-break dev4 5.872 > 5.562 also favors it). Audit eligible
[ALIGN_11, ALIGN_150_05], selection ALIGN_150_05 maps to reported selected
align_1.5_0.5; final score selected is identical (5y 5.334 / last 3.212 / DD
19.46). Here the robust pick coincides with the plain max-dev4 eligible pick.

## Look-ahead check

engine_user.py plus the v204 driver:

- Feature timing: target uses books[t], s[t], g[t] at the decision
  (engine_user.py:83-104); sigma_d/sigma_4h are rolling windows ending at t
  (prepare sig4; sd = sig4*sqrt(6)); cubes row i is the holding bar
  T = t+4h (prepare via v172.cube_ohlc). Member books are causal inputs by
  construction; P2 = (A+B)/2 is an algebraic mix at bar t only. The align
  multiplier reads tgt[a] at bar i only (line 220) — the book direction used
  is known at the decision (see check above); aligns ((1,1), (1.5,0.5),
  (2,0)) with fixed base size and X = 0.12 are pre-registered constants, none
  fit on any test year. PASS.
- Label windows: no forward return is read; PnL comes only from 1m fills,
  SL/TP exits during T, and the T+4h exit/settlement prices. TP uses
  m_sleeve_tp = 1.0 on all rows, SL at 5 sigma_4h unchanged. PASS.
- Fit windows: no statistic is fit on any test year in this path; vol and
  the governor are running causal filters (vol from books.shift(2) returns,
  governor from eq at i-2 over the trailing 540 bars); aligns were
  pre-registered for this direction (at most 3 variants), not tuned here;
  selection uses first-four-years metrics only (robust worst-year). PASS.
- Fill timing: book limit 10 bps better than minute-0, minutes 2..238 strict
  trade-through with expiry and no fallback (engine_user.py:117-124,
  d_limit/win_end per row); held SL/TP checked from minute 0 over
  [0, fill_min + 1) so a held stop wins a same-minute tie with the new fill
  and cancels the pending order, stop-first in one minute, flat afterwards
  (lines 165-182); sleeve trigger minutes 16..238 strict with exits strictly
  after the fill minute in (ladder, rung, asset) budget order with risk
  budget X = 0.12 per row summing own notionals and gap 0.02 (lines 194-260);
  sleeve SL uses m_sleeve_sl = 5 per row, rung notional rn_base * m on every
  row with m = 0 skipping the rung. PASS.

Fee/funding arithmetic: maker 0.0002 on book entries and TP, taker 0.00055
on stops/market exits, longs pay 0.0001 at 00/08/16 UTC settlements, shorts
zero, no carry (engine_user.py:33-36, funds in sleeve exit). This is
the AGENTS.md gate cost model. tests/test_engine_user.py covers limit fill
+ TP, stop through a gap (fills at minute open), unfilled-limit expiry, and
long funding at settlement on synthetic bars. PASS.

## Verdict

- Engineering REPRODUCED bit-exact on all three rows (dev4/worst/5y/last-year,
  gate DD, yearly legs, full stats dicts).
- v197 anchor CONFIRMED: reference nets/stats/DD exact under the corrected
  engine (C1 minute-path peaks, C2 stop-wins-tie).
- Book direction PASS: the align multiplier uses the decision-known target
  book weight sign only (engine_user.py:104 computed, line 220 read).
- Look-ahead PASS (decision-known features/sigma/scale/governor/direction, no
  label or fit leakage, causal fill/stop/sleeve/budget timing, first-four-years
  robust selection only; aligns/size/budget pre-registered, not test-fit).
- Direction result: aligning dip size with the book direction improves the
  first four years on both mean and worst-year (dev4 5.562 -> 5.872, worst 2.885
  -> 2.945) at lower DD (19.72 -> 19.46); long-only (2, 0) reaches dev4 5.767 /
  5y 5.215 but is correctly excluded by DD 20.55 > 20. Selected =
  align_1.5_0.5.
- Gate: selected align_1.5_0.5 clears the 5-year mean (5.334 >= 5) with DD 19.46
  <= 20 and no losing year, but the gate still fails: the most recent year
  3.212 < 5 (nets 41.66 / 49.19 / 181.38 / 160.10 / 46.13). Manifest (status
  rejected, live_approved false, audit passed/replay_complete false awaiting
  audit) must stay non-live_approved.
