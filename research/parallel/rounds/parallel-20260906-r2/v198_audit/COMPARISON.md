# v198 blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v198_audit/replication.json
was saved before opening v198/ (see Part A script header E1-E8/L1-L4).
Base: research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py
(the gate engine implementing the AGENTS.md 2026-09-27 user goal, gate cost model
and current execution assumptions). Leader files were not edited.

Reported: research/parallel/rounds/parallel-20260906-r2/v198/v198_result.json
from research/parallel/rounds/parallel-20260906-r2/v198/v198_tsmom_member.py.
Audit: rows key in
research/parallel/rounds/parallel-20260906-r2/v198_audit/replication.json
(V151 = (A+B)/2, TSMOM T on opens_v154 with L in (180, 540, 1080), vol 42-bar
* sqrt(2190), raw signal * 0.20 / vol / 5 clipped to [-0.5, 0.5], blends
0.75 V151 + 0.25 T and 0.5 V151 + 0.5 T; each with the v197 sleeve:
book SL/TP m = 4, rung SL 5 sigma_4h, TP L(1 + sigma_4h), book limit
(d, W) = (0.001, 239), target 0.25, cap 2.0, gap 0.02, size_mult 1.5, X 0.12).

## Pipeline construction check

v198_tsmom_member.py:44-48 builds v151 = (A+B)/2 on the books154 index
(missing -> 0.0) but prepares with eu.prepare(books154, opens); the audit builds
V151 on the member union index (missing -> 0.0) after checking (A+B+D)/3 ==
books_v154 exactly (max abs diff 0.0, union bars 10950, same 5 majors columns)
and verifies V151 index/columns equal books_v154. V151 audit vs driver v151 max
abs diff = 0.0. prepare uses books only for idx/cols while vol/s inside simulate
is recomputed from the books argument, so the driver quirk is immaterial (same
as v193/v197 audits). PASS (same books, same opens, same cubes). Driver passes
sleeve_risk_budget = 0.12 and size_mult = 1.5 per row
(v198_tsmom_member.py:52-53) and leaves target, cap, gap and m_sleeve_tp at
engine defaults; engine_user.py:71 target default 0.25, cap default 2.0, gap
default 0.02, m_sleeve_tp default 1.0 match the audit explicit TARGET = 0.25,
CAP = 2.0, GAP = 0.02, TP mult 1.0. The scaled rung notional takes the size_mult
branch (engine_user.py:187 rn = s * g * mult * 0.25/4/1.657) — the v197 sleeve.

TSMOM construction: driver v198_tsmom_member.py:34-39 computes on the sorted
opens panel sig = sum over L of sign(o / o.shift(L) - 1) / 3, vol =
o.pct_change().rolling(42, min_periods=42).std() * sqrt(2190), raw =
(sig * 0.20 / vol / 5).clip(-0.5, 0.5), reindexed to the books index fillna 0.
The audit compute_tsmom uses o / o.shift(1) - 1 for pct (vs pct_change),
concat-mean skipna for the signal (vs sum/3), same rolling vol and clip, same
reindex fillna 0. On the books span (2021-09-24 onward, where all 5 majors have
full 1080-bar history) both agree: books-span abs-mean 0.05003691 both, max abs
diff driver-T vs audit-T = 2.1e-13 (floating rounding only; signal/vol windows
are identical and causal). No clipping binds on the books span in the audit
(clipped frac 0.0, nonzero frac 0.9999, abs-mean 0.0500, mean +0.0010). PASS —
same T up to arithmetic noise, and the engine outputs below are bit-exact.

TSMOM uses only opens <= t: signal at t reads open_t and open_{t-L} only
(shift L in (180, 540, 1080) on the sorted panel); vol at t is the trailing
42-bar std of 4h pct changes ending at t (pct uses t/t-1, rolling 42 ends at t)
annualized by sqrt(2190); clip/fillna are pointwise at t; the panel is
reindexed to the books index (missing -> 0) without shifting time. The audit
test_tsmom_causal_and_bounded checks truncation causality at 4 cuts
(full-prefix equality), the 0.5 clip bound, a constant-opens zero case and a
steady-uptrend positive case. No open_{t+k}, k > 0, is read. PASS.

