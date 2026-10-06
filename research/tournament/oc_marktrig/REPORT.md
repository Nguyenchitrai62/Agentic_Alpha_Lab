# oc_marktrig REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
BASE = oc_dipexit D0 replica (TP 1sg limit; close5 4sg stop on last close at
(m+1)%5==0 exiting next open; 8sg backstop on last low exiting min(bl,open);
timeout at next-bar open; maker 0.0002 / taker 0.00055; longs pay 0.0001 on
settling timeouts) with B1 sizes (w = 1/(1+n), v399/oc_b1deeper-exact n, raw
w*y sums, no renormalisation; fills identical across arms). MARK = same
levels/TP/timeout/fees, but both stops TRIGGER on the reconstructed mark
mark(t) = close(t) x (1 + trailing-5m mean of the Binance premium-index 1m
close over [t-4, t], causal; NaN mark never triggers): close5 fires on
mark(m) <= sl exiting next open, backstop fires on mark(t) <= bl exiting next
open (taker; no min() cap -- a close-based trigger cannot exit inside its own
minute). Stop-first priority kept (backstop ties, TP strictly earlier, else
stop; same-minute stop+TP -> stop). Majors x R2 depths (2.5/3/3.5/4/5) x 5
anchor years (bar open in [anchor, next anchor), anchors 2021-09-24..2025-09-24
+ 2026-09-24) x 4 clock phases (4h grid from 2020-08-01 00:00 + 0/1/2/3h).
PAIRED rungs kept only if BASE and MARK nets both finite: 22312 (phase0
per-coin 1067/1126/952/1179/1174 = oc_dipexit 5498 to the tick -- replica
validated; p1 5675, p2 5610, p3 5529). BASE 5y 4-phase-mean sum = 7.718 =
oc_placebo_dip base to 1e-3 -- second validation. Ledger checksum
a8f94d824894f7c6. Year = bar-open year; daily sums group w*y by each arm's
own EXIT date UTC; maxDD of the cumulative daily-sum path from 0 (>= 0, w*y
units). Mean4 = mean across 4 phases. All 5 years are research data: a
PROMISING result would still need prospective validation (disclosed vs
RULES.md hidden-year rule).

## 4-phase-mean per year (S = sum w*y, n = trades, win = y>0 share, stops =
close5+backstop count, av = base stops avoided to MARK tp/time, W = worst day, DD = maxDD)
| year | BASE S/n/win/stops/av/W/DD | MARK S/n/win/stops/av/W/DD |
|---|---|---|
| 2021 | 0.911/1042.8/.660/46.5/--/-0.740/0.856 | 0.960/1042.8/.659/46.5/1.25/-0.714/0.822 |
| 2022 | 0.833/1014.8/.699/59.5/--/-0.726/0.951 | 0.606/1014.8/.690/70.8/4.75/-0.727/0.980 |
| 2023 | 2.100/1338.0/.748/78.0/--/-0.735/0.800 | 2.316/1338.0/.749/75.0/6.25/-0.785/0.850 |
| 2024 | 3.197/989.5/.734/11.8/--/-0.274/0.355 | 3.203/989.5/.735/11.8/0.25/-0.264/0.345 |
| 2025 | 0.677/1193.0/.661/34.5/--/-0.508/0.607 | 0.691/1193.0/.661/33.3/0.50/-0.521/0.623 |

Avoided-stop detail (4-phase means per year; denominators = base stops):
2021: avoid rate 2.9% (1.25 rungs: 0.00 tp + 1.25 time; deeper stop->backstop
0.00); 2022: 7.9% (4.75: 1.50 tp + 3.25 time; deeper 1.75); 2023: 8.2% (6.25:
1.50 tp + 4.75 time; deeper 0.00); 2024: 1.5% (0.25: 0.25 tp + 0.00 time;
deeper 0.00); 2025: 2.1% (0.50: 0.00 tp + 0.50 time; deeper 0.00). Full
BASE-how x MARK-how confusion per (phase, year) is stored in results.json.

