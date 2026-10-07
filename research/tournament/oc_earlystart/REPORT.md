# oc_earlystart REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
BASE (B1 rungs fillable offsets 16..238) vs EARLY (SAME static bids at
lv = O(T)x(1-kxsg(T)), fillable offsets 6..238; bot places them at minute 5,
nothing fills in minutes 0-5 per the user rule). B1 size x 1/(1+n) at the
OWN fill minute, strict low<lv trade-through fills, D0 exits from the fill
price (TP +1sg maker, close5 stop 4sg / backstop 8sg / timeout next open
taker, 0.0001 funding on settling timeouts), majors x R2 depths
(2.5/3/3.5/4/5), bars with open in [2021-09-24, 2026-09-24) (5 anchor
years). Weights w = 1/(1+n_fill), renormalised per year-arm to mean 1
(primary, as oc_b1deeper); daily sums by exit date UTC; maxDD of cumulative
daily-sum path from 0; eff = sum/maxDD. BASE fills per coin
1067/1126/952/1179/1174 match oc_b1deeper B1 to the fill and its per-year
sums/means/win rates to 4 decimals — replica validated. EARLY adds only +33
net fills (1070/1134/959/1187/1181); most 6-15 touches pre-empt a later BASE
fill of the same rung (same price, earlier f, different exit). Ledger
checksum cf485f322a6c759d. All 5 years are research data: a PROMISING result
still needs prospective validation (disclosed vs RULES.md hidden-year rule).

## Per-year BASE vs EARLY (renormalised w; mean in bps, win = net>0 share)
| year | BASE n/mean/win/sum/worst/DD/eff | EARLY n/mean/win/sum/worst/DD/eff |
|---|---|---|
| 2021 | 990/38.1/.688/3.887/-0.720/0.720/5.40 | 998/38.2/.690/3.903/-0.715/0.715/5.46 |
| 2022 | 1045/3.8/.695/0.272/-1.082/1.699/0.16 | 1052/5.6/.701/0.568/-1.075/1.643/0.35 |
| 2023 | 1330/39.7/.773/5.725/-0.400/0.409/14.01 | 1346/32.7/.767/5.044/-0.845/0.845/5.97 |
| 2024 | 989/41.1/.699/3.959/-0.332/0.332/11.92 | 991/41.5/.700/4.011/-0.331/0.331/12.10 |
| 2025 | 1144/13.4/.656/1.210/-0.903/1.130/1.07 | 1144/13.4/.656/1.213/-0.899/1.125/1.08 |
| FULL | 5498/27.4/.705/15.138/-1.138/1.787/8.47 | 5531/26.1/.706/14.849/-1.124/1.717/8.65 |

## Marginal minute-6-15 fills alone (EARLY arm, raw y in bps, descriptive)
| year | n | mean | win rate |
|---|---|---|---|
| 2021 | 14 | +58.8 | .857 |
| 2022 | 42 | -44.3 | .786 |
| 2023 | 93 | -82.9 | .720 |
| 2024 | 5 | +70.3 | .800 |
| 2025 | 23 | -111.2 | .783 |
| FULL | 177 | -61.9 | .757 |

## Decision (PROMISING = sum strictly higher in >=4/5 yrs AND maxDD not worse in >=4/5)
| check | score | pass? |
|---|---|---|
| S_EARLY > S_BASE | 4/5 (2021 +0.02, 2022 +0.30, 2024 +0.05, 2025 +0.00; 2023 -0.68) | YES |
| DD_EARLY <= DD_BASE | 4/5 (2021/22/24/25 not worse; 2023 0.409 -> 0.845 worse) | YES |
| PROMISING | | YES |

## Notes
- The effect is tiny where it wins: three of the four passing years move the
  renormalised sum by +0.02/+0.05/+0.00; the only material gain is 2022
  (+0.30, doubling the worst year). 2023 loses materially (-0.68) and its DD
  doubles (0.41 -> 0.85, worst day -0.40 -> -0.85).
- The marginal 6-15 fills look bad in isolation (FULL mean -61.9 bps despite
  a 76% win rate — fat left tail; negative mean in 3/5 years), yet the arm
  comparison passes, because ~144/177 of them displace a later BASE fill of
  the same rung rather than adding exposure: this test measures
  fill-TIMING shift, not extra size.
- Full-path totals favour BASE (15.14 vs 14.85 renormalised; raw sums
  9.67 vs 9.61), so the year-count verdict rests on renormalisation and on
  2024's DD pass by 0.0006 — fragile.
- Repro: `research/tournament/oc_earlystart/{PLAN.md,early.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_earlystart.py` (12 tests
  pass); one process, peak RAM ~0.4 GB (float32 1m arrays).

## Verdict
VERDICT: PROMISING (4/5 years sum higher, 4/5 years maxDD not worse) — but fragile: gains are near-zero in 3 of 4 passing years, 2023 loses -0.68 with doubled DD, marginal 6-15 fills average -62 bps, and full-path totals favour BASE; needs prospective validation before any engine change.
