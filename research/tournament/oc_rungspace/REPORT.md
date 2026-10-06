# oc_rungspace REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
BASE (R2 depths 2.5/3.0/3.5/4.0/5.0, static B1 bid, size x 1/(1+n)) vs WIDE
(ONE fixed alternative 2.5/3.25/4.0/5.0/6.0, same B1 size, same D0 exits from
the fill px: TP = px*(1+sg), close-stop 4sg, backstop 8sg; maker 0.0002 /
taker 0.00055; longs pay 0.0001 on settling timeouts). Majors, bars with open
in [2021-09-24, 2026-09-24) (5 anchor years); n = other majors with
C(T+m-1) <= O(T) x (1 - 2.5 sg(T)), v399-exact; fill on strict low < lv,
live offsets 16..238. Weights w = 1/(1+n_fill), renormalised per year-arm to
mean 1 (primary); daily sums by exit date UTC; maxDD of cumulative daily-sum
path from 0; ALL5 = bars where all 5 rungs of a coin have kept fills. BASE
fills 5498 = oc_b1deeper B1 to the tick per coin (1067/1126/952/1179/1174)
with matching means/win rates — replica validated. WIDE fills 4479 (-19%:
861/910/783/957/968). Ledger checksum dfcbea78f99708ca. All 5 years are
research data: a PROMISING result would still need prospective validation
(disclosed vs RULES.md hidden-year rule).

## Per-year BASE vs WIDE (renormalised w; mean in bps, win = net>0 share)
| year | BASE n/mean/win/sum/worst/DD/all5 | WIDE n/mean/win/sum/worst/DD/all5 |
|---|---|---|
| 2021 | 990/38.1/.688/3.887/-0.720/0.720/58 | 807/38.8/.693/3.151/-0.470/0.470/29 |
| 2022 | 1045/3.8/.695/0.272/-1.082/1.699/72 | 870/10.2/.708/0.869/-0.865/1.325/41 |
| 2023 | 1330/39.7/.773/5.725/-0.400/0.409/80 | 1091/32.3/.764/4.207/-0.287/0.291/55 |
| 2024 | 989/41.1/.699/3.959/-0.332/0.332/44 | 785/37.8/.696/2.898/-0.186/0.196/15 |
| 2025 | 1144/13.4/.656/1.210/-0.903/1.130/52 | 926/12.3/.662/0.921/-0.798/0.952/25 |
| FULL | 5498/27.4/.705/15.138/-1.138/1.787/306 | 4479/26.0/.707/12.090/-0.915/1.401/165 |

## Decision (PROMISING = sum not lower in >=4/5 yrs AND maxDD not worse in >=4/5)
| check | score | pass? |
|---|---|---|
| S_wide >= S_base | 1/5 (only 2022, +0.60) | NO |
| DD_wide <= DD_base | 5/5 (cuts DD every year) | YES |
| PROMISING | | NO |

## Notes
- Wider spacing halves full-ladder bars (306 -> 165, cut every year,
  most in 2024: 44 -> 15) and cuts tails everywhere (full DD 1.79 -> 1.40,
  worst day better every year), but drops ~1/5 of fills — many of them
  winners at the vacated 3.0/3.5 rungs — so the size-weighted yearly sum
  loses in 4/5 years (-0.74/-1.52/-1.06/-0.29 in 2021/2023/2024/2025).
  Opportunity cost dominates the concentration benefit under
  equal-mean-exposure scoring.
- Raw (non-renormalised) sums show the same 1/5 pattern (BASE vs WIDE:
  2.39/0.18/3.81/2.58/0.71 vs 1.92/0.59/2.77/1.90/0.55), so the verdict
  does not hinge on renormalisation.
- Repro: `research/tournament/oc_rungspace/{PLAN.md,rungspace.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_rungspace.py` (13 tests
  pass); one process, peak RAM ~0.4 GB (float32 1m arrays).

## Verdict
VERDICT: NOT PROMISING — wider spacing cuts full-ladder bars 306->165 and drawdown in 5/5 years but its yearly sum is not lower in only 1/5 years, so the current R2 rung spacing stands.
