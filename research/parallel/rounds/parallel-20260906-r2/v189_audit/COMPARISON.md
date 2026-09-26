# v189 blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v189_audit/replication.json
was saved before opening v189/ (see Part A script header E1-E8/L1-L4).
Base: research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py
(the gate engine implementing the OPENCODE_V188_AUDIT.md spec from AGENTS.md
2026-09-27 user goal, gate cost model and current execution assumptions).
Leader files were not edited.

Reported: research/parallel/rounds/parallel-20260906-r2/v189/v189_result.json
from research/parallel/rounds/parallel-20260906-r2/v189/v189_pipeline_comparison.py.
Audit: rows key in
research/parallel/rounds/parallel-20260906-r2/v189_audit/replication.json
(P1 = A, P2 = (A+B)/2, P3 = (A+B+D)/3, each with and without the dip sleeve,
book SL/TP m = 4, sleeve SL 2 sigma_4h).

## Pipeline construction check

v189_pipeline_comparison.py:32-34 reindexes members A/B/D to the books154
index (missing -> 0.0) and asserts ((A+B+D)/3 - books154).abs().max() < 1e-9;
pipes are P1_v144 = A, P2_v151 = (A+B)/2, P3_v154 = books154; prep is built
once from books154/opens and simulate is called with m_sl = 4.0,
m_sleeve_sl = 2.0 per row. Audit builds P1/P2/P3 on the member union index
(missing -> 0.0) after checking (A+B+D)/3 == books_v154 exactly (max abs
diff 0.0, union bars 10950) and verifies P3 == books_v154 exactly (diff
0.0); shared 1m preparation is identical across pipelines (same idx/cols).
PASS (actual diff 0.0 satisfies both thresholds).

## v189 (pipelines under engine_user, m = 4)

| row | monthly dev4 % | monthly 5y % | last-year monthly % | gate DD % | yearly nets % |
| --- | --- | --- | --- | --- | --- |
| reported P1_v144 | 3.525 | 3.404 | 2.925 | 19.57 | 20.00 / 47.77 / 74.10 / 70.82 / 41.33 |
| audit P1_nosleeve | 3.525 | 3.404 | 2.925 | 19.57 | 20.00 / 47.77 / 74.10 / 70.82 / 41.33 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported P1_v144+sleeve | 3.718 | 3.544 | 2.849 | 19.68 | 24.43 / 47.57 / 85.90 / 68.98 / 40.09 |
| audit P1_sleeve | 3.718 | 3.544 | 2.849 | 19.68 | 24.43 / 47.57 / 85.90 / 68.98 / 40.09 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported P2_v151 | 3.677 | 3.428 | 2.435 | 19.03 | 18.74 / 51.77 / 74.30 / 80.20 / 33.47 |
| audit P2_nosleeve | 3.677 | 3.428 | 2.435 | 19.03 | 18.74 / 51.77 / 74.30 / 80.20 / 33.47 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported P2_v151+sleeve | 3.896 | 3.584 | 2.342 | 19.41 | 23.37 / 52.50 / 86.27 / 78.73 / 32.02 |
| audit P2_sleeve | 3.896 | 3.584 | 2.342 | 19.41 | 23.37 / 52.50 / 86.27 / 78.73 / 32.02 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported P3_v154 | 3.318 | 3.377 | 3.611 | 18.66 | 18.33 / 45.93 / 74.50 / 59.01 / 53.06 |
| audit P3_nosleeve | 3.318 | 3.377 | 3.611 | 18.66 | 18.33 / 45.93 / 74.50 / 59.01 / 53.06 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported P3_v154+sleeve | 3.529 | 3.533 | 3.549 | 19.03 | 22.92 / 45.81 / 86.04 / 58.48 / 51.96 |
| audit P3_sleeve | 3.529 | 3.533 | 3.549 | 19.03 | 22.92 / 45.81 / 86.04 / 58.48 / 51.96 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |

