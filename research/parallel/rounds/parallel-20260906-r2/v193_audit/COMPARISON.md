# v193 blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v193_audit/replication.json
was saved before opening v193/ (see Part A script header E1-E8/L1-L4).
Base: research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py
(the gate engine implementing the AGENTS.md 2026-09-27 user goal, gate cost model
and current execution assumptions). Leader files were not edited.

Reported: research/parallel/rounds/parallel-20260906-r2/v193/v193_result.json
from research/parallel/rounds/parallel-20260906-r2/v193/v193_sleeve_risk_budget.py.
Audit: rows key in
research/parallel/rounds/parallel-20260906-r2/v193_audit/replication.json
(P2 = (A+B)/2 with the dip sleeve, rung stop 5 sigma_4h, TP L(1 + sigma_4h),
book SL/TP m = 4, book limit (d, W) = (0.001, 239), sleeve risk budget
X in (0.03, 0.05, 0.08) with gap 0.02).
Adversarial diagnostics:
research/parallel/rounds/parallel-20260906-r2/v193_audit/analysis.json
from research/parallel/rounds/parallel-20260906-r2/v193_audit/analyze_v193.py
(line-exact instrumented copy of engine_user.simulate; reproduces the blind
replication stats exactly before reporting diagnostics).

## Pipeline construction check

v193_sleeve_risk_budget.py:36-38 builds v151 = (A+B)/2 on the books154 index
(missing -> 0.0) but prepares with eu.prepare(books154, opens); the audit builds
P2 on the member union index (missing -> 0.0) and prepares with eu.prepare(P2,
opens). P2 vs driver v151 max abs diff = 0.0 (union bars 10950, same 5 majors
columns), and prepare(P2) vs prepare(books154) is bit-identical on O/H/L/C,
sig4, o1, o2 and settlement flags (nan-aware equality; the earlier naive
NaN != NaN comparison was fixed in analyze_v193.py). prepare uses books only
for idx/cols while vol/s inside simulate is recomputed from the books argument
(P2 == v151), so the driver quirk is immaterial. PASS (same books, same opens,
same cubes). Driver gap defaults to 0.02 (engine_user.py:71), matching the
audit's explicit gap = 0.02.

## v193 (P2+sleeve risk-budget X under engine_user, book m = 4, limit 10bps/239)

| row | monthly dev4 % | monthly 5y % | last-year monthly % | gate DD % | yearly nets % |
| --- | --- | --- | --- | --- | --- |
| reported 0.03 | 4.385 | 4.046 | 2.704 | 19.60 | 26.59 / 47.20 / 103.11 / 107.26 / 37.74 |
| audit P2_X030 | 4.385 | 4.046 | 2.704 | 19.60 | 26.59 / 47.20 / 103.11 / 107.26 / 37.74 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported 0.05 | 4.747 | 4.324 | 2.653 | 20.10 | 30.54 / 52.17 / 114.89 / 116.98 / 36.92 |
| audit P2_X050 | 4.747 | 4.324 | 2.653 | 20.10 | 30.54 / 52.17 / 114.89 / 116.98 / 36.92 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported 0.08 | 5.046 | 4.603 | 2.847 | 19.33 | 34.58 / 54.37 / 122.74 / 129.58 / 40.05 |
| audit P2_X080 | 5.046 | 4.603 | 2.847 | 19.33 | 34.58 / 54.37 / 122.74 / 129.58 / 40.05 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |

Stats are bit-exact on every row (fills/unfilled/stops/tps/rungs/rung_stops/
rung_tps/liq/fees/funding, e.g. X030 39469 / 4009 / 76 / 50 / 3663 / 127 /
1886 / 0 / 0.0982 / 0.1843; X050 39670 / 4044 / 75 / 49 / 4505 / 163 / 2380 /
0 / 0.0981 / 0.1842; X080 39882 / 4063 / 76 / 49 / 5001 / 191 / 2714 / 0 /
0.0980 / 0.1844). dd_4h/dd_1m match (X030 19.49 / 19.60; X050 19.91 / 20.10;
X080 19.13 / 19.33). Larger X -> more rungs taken (3663 < 4505 < 5001); book
fills drift slightly with X (39469 -> 39670 -> 39882) only through the
equity-linked min-notional filter (order intent is price-triggered; the skip
threshold scales with prev_eq), reproduced bit-exact.

## Selection uses no last-year statistic

v193_sleeve_risk_budget.py:45-47: ok = rows with gate_dd <= 20 and all
yearly[:4] net_pct >= 0; pool = ok or all rows; sel = max monthly_dev4 over
pool; final_score_selected reports monthly_5y/monthly_last_year/losing_years/
gate_dd/gate_pass once for the winner. monthly_dev4 in engine_user.py:267-268
is the geometric mean of years[:4] only. The last-year monthly (2.847 for the
winner) is reported, never ranked on. PASS.

Eligibility note: X050 (dev4 4.747) is correctly excluded by gate_dd 20.10 >
20, so ok = {0.03, 0.08}; the winner 0.08 (dev4 5.046) is the plain max-dev4
eligible row. Audit eligible [P2_X030, P2_X080], selection P2_X080 matches
reported selected 0.08.

## Adversarial checks

(1) Budget uses only exits already happened: engine_user.py:204-207 computes
risk_open over taken rungs with exit minute x > f, where x is the full-scan
SL/TP exit (or 240). The instrumented re-derivation checks, for all 5163
sleeve candidates per X row, the causal predicate "no SL/TP hit in
(f_prev+1 .. f)" by scanning only 1m prices up to the decision minute f, and
compares it with the engine predicate x > f. Mismatches: 0 for X = 0.03 and 0
for X = 0.08. The full-scan exit is only a compact encoding of the same
already-observed prefix (an exit at or before f would already have printed on
the 1m tape; same-minute fills cannot exit before f+1). PASS — no lookahead.