## v198 (V151 + TSMOM blends under engine_user, v197 sleeve, book m = 4)

| row | monthly dev4 % | monthly 5y % | last-year monthly % | gate DD % | yearly nets % |
| --- | --- | --- | --- | --- | --- |
| reported ref_v151 | 5.562 | 4.996 | 2.761 | 19.32 | 40.67 / 51.32 / 147.63 / 154.98 / 38.66 |
| audit V151 | 5.562 | 4.996 | 2.761 | 19.32 | 40.67 / 51.32 / 147.63 / 154.98 / 38.66 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported blend75_25 | 4.979 | 4.708 | 3.629 | 20.12 | 35.27 / 34.96 / 143.22 / 132.04 / 53.37 |
| audit BLEND75_25 | 4.979 | 4.708 | 3.629 | 20.12 | 35.27 / 34.96 / 143.22 / 132.04 / 53.37 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported blend50_50 | 4.213 | 3.947 | 2.892 | 23.22 | 33.18 / 16.15 / 128.71 / 104.84 / 40.80 |
| audit BLEND50_50 | 4.213 | 3.947 | 2.892 | 23.22 | 33.18 / 16.15 / 128.71 / 104.84 / 40.80 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |

Yearly legs match in full (net/monthly/dd_1m/mean_g per anchor verified equal
as dicts, not just nets).

Stats are bit-exact on every row (fills/unfilled/stops/tps/rungs/rung_stops/
rung_tps/liq/fees/funding, e.g. V151 40078 / 4079 / 76 / 48 / 5004 / 191 /
2717 / 0 / 0.0968 / 0.1817; BLEND75_25 42201 / 4277 / 78 / 58 / 4957 / 187 /
2685 / 0 / 0.0889 / 0.1674; BLEND50_50 41488 / 4180 / 86 / 55 / 4913 / 186 /
2647 / 0 / 0.0821 / 0.1433). dd_4h/dd_1m match (V151 19.07 / 19.32; BLEND75_25
19.91 / 20.12; BLEND50_50 23.14 / 23.22). More TSMOM weight -> gate DD rises
(19.32 -> 20.12 -> 23.22) while dev4 falls (5.562 -> 4.979 -> 4.213).

V151 equals the v197 selected row P2_M150 exactly (dev4 5.562, 5y 4.996, last
2.761, gate DD 19.32, nets 40.67 / 51.32 / 147.63 / 154.98 / 38.66, stats
40078 / 4079 / 76 / 48 / 5004 / 191 / 2717 / 0). PASS — the required v197 anchor
holds, so the v198 sweep is a pure TSMOM blend on top of the audited v197
selection.

## Selection uses no last-year statistic

v198_tsmom_member.py:57-59: ok = rows with gate_dd <= 20 and all
yearly[:4] net_pct >= 0; pool = ok or all rows; sel = max monthly_dev4 over
pool; final_score_selected reports monthly_5y/monthly_last_year/losing_years/
gate_dd/gate_pass once for the winner. monthly_dev4 in
research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py:267-268
is the geometric mean of years[:4] only. The last-year monthly (2.761 for the
winner) is reported, never ranked on. PASS.

Eligibility note: blend75_25 (dev4 4.979) is correctly excluded by gate_dd
20.12 > 20 and blend50_50 (dev4 4.213) by 23.22 > 20, so ok = {ref_v151}; the
winner ref_v151 is the only eligible row. Audit eligible [V151], selection V151
maps to reported selected ref_v151; final score selected is identical
(5y 4.996 / last 2.761 / DD 19.32).

## Look-ahead check

