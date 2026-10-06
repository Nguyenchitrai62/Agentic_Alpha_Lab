# oc_dipbe REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
B1 base exits (D0 replica: TP 1.0sg, close5 stop 4sg, 8sg backstop, timeout at
next-bar open; maker 0.0002 / taker 0.00055; longs pay 0.0001 on settling
timeouts) vs break-even arm on the SAME 5498 paired fills (majors x R2 depths
2.5/3/3.5/4/5, bars with open in [2021-09-24, 2026-09-24), 5 anchor years):
once 1m high > px*(1+0.6sg) strictly before any base trigger, the close-stop
moves to px*1.00075 (fill + round-trip fees) on 5m-block closes for m>tb, exit
next open taker; bl/TP unchanged with base stop-first priority. Weights
w=1/(1+n_fill) renormalised per year-arm to mean 1 (identical factor across
arms); daily sums by each arm's own exit date UTC; maxDD of cumulative
daily-sum path from 0. Base replica validated: per-year n/sums match
oc_b1deeper B1 to the tick (990/1045/1330/989/1144). BE armed on 3321/5498
fills (60.4%). All 5 years are research data: a PROMISING result would still
need prospective validation (disclosed vs RULES.md hidden-year rule).

## Per-year BASE vs BE (renormalised w; win = net>0 share; tmo = timeout share)
| year | BASE n/mean/win/tmo/sum/worst/DD | BE n/mean/win/tmo/sum/worst/DD | sum ratio | DD pass? |
|---|---|---|---|---|
| 2021 | 990/.00381/.688/.445/3.887/-0.720/0.720 | 990/.00335/.601/.323/3.302/-0.555/0.555 | 85% | YES |
| 2022 | 1045/.00038/.695/.396/0.272/-1.082/1.699 | 1045/-.00034/.607/.291/-0.401/-1.099/1.779 | neg | NO |
| 2023 | 1330/.00397/.773/.328/5.725/-0.400/0.409 | 1330/.00341/.689/.246/5.169/-0.400/0.409 | 90% | YES (equal) |
| 2024 | 989/.00411/.699/.433/3.959/-0.332/0.332 | 989/.00363/.611/.310/3.430/-0.341/0.341 | 87% | NO |
| 2025 | 1144/.00134/.656/.467/1.210/-0.903/1.130 | 1144/.00087/.566/.358/0.785/-0.725/0.879 | 65% | YES |
| FULL | 5498/.00274/.705/.410/15.138/-1.138/1.787 | 5498/.00221/.618/.303/12.359/-1.156/1.872 | 82% | NO |

## Decision (PROMISING = maxDD not worse in >=4/5 yrs AND sum >= 97% of base in >=4/5)
| check | score | pass? |
|---|---|---|
| DD_BE <= DD_base | 3/5 (2021, 2023, 2025) | NO |
| S_BE >= 0.97*S_base | 0/5 (best 90% in 2023; 2022 negative) | NO |
| PROMISING | | NO |

## Notes
- Same failure mode as oc_dipexit E3 (breakeven trail 0/5): the +0.6sg trigger
  fires on 60% of fills, converts timeouts into ~ breakeven stops (win rate
  70.5% -> 61.8%, timeout share 41% -> 30%), and whipsaws winners — the sum
  give-back is 10-35% per year, far beyond the 3% risk-rule budget, and 2022
  goes negative.
- The tail does not even improve reliably: DD is worse in 2022 (1.78 vs 1.70)
  and 2024 (0.341 vs 0.332), equal in 2023; full-path DD 1.87 vs 1.79.
- Repro: `research/tournament/oc_dipbe/{PLAN.md,be_core.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_dipbe.py` (10 tests pass);
  one process, peak RAM ~0.4 GB (float32 1m arrays).

## Verdict
VERDICT: NOT PROMISING — break-even protection keeps >=97% of the yearly sum in 0/5 years and cuts maxDD in only 3/5 years, so the base D0 exit stands.