## Per-phase yearly sums (w*y; shows the clock swing)
| year | BASE p0/p1/p2/p3 | MARK p0/p1/p2/p3 |
|---|---|---|
| 2021 | 2.388/0.916/0.733/-0.392 | 2.503/0.816/0.790/-0.269 |
| 2022 | 0.183/1.374/1.313/0.461 | -0.234/0.705/1.144/0.807 |
| 2023 | 3.810/1.591/2.546/0.453 | 4.132/1.843/2.555/0.733 |
| 2024 | 2.579/3.219/3.497/3.495 | 2.551/3.264/3.497/3.502 |
| 2025 | 0.712/0.440/0.676/0.881 | 0.811/0.322/0.729/0.899 |

## Cascade table: 10 worst exit dates by BASE pooled daily sum (all phases)
| date | BASE sum | MARK sum | delta | BASE stops | MARK stops | BASE tp | MARK tp |
|---|---|---|---|---|---|---|---|
| 2023-08-17 | -2.883 | -2.579 | +0.304 | 78 | 68 | 61 | 64 |
| 2021-12-04 | -2.870 | -2.703 | +0.167 | 49 | 51 | 52 | 51 |
| 2024-04-13 | -2.331 | -2.295 | +0.036 | 39 | 40 | 61 | 61 |
| 2024-01-03 | -2.291 | -2.696 | -0.405 | 64 | 66 | 40 | 38 |
| 2022-05-11 | -2.126 | -2.227 | -0.102 | 69 | 70 | 187 | 187 |
| 2025-10-10 | -2.034 | -2.084 | -0.050 | 70 | 70 | 74 | 74 |
| 2023-06-10 | -1.534 | -1.744 | -0.210 | 34 | 34 | 56 | 56 |
| 2022-11-08 | -0.921 | -0.757 | +0.164 | 37 | 38 | 150 | 150 |
| 2023-06-05 | -0.802 | -0.747 | +0.055 | 27 | 22 | 34 | 34 |
| 2024-08-05 | -0.780 | -0.815 | -0.035 | 63 | 65 | 210 | 209 |

## Decision (PROMISING = mean4 sum >= BASE in >=4/5 AND mean4 maxDD not worse in >=4/5 AND mean4 worst day not worse in >=4/5)
| check | score | pass? |
|---|---|---|
| sum >= BASE | 4/5 (all but 2022: -0.227) | YES |
| maxDD not worse | 2/5 (only 2021, 2024) | NO |
| worst day not worse | 2/5 (only 2021, 2024) | NO |
| PROMISING | | NO |

## Notes
- The mark avoids only 1.5-8.2% of base stops per year (0.25-6.25 rungs per
  phase-year); almost all avoided stops decay into timeouts, only 0-1.5 per
  phase-year recover into TP. The 5y mean4 delta is +0.057 on a 7.72 base.
- The mark FIRES MORE stops than the base in most phase-years (e.g. p0 2022:
  64 -> 84; pooled 2022: 59.5 -> 70.8): in crashes the premium goes negative,
  so mark = close x (1 + negative mean) sits BELOW last and triggers earlier,
  not later. The 2022 mean4 loss (-0.227) and the 2024-01-03 cascade row
  (-0.405, +2 stops) are this mechanism.
- Tails decide the verdict: 2023 worst day -0.735 -> -0.785 and DD 0.800 ->
  0.850 despite a +0.216 sum gain; 2025 also worse on both tail legs at a
  +0.013 sum gain.
- Repro: `research/tournament/oc_marktrig/{PLAN.md,marktrig.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_marktrig.py` (12 tests pass);
  one process via `scripts/heavy_slot.py`, majors 1m OHLC + premium as float32.

## Verdict
VERDICT: NOT PROMISING -- mark-trigger stops beat the base sum in 4/5 years but meet the maxDD and worst-day legs in only 2/5 years, so last-price triggers stand.