engine_user.py plus the v198 driver:

- Feature timing: target uses books[t], s[t], g[t] at the decision
  (engine_user.py:89-98); sigma_d/sigma_4h are rolling windows ending at t
  (prepare sig4, line 63; sd = sig4*sqrt(6)); cubes row i is the holding bar
  T = t+4h (prepare via v172.cube_ohlc). Member books are causal inputs by
  construction; V151 = (A+B)/2 is an algebraic mix at bar t only. TSMOM signal
  uses opens with timestamps <= t only (open_t vs open_{t-L}, L in
  (180, 540, 1080) on the sorted opens panel); vol is the trailing 42-bar std
  ending at t; clip/reindex are pointwise at t. The blend weights
  (1.0, 0.75/0.25, 0.5/0.5) are pre-registered constants — none is fit on any
  test year. PASS.
- Label windows: no forward return is read; PnL comes only from 1m fills,
  SL/TP exits during T, and the T+4h exit/settlement prices. PASS.
- Fit windows: no statistic is fit on any test year in this path; vol and
  the governor are running causal filters (vol from books.shift(2) returns,
  governor from eq at i-2 over the trailing 540 bars); TSMOM has no fit
  parameters (fixed L set, fixed 42-bar vol, fixed 0.20/5 scale and 0.5 clip);
  selection uses first-four-years metrics only. PASS.
- Fill timing: book limit 10 bps better than minute-0, minutes 2..238 strict
  trade-through with expiry and no fallback (engine_user.py:111-118,
  d_limit/win_end per row); SL/TP checked from minute 0 on the held position
  and from the fill minute on the new position, stop-first in one minute, flat
  afterwards with the pending order cancelled (lines 125-176); sleeve trigger
  minutes 16..238 strict with exits strictly after the fill minute in (minute,
  rung, asset) budget order with risk budget X = 0.12 and gap 0.02
  (lines 186-228); sleeve SL uses m_sleeve_sl = 5 per row, rung notional
  rn = s * g * 1.5 * 0.25/4/1.657 on every row. PASS.

Fee/funding arithmetic: maker 0.0002 on book entries and TP, taker 0.00055
on stops/market exits, longs pay 0.0001 at 00/08/16 UTC settlements, shorts
zero, no carry (engine_user.py:33-36,169-180, funds in sleeve exit). This is
the AGENTS.md gate cost model. tests/test_engine_user.py covers limit fill
+ TP, stop through a gap (fills at minute open), unfilled-limit expiry, and
long funding at settlement on synthetic bars. PASS.

## Verdict

- Engineering REPRODUCED bit-exact on all three rows (dev4/5y/last-year,
  gate DD, yearly legs, stats).
- TSMOM causality PASS (shift/rolling on sorted opens, truncation-tested;
  driver-T vs audit-T max diff 2.1e-13, arithmetic noise only).
- V151 == v197 selection anchor CONFIRMED exact.
- Look-ahead PASS (decision-known features/sigma/scale/governor, no label
  or fit leakage, causal fill/stop/sleeve/budget timing, first-four-years
  selection only; blend weights pre-registered, not test-fit).
- Direction result: TSMOM blends hurt on the selection metric (dev4 5.562 ->
  4.979 -> 4.213) and breach the DD gate (19.32 -> 20.12 -> 23.22); the 25%
  blend lifts the most recent year (3.629 vs 2.761) but that year is never
  ranked on. Selected = reference (v197).
- Gate: selected ref_v151/V151 is the best dev4 under the DD gate so far (dev4
  5.562 >= 5, DD 19.32 <= 20, no losing year) but the gate still fails: 5y 4.996
  < 5 (by 0.004) and the most recent year 2.761 < 5 (nets 40.67 / 51.32 /
  147.63 / 154.98 / 38.66). Manifest (status rejected, live_approved false,
  audit passed/replay_complete false awaiting audit) must stay non-live_approved.
