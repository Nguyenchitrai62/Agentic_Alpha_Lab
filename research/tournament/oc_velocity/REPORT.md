# oc_velocity REPORT (2026-10-05; PLAN pre-registered before any outcome)

## Setup
B1 (oc_b1deeper replica: static bid at lv = O*(1-k*sg), k in 2.5/3/3.5/4/5,
size w = 1/(1+n), D0 exits from lv; maker 0.0002 / taker 0.00055; longs pay
0.0001 on settling timeouts) vs B1+velocity-guard (BTC close(m-1) <=
max(close(m-16..m-1))*(1-3.0*sg_BTC); from guard minute m* cancel all
still-resting majors bids, kept iff f < m*; kept rungs identical price /
size / exits). Majors x R2 depths, bars open in [2021-09-24, 2026-09-24)
(5 anchor years); same weights, NO renormalisation (guard = subset sum);
daily sums of w*y by exit date UTC; maxDD of cumulative daily-sum path.
B1 fills 5498 = replica to the tick per coin (1067/1126/952/1179/1174) with
matching means/win rates. Guard fired in 65 bars, removed 394 rungs
(75/107/102/39/71 per year) in 41 bars. Ledger checksum c48fdc41b8337eb1.
All 5 years are research data: a PROMISING result would still need
prospective validation (disclosed vs RULES.md hidden-year rule).

## Per-year B1 vs GUARD (same-weight w*y sums; mean in %, win = net>0 share)
| year | B1 n/mean/win/sum/worst/DD | GUARD n/mean/win/sum/worst/DD | removed n/mean/win/rsum |
|---|---|---|---|
| 2021 | 990/0.38/.688/2.388/-0.442/0.442 | 915/0.46/.697/2.401/-0.469/0.469 | 75/-0.54/.573/-0.013 |
| 2022 | 1045/0.04/.695/0.183/-0.727/1.142 | 938/-0.05/.678/-0.058/-0.727/1.199 | 107/+0.83/.841/+0.240 |
| 2023 | 1330/0.40/.773/3.810/-0.266/0.272 | 1228/0.41/.765/3.837/-0.266/0.272 | 102/+0.26/.873/-0.028 |
| 2024 | 989/0.41/.699/2.579/-0.216/0.216 | 950/0.40/.700/2.428/-0.216/0.216 | 39/+0.57/.667/+0.151 |
| 2025 | 1144/0.13/.656/0.712/-0.531/0.665 | 1073/0.19/.645/0.823/-0.380/0.514 | 71/-0.72/.817/-0.111 |
| FULL | 5498/0.27/.705/9.671/-0.727/1.142 | 5104/0.29/.699/9.432/-0.727/1.199 | 394/+0.13/.763/+0.240 |

## Decision (PROMISING = DD not worse in >=4/5 yrs AND sum >=95% B1 in >=4/5)
| year | DD_g <= DD_B1 | S_g >= 95% S_B1 (ratio) |
|---|---|---|
| 2021 | NO (0.469 > 0.442) | YES (100.5%) |
| 2022 | NO (1.199 > 1.142) | NO (neg / +0.183) |
| 2023 | YES (equal) | YES (100.7%) |
| 2024 | YES (equal) | NO (94.1%) |
| 2025 | YES (0.514 < 0.665) | YES (115.6%) |
| score | 3/5 | 3/5 -> NOT PROMISING |

## Top-10 guard events (ranked by removed count, then removed RS)
| bar open UTC | m* | removed n/mean/win/rsum |
|---|---|---|
| 2026-02-06 00:00 | 16 | 23/-1.11/.783/-0.066 |
| 2024-01-03 12:00 | 16 | 22/-0.70/.727/-0.031 |
| 2024-04-13 20:00 | 16 | 20/+0.70/.900/+0.032 |
| 2022-11-08 16:00 | 126 | 19/-0.08/.789/-0.005 |
| 2024-02-28 16:00 | 86 | 18/-0.96/.778/-0.173 |
| 2023-06-30 12:00 | 99 | 17/+1.05/.941/+0.058 |
| 2022-05-11 12:00 | 39 | 16/-2.78/.563/-0.096 |
| 2022-02-24 00:00 | 188 | 16/-0.53/.313/-0.024 |
| 2022-11-09 20:00 | 44 | 16/+1.10/.875/+0.039 |
| 2026-02-05 20:00 | 23 | 16/+1.11/1.000/+0.059 |

Query dates fired? 2024-01-03 YES (12:00 bar, m*=16, saved -0.031),
2024-08-05 YES, 2022-06-13 NO, 2022-11-09 YES (20:00 bar but removed rungs
won +0.039), 2025-10-10 YES.

## Notes
- The guard fires rarely (65/10956 bars) and mostly at m*=16 on the open,
  i.e. it reacts to a velocity print already complete before the live window.
- Removed rungs win 76% overall (84-94% in 2022-23): the guard cancels dips
  that usually still mean-revert to TP, so in 2022 it deleted +0.24 of edge
  and flipped the year negative, and in 2024 it cost 5.9% of the sum (94.1%
  < 95% bar). It helped only in 2025 (cut DD 0.665->0.514, sum +15%).
- Repro: `research/tournament/oc_velocity/{PLAN.md,velocity.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_velocity.py` (10 tests
  pass); one process, peak RAM ~0.5 GB (float32 1m arrays).

## Verdict
VERDICT: NOT PROMISING — the 3-sigma velocity guard keeps >=95% of B1's sum in only 3/5 years and cuts maxDD in only 3/5 years (it deletes mostly winning rungs, e.g. 2022 removed win rate 84%), so the flash-velocity dip guard is rejected and B1 stands.