Stats are bit-exact on every row (fills/unfilled/stops/tps/rungs/rung_stops/
rung_tps/fees/funding, e.g. P2+sleeve 35288 / 8296 / 74 / 51 / 2571 / 432 /
1214 / 0.0960 / 0.1835; P3+sleeve 35882 / 8439 / 83 / 54 / 2545 / 426 / 1203).
dd_4h/dd_1m match (P2+sleeve 19.38 / 19.41). Sleeve adds about +0.19pp dev4
on P1, +0.22pp on P2, +0.21pp on P3.

## Selection uses no last-year statistic

v189_pipeline_comparison.py:44-46: eligible = rows with gate_dd <= 20 and
all yearly[:4] net_pct >= 0; selected = max monthly_dev4 over eligible;
final_score_selected reports monthly_5y/monthly_last_year/losing_years/
gate_dd/gate_pass once for the winner. monthly_dev4 in
research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py:267
is the geometric mean of years[:4] only. The last-year monthly (2.342 for
the winner) is reported, never ranked on. PASS.

Eligibility note: all six audit rows have gate_dd <= 20 and zero losing
years in the first four (in fact zero losing years overall), so the DD and
losing-year filters do not discriminate; the winner P2_v151+sleeve
(P2_sleeve, dev4 3.896) is the plain max-dev4 row. The last-year leader
(P3_v154+sleeve last 3.549) ranks only 4th on dev4 (3.529) and was not
selectable, consistent with the manifest note.

## Look-ahead check

engine_user.py plus the v189 driver:

- Feature timing: target uses books[t], s[t], g[t] at the decision
  (engine_user.py:89-98); sigma_d/sigma_4h are rolling windows ending at t
  (prepare sig4, line 99 sd = sig4*sqrt(6)); cubes row i is the holding bar
  T = t+4h (prepare via v172.cube_ohlc). Member books are causal inputs by
  construction; P1/P2/P3 are algebraic mixes at bar t only. PASS.
- Label windows: no forward return is read; PnL comes only from 1m fills,
  SL/TP exits during T, and the T+4h exit/settlement prices. PASS.
- Fit windows: no statistic is fit on any test year in this path; vol and
  the governor are running causal filters (vol from books.shift(2) returns,
  governor from eq at i-2 over the trailing 540 bars); m = 4 was
  pre-selected in v188 on the first four years, not here. PASS.
- Fill timing: book limit 10 bps, minutes 2..59 strict trade-through with
  expiry (engine_user.py:111-118); SL/TP checked from minute 0 on the held
  position and from the fill minute on the new position, stop-first in one
  minute, flat afterwards with the pending order cancelled (lines 125-176);
  sleeve trigger minutes 16..238 strict with exits strictly after the fill
  minute in (minute, rung, asset) budget order (lines 186-230). PASS.

Fee/funding arithmetic: maker 0.0002 on book entries and TP, taker 0.00055
on stops/market exits, longs pay 0.0001 at 00/08/16 UTC settlements, shorts
zero, no carry (engine_user.py:33-36,169-180, funds in sleeve exit). This is
the AGENTS.md gate cost model. tests/test_engine_user.py covers limit fill
+ TP, stop through a gap (fills at minute open), unfilled-limit expiry, and
long funding at settlement on synthetic bars. PASS.

## Verdict

- Engineering REPRODUCED bit-exact on all six rows (dev4/5y/last-year,
  gate DD, yearly nets, stats).
- Look-ahead PASS (decision-known features/sigma/scale/governor, no label
  or fit leakage, causal fill/stop/sleeve timing, first-four-years
  selection only).
- Gate: every row fails monthly >= 5% (best dev4 3.896 P2+sleeve, best 5y
  3.584, best last-year 3.611 P3 nosleeve) while passing DD <= 20% with no
  losing year. Selected P2_v151+sleeve final 5y 3.584 / last 2.342 / DD
  19.41 -> gate fails. Manifest (status rejected, live_approved false,
  audit passed/replay_complete false awaiting audit) must stay
  non-live_approved.
