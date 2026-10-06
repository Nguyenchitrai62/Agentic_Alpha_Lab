# oc_fillttl REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
D0 = oc_dipexit replica (TP 1sg limit, close5 stop 4sg on (t+1)%5==0,
8sg backstop, timeout at next 4h open; maker 0.0002 / taker 0.00055; longs
pay 0.0001 on settling timeouts) vs fill-relative T240 (time exit at
open(f+240)) and T120 (time exit at max(240, f+120), i.e. >=120 min), with
sl/bl/tp and stop-first priority unchanged and running into the next
bar(s); funding 0.0001 per 00/08/16 UTC settlement in (fill, exit] on TIME
exits only. Majors x R2 depths (2.5/3/3.5/4/5) x B1 sizes (w=1/(1+n),
v399/oc_b1deeper-exact n, raw w*y sums, no renormalisation; fills identical
across variants, only exits differ). 5 anchor years (bar open in
[anchor, next anchor), anchors 2021-09-24..2025-09-24 + 2026-09-24) x 4
clock phases (4h grid from 2020-08-01 00:00 + 0/1/2/3h). PAIRED rungs kept
only if D0+T240+T120 all finite: 22312 (phase0 per-coin
1067/1126/952/1179/1174 = oc_dipexit 5498 to the tick — replica validated;
p1 5675, p2 5610, p3 5529; total 22312). Ledger checksum 5388704f77b6ef2a.
Year = bar-open year; daily sums group w*y by EXIT date UTC; maxDD of the
cumulative daily-sum path from 0 (>=0, w*y units). Mean4 = mean across 4
phases; dispersion = max-min of the four yearly w*y sums. Overlap =
held [f+1,x) vs next-bar live [256,479); share pooled over phases.
All 5 years are research data: a PROMISING result would still need
prospective validation (disclosed vs RULES.md hidden-year rule).

## 4-phase-mean per year (S=sum w*y, n=trades, win=y>0 share, W=worst day, DD=maxDD; D=dispersion of yearly sums)
| year | D0 S/n/win/W/DD/D | T240 S/n/win/W/DD/D | T120 S/n/win/W/DD/D |
|---|---|---|---|
| 2021 | 0.911/1042.8/.660/-0.740/0.856/2.780 | 0.508/1042.8/.701/-0.876/1.205/2.830 | 0.666/1042.8/.678/-0.869/0.985/2.653 |
| 2022 | 0.833/1014.8/.699/-0.726/0.951/1.191 | 1.123/1014.8/.740/-0.888/1.107/2.274 | 0.897/1014.8/.720/-0.889/1.117/1.820 |
| 2023 | 2.100/1338.0/.748/-0.735/0.800/3.357 | 2.268/1338.0/.783/-0.786/0.833/2.432 | 2.218/1338.0/.765/-0.749/0.809/2.402 |
| 2024 | 3.197/989.5/.734/-0.274/0.355/0.917 | 3.730/989.5/.790/-0.274/0.288/1.470 | 3.511/989.5/.764/-0.236/0.263/0.923 |
| 2025 | 0.677/1193.0/.661/-0.508/0.607/0.441 | 0.531/1193.0/.725/-0.722/1.032/1.210 | 0.636/1193.0/.687/-0.602/0.713/1.042 |

## Per-phase yearly sums (w*y; shows the clock swing)
| year | D0 p0/p1/p2/p3 | T240 p0/p1/p2/p3 | T120 p0/p1/p2/p3 |
|---|---|---|---|
| 2021 | 2.388/0.916/0.733/-0.392 | 2.300/-0.178/0.441/-0.530 | 2.393/-0.031/0.561/-0.260 |
| 2022 | 0.183/1.374/1.313/0.461 | -0.078/1.946/2.196/0.427 | -0.067/1.719/1.753/0.181 |
| 2023 | 3.810/1.591/2.546/0.453 | 3.567/1.888/2.484/1.135 | 3.365/1.760/2.786/0.963 |
| 2024 | 2.579/3.219/3.497/3.495 | 3.083/3.442/3.843/4.553 | 2.997/3.613/3.514/3.920 |
| 2025 | 0.712/0.440/0.676/0.881 | 0.134/-0.113/1.096/1.006 | 0.723/0.018/0.742/1.059 |

## Gross-exposure note (same coin, next bar; pooled over phases)
| year | D0 minutes/fills | T240 minutes/fills | T120 minutes/fills |
|---|---|---|---|
| 2021 | 0.000/0.000 | 0.470/0.413 | 0.225/0.290 |
| 2022 | 0.000/0.000 | 0.442/0.364 | 0.192/0.247 |
| 2023 | 0.000/0.000 | 0.425/0.297 | 0.194/0.205 |
| 2024 | 0.000/0.000 | 0.463/0.379 | 0.220/0.279 |
| 2025 | 0.000/0.000 | 0.467/0.423 | 0.214/0.295 |
Read: D0 never overlaps by construction (x<=240<256). T240 holds ~42-47%
of rung-minutes inside the next bar's live window (30-42% of fills touch
it); T120 ~19-22% of minutes (20-30% of fills). Standalone rung sums above
ignore this crowding; a deployment would need netting/capital for
overlapping same-coin rungs.

## Decision (PROMISING = mean4 sum >= D0 in >=4/5 AND mean4 DD not worse by >0.01 in >=4/5 AND dispersion strictly lower in >=3/5)
| variant | sum>=D0 | DD<=D0+0.01 | disp lower | verdict |
|---|---|---|---|---|
| T240 | 3/5 (2022,2023,2024) | 1/5 (only 2024) | 1/5 (only 2023) | NOT PROMISING |
| T120 | 3/5 (2022,2023,2024) | 2/5 (2023,2024) | 2/5 (2021,2023) | NOT PROMISING |

## Notes
- Longer holds raise win rates every year (D0 66-75% -> T120 68-77% ->
  T240 70-79%) but not sums: 2021 and 2025 lose under both T variants
  (-0.40/-0.25 and -0.15/-0.04 mean4), and tails worsen (T240 DD +0.35/
  +0.16/+0.03/-0.07/+0.43; worst day worse in 4/5 years for both).
- Dispersion is not cured: T240 dispersion is larger in 4/5 years, T120 in
  3/5; the clock swing (e.g. 2023: 0.45..3.81 across phases) persists.
- Repro: `research/tournament/oc_fillttl/{PLAN.md,fillttl.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_fillttl.py` (15 tests
  pass); one process, majors 1m OHLC as float32.

## Verdict
VERDICT: NOT PROMISING — neither fill-relative exit meets the pre-registered rule (T240 3/1/1, T120 3/2/2), so the 4h-clock time exit stands.
