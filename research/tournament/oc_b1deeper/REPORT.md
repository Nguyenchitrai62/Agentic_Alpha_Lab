# oc_b1deeper REPORT (2026-10-05; PLAN pre-registered before any outcome)

## Setup
B1 (v399 size-only: static bid at lv, size x 1/(1+n)) vs B1+deeper (bid amended
to lv x (1 - 0.5 n sg) while n >= 1, back to lv when n = 0; size kept as B1;
fill on strict low < level in force; exits = D0 replica from the ACTUAL fill
px; maker 0.0002 / taker 0.00055; longs pay 0.0001 on settling timeouts).
Majors x R2 depths (2.5/3/3.5/4/5), bars with open in [2021-09-24, 2026-09-24)
(5 anchor years); n = other majors with C(T+m-1) <= O(T) x (1 - 2.5 sg(T)),
v399-exact. Weights w = 1/(1+n_fill), renormalised per year-arm to mean 1
(primary); daily sums by exit date UTC; maxDD of cumulative daily-sum path
from 0. B1 fills 5498 = oc_dipexit D0 paired rungs to the tick per coin
(1067/1126/952/1179/1174) with matching means/win rates — replica validated.
DEEP fills 3659 (-33%: 702/737/580/799/841). Ledger checksum 47fcb772de97b005.
All 5 years are research data: a PROMISING result would still need
prospective validation (disclosed vs RULES.md hidden-year rule).

## Per-year B1 vs B1+deeper (renormalised w; mean in bps, win = net>0 share)
| year | B1 n/mean/win/sum/worst/DD | DEEP n/mean/win/sum/worst/DD |
|---|---|---|
| 2021 | 990/38.1/.688/3.887/-0.720/0.720 | 647/51.0/.730/3.011/-0.465/0.465 |
| 2022 | 1045/3.8/.695/0.272/-1.082/1.699 | 755/7.7/.726/0.384/-0.765/1.341 |
| 2023 | 1330/39.7/.773/5.725/-0.400/0.409 | 956/34.0/.773/4.043/-0.353/0.361 |
| 2024 | 989/41.1/.699/3.959/-0.332/0.332 | 641/40.2/.710/2.461/-0.285/0.285 |
| 2025 | 1144/13.4/.656/1.210/-0.903/1.130 | 660/12.6/.703/0.722/-0.595/0.672 |
| FULL | 5498/27.4/.705/15.138/-1.138/1.787 | 3659/28.8/.732/10.620/-0.761/1.335 |

## Decision (PROMISING = sum not lower in >=4/5 yrs AND maxDD not worse in >=4/5)
| check | score | pass? |
|---|---|---|
| S_deep >= S_B1 | 1/5 (only 2022, +0.11) | NO |
| DD_deep <= DD_B1 | 5/5 (cuts DD every year) | YES |
| PROMISING | | NO |

## Notes
- The deeper bid raises per-fill quality (win rate higher in all 5 years,
  mean higher in 2021-22) and cuts tails everywhere (full DD 1.79 -> 1.34,
  worst day better every year), but misses ~1/3 of fills — many of them
  winners — so the size-weighted yearly sum loses in 4/5 years (-0.88/-1.68/
  -1.50/-0.49 in 2021/2023/2024/2025). Opportunity cost dominates the price
  improvement under equal-mean-exposure scoring.
- Raw (non-renormalised) sums show the same 1/5 pattern (B1 vs DEEP:
  2.39/0.18/3.81/2.58/0.71 vs 2.35/0.31/3.26/2.08/0.58), so the verdict does
  not hinge on renormalisation.
- Repro: `research/tournament/oc_b1deeper/{PLAN.md,deeper.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_b1deeper.py` (13 tests pass);
  one process, peak RAM ~0.4 GB (float32 1m arrays).

## Verdict
VERDICT: NOT PROMISING — B1+deeper cuts drawdown in 5/5 years but its yearly sum is not lower in only 1/5 years, so the correlation-aware dip price is rejected and B1 size-only stands.
