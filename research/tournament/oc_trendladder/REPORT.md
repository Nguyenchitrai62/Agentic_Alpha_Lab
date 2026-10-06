# oc_trendladder REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
BASE (fixed R2 depths 2.5/3/3.5/4/5, static bid, size x 1/(1+n), D0-from-fill
exits) vs TREND (same, but every rung depth k scaled by BTC-trend mult known
at the bar open: r30 = O_BTC[j-1]/O_BTC[j-181]-1 from 4h opens strictly rows
< bar; mult = 0.85 iff finite r30 > 0 else 1.15; k_eff = k*mult, e.g. 2.5 ->
2.125 up / 2.875 down; n detector v399-exact NOT scaled; stops/TP from the
ACTUAL fill px; maker 0.0002 / taker 0.00055; longs pay 0.0001 on settling
timeouts). Majors x R2 depths, bars with open in [2021-09-24, 2026-09-24)
(5 anchor years); n = other majors with C(T+m-1) <= O(T) x (1 - 2.5 sg(T)).
Weights w = 1/(1+n_fill), renormalised per year-arm to mean 1 (primary);
daily sums by exit date UTC; maxDD of cumulative daily-sum path from 0.
Trend mix over traded bars: 28995 up (0.85) / 25785 down (1.15). BASE fills
5498 = oc_b1deeper B1 paired rungs to the tick per coin (1067/1126/952/
1179/1174) with matching means/win rates — replica validated. TREND fills
6097 (+10.9%: 1122/1229/1071/1338/1337). Ledger checksum a2af22d42090d60b.
All 5 years are research data: a PROMISING result would still need
prospective validation (disclosed vs RULES.md hidden-year rule).

## Per-year BASE vs TREND (renormalised w; mean in bps, win = net>0 share)
| year | BASE n/mean/win/sum/worst/DD | TREND n/mean/win/sum/worst/DD |
|---|---|---|
| 2021 | 990/38.1/.688/3.887/-0.720/0.720 | 847/47.7/.708/4.061/-0.333/0.531 |
| 2022 | 1045/3.8/.695/0.272/-1.082/1.699 | 1206/8.9/.690/1.333/-0.815/1.201 |
| 2023 | 1330/39.7/.773/5.725/-0.400/0.409 | 1718/40.8/.771/7.161/-0.703/0.767 |
| 2024 | 989/41.1/.699/3.959/-0.332/0.332 | 1246/31.7/.680/3.573/-0.523/0.523 |
| 2025 | 1144/13.4/.656/1.210/-0.903/1.130 | 1080/13.3/.670/0.754/-1.658/1.742 |
| FULL | 5498/27.4/.705/15.138/-1.138/1.787 | 6097/28.7/.710/16.975/-1.485/1.560 |

## Decision (PROMISING = sum not lower in >=4/5 yrs AND maxDD not worse in >=4/5)
| check | score | pass? |
|---|---|---|
| S_tr >= S_base | 3/5 (2021 +0.17, 2022 +1.06, 2023 +1.44; 2024 -0.39, 2025 -0.46) | NO |
| DD_tr <= DD_base | 2/5 (2021, 2022; worse in 2023/2024/2025) | NO |
| PROMISING | | NO |

## Notes
- TREND helps 2021-2023 on sums (all three up years pass) but gives it back
  in 2024-2025 (-0.39/-0.46) while drawdown is worse in three years
  (2023 0.41 -> 0.77, 2024 0.33 -> 0.52, 2025 1.13 -> 1.74 with worst day
  -1.66 vs -0.90). Full-path sum favours TREND (15.14 -> 16.97) but that is
  three good years vs two bad ones, not consistency.
- Raw (non-renormalised) sums show the same 3/5 pattern (BASE vs TREND:
  2.39/0.18/3.81/2.58/0.71 vs 2.45/0.95/5.20/2.52/0.46 — passes 2021/22/23),
  so the verdict does not hinge on renormalisation.
- Repro: `research/tournament/oc_trendladder/{PLAN.md,trend.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_trendladder.py` (15 tests
  pass); one process, all-five-coins 1m closes as float32, peak RAM ~0.5 GB.

## Verdict
VERDICT: NOT PROMISING — trend-conditional depth beats fixed depths on sum in only 3/5 years and on maxDD in only 2/5 years, so the rule is rejected and fixed R2 depths stand.
