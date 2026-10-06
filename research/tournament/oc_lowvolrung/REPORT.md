# oc_lowvolrung REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
Baseline ladder (R2 rungs 2.5/3/3.5/4/5, B1 static bid, size x 1/(1+n),
D0 exits from the fill px; maker 0.0002 / taker 0.00055; longs pay 0.0001 on
settling timeouts; oc_b1deeper-exact) vs augmented ladder (baseline + extra
2.0-sigma rung armed only when the coin's sigma4 is at/below its walk-forward
lowest-tercile cutoff q(c,Y) from finite sigma with T < anchor). Majors,
bars with open in [2021-09-24, 2026-09-24) (5 anchor years); n = other
majors with C(T+m-1) <= O(T) x (1-2.5 sg(T)). RAW weights w = 1/(1+n_fill),
no renormalisation; daily sums by exit date UTC; maxDD of cumulative
daily-sum path from 0. BASE replica validated: 1067/1126/952/1179/1174
fills per coin and raw yearly sums 2.39/0.18/3.81/2.58/0.71 = oc_b1deeper
B1 to the tick. EXTRA fills 3101 (554/614/662/658/613). Ledger checksum
d64c1267e6bdfd8d. All 5 years are research data: a PROMISING result would
still need prospective validation (disclosed vs RULES.md hidden-year rule).

## Per-year ladder (raw w*y sums; worst day / maxDD in the same units)
| year | BASE n/sum/worst/DD | WITH n/sum/worst/DD | sum higher? | DD not worse? |
|---|---|---|---|---|
| 2021 | 990/2.39/-0.44/0.44 | 1623/2.06/-0.72/0.74 | NO (-0.33) | NO |
| 2022 | 1045/0.18/-0.73/1.14 | 1676/0.57/-0.93/1.58 | YES (+0.38) | NO |
| 2023 | 1330/3.81/-0.27/0.27 | 2085/5.42/-0.39/0.41 | YES (+1.61) | NO |
| 2024 | 989/2.58/-0.22/0.22 | 1385/3.09/-0.21/0.23 | YES (+0.51) | NO |
| 2025 | 1144/0.71/-0.53/0.66 | 1830/0.34/-0.92/1.28 | NO (-0.37) | NO |
| FULL | 5498/9.67/-/1.14 | 8599/11.48/-/1.58 | (raw +1.81) | (worse) |

## Extra 2.0 rung standalone (raw; mean in bps, win = net>0 share)
| year | n | mean | win | sum |
|---|---|---|---|---|
| 2021 | 633 | -9.9 | .573 | -0.33 |
| 2022 | 631 | +5.8 | .656 | +0.38 |
| 2023 | 755 | +20.3 | .691 | +1.61 |
| 2024 | 396 | +15.9 | .616 | +0.51 |
| 2025 | 686 | -5.2 | .576 | -0.37 |

## Decision (PROMISING = sum strictly higher in >=4/5 yrs AND maxDD not worse in >=4/5)
| check | score | pass? |
|---|---|---|
| S_with > S_base | 3/5 (2022/2023/2024) | NO |
| DD_with <= DD_base | 0/5 (worse every year) | NO |
| PROMISING | | NO |

## Notes
- The gated rung helps in the middle years (2022-24: positive mean, win
  62-69%, ladder sum +0.38/+1.61/+0.51) but loses at both ends (2021 mean
  -9.9 bps, 2025 -5.2 bps; ladder sum -0.33/-0.37), and it worsens maxDD in
  all 5 years (full-path DD 1.14 -> 1.58; worst day worse in 4/5). LOO sums
  (descriptive, no selection): WITH higher in 5/5 exclusions, driven by
  2023; per-year gate fails on both required legs.
- Cut-offs (sigma terciles, per coin, strictly pre-anchor) drift down as
  vol compresses (e.g. BTC 0.0141 -> 0.0099); armed-bar shares 11-20% per
  coin-year (see results.json). Gate boundary inclusive (<=).
- Repro: `research/tournament/oc_lowvolrung/{PLAN.md,core.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_lowvolrung.py` (12 tests
  pass); one process, peak RAM ~0.4 GB (float32 1m arrays).

## Verdict
VERDICT: NOT PROMISING — the low-vol-gated 2.0 rung raises the ladder sum in only 3/5 years and worsens maxDD in 5/5 years, so the regime-conditional shallow rung is rejected.