(2) Gap fills at the stop: book stops filled at min(SL, minute open) (long) /
max(SL, minute open) (short): 0 gap fills on both X = 0.03 and X = 0.08 — every
book stop filled exactly at the stop. Sleeve rung stops filled at min(SL,
minute open): X030 2 gaps, X080 7 gaps; max gap 3.62% of L on both rows; total
equity drag 0.00231 (X030) / 0.00620 (X080) of starting equity summed over the
full 5-year path, max single-gap drag 0.00175. The 2% gap allowance in the
budget (rn * (5 sigma_4h + 0.02)) therefore covers the observed gap scale with
margin; gap slippage does not move any headline number.

(3) Largest 1m-marked intrabar drawdown bars (X = 0.08; path_min = start-equity
fraction at the worst minute, with book/sleeve split at that minute):
2025-09-25 12:00 -0.08233 (book -0.07581, sleeve -0.00652, bar net -0.04639);
2024-03-05 12:00 -0.07999 (book -0.08689, sleeve +0.00690, net -0.06533);
2023-12-10 20:00 -0.06753 (book -0.03551, sleeve -0.03202, net -0.03899);
2026-08-22 00:00 -0.06366 (book -0.03711, sleeve -0.02656, net -0.04732);
2023-04-19 04:00 -0.05833 (book -0.03723, sleeve -0.02111, net -0.02981).
The worst intrabar dips are book-led (the top two are ~90-100% book); the
sleeve never dominates the tail single-handedly, consistent with the risk
budget doing its job. Gate DD (max of 4h-close and 1m-marked full-path DD)
correctly binds on the 1m mark on all three rows.

(4) Concentration of the X = 0.08 gain vs X = 0.03 (per-bar simple-sum
attribution over 10944 live bars, top 5% = 547 bars ranked by X080 sleeve
pnl; compounding caveat: sums do not equal compounded equity ratios, they
attribute the path): total net-per-bar diff 0.32925, top-5% diff 0.55710,
share 169.2%; sleeve-only diff 0.31646, top-5% sleeve diff 0.57468, share
181.6%. Within X080 alone, total sleeve per-bar sum 0.67403 vs top-5% 1.64340
(share 243.8%). The extra budget's edge is highly concentrated: the top 5%
sleeve bars contribute ~1.7-1.8x the total incremental gain, with the
remaining 95% netting a partly offsetting drag. The budget buys fatter tails,
not a uniform lift.

(5) Leakage: engine_user.py plus the v193 driver:
- Feature timing: target uses books[t], s[t], g[t] at the decision
  (engine_user.py:89-98); sigma_d/sigma_4h are rolling windows ending at t
  (prepare sig4, line 63; sd line 99); cubes row i is the holding bar
  T = t+4h (prepare via v172.cube_ohlc). Member books are causal inputs by
  construction; P2 = (A+B)/2 is an algebraic mix at bar t only. PASS.
- Label windows: no forward return is read; PnL comes only from 1m fills,
  SL/TP exits during T, and the T+4h exit/settlement prices. PASS.
- Fit windows: no statistic is fit on any test year in this path; vol and
  the governor are running causal filters (vol from books.shift(2) returns,
  governor from eq at i-2 over the trailing 540 bars); X in (0.03, 0.05,
  0.08) was pre-registered for this direction, not tuned here; selection
  uses first-four-years metrics only. PASS.
- Fill timing: book limit d = 0.001 better than minute-0, minutes 2..238
  strict trade-through with expiry and no fallback (engine_user.py:111-118,
  d_limit/win_end per row); SL/TP checked from minute 0 on the held position
  and from the fill minute on the new position, stop-first in one minute,
  flat afterwards with the pending order cancelled (lines 125-176); sleeve
  trigger minutes 16..238 strict with exits strictly after the fill minute
  in (minute, rung, asset) budget order (lines 186-234); sleeve SL uses
  m_sleeve_sl = 5 per row, TP at L(1 + sigma_4h) unchanged; risk budget
  X with gap 0.02 per the spec. PASS.

Fee/funding arithmetic: maker 0.0002 on book entries and TP, taker 0.00055
on stops/market exits, longs pay 0.0001 at 00/08/16 UTC settlements, shorts
zero, no carry (engine_user.py:33-36,169-180, funds in sleeve exit). This is
the AGENTS.md gate cost model. tests/test_engine_user.py covers limit fill
+ TP, stop through a gap (fills at minute open), unfilled-limit expiry, and
long funding at settlement on synthetic bars. PASS.

## Verdict

- Engineering REPRODUCED bit-exact on all three rows (dev4/5y/last-year,
  gate DD, yearly nets, stats).
- Budget causality PASS (0/5163 mismatches); stop-gap accounting PASS (0 book
  gaps; 7 sleeve gaps at X080 with 0.0062 total equity drag); worst intrabar
  bars are book-led; X080-vs-X030 incremental gain is tail-concentrated
  (~1.7x from the top 5% sleeve bars, compounding caveat noted).
- Look-ahead PASS (decision-known features/sigma/scale/governor, no label
  or fit leakage, causal fill/stop/sleeve/budget timing, first-four-years
  selection only).
- Gate: X080 is the first dev4 >= 5 in this lineage (5.046) with DD <= 20%
  (19.33) and no losing year, but the gate still fails: 5y 4.603 < 5 and the
  most recent year 2.847 < 5 (nets 34.58 / 54.37 / 122.74 / 129.58 / 40.05).
  Manifest (status rejected, live_approved false, audit passed/replay_complete
  false awaiting audit) must stay non-live_approved.
