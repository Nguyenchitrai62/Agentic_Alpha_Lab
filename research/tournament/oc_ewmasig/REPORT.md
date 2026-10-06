# oc_ewmasig REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
BASE (sigma360: pct_change of 4h opens, rolling 360 std ddof=1 min 120, shift 1)
vs EWMA (sigma_eff = r.ewm(halflife=60, min_periods=120, adjust=True).std(
bias=False).shift(1), lambda = 0.5**(1/60) ~= 0.98851, known at bar open;
replaces sigma360 everywhere). Rung levels, close-stop (4sg), backstop (8sg)
and TP (1.0sg) all use the arm's own sigma; n counts other majors with
C(T+m-1) <= O(T)*(1-2.5*sg_arm(T)) (F=2.5, v399-exact). B1 static bid, fill on
strict low < lv in live minutes 16..238, size 1/(1+n_fill); D0-from-fill
exits; maker 0.0002 / taker 0.00055; longs pay 0.0001 on settling timeouts.
Majors x R2 depths (2.5/3/3.5/4/5), bars with open in [2021-09-24, 2026-09-24)
(5 anchor years); 4h grid from 2020-08-01 00:00 UTC. Weights w renormalised
per year-arm to mean 1 (primary); daily sums by exit date UTC; maxDD of
cumulative daily-sum path from 0; E = S/maxDD. BASE fills 5498 =
oc_b1deeper B1 to the tick per coin (1067/1126/952/1179/1174) - replica
validated. EWMA fills 5176 (-6%: 1028/1087/904/1090/1067). Ledger checksum
fc54befd3d544eb2. All 5 years are research data: a PROMISING result would still
need prospective validation (disclosed vs RULES.md hidden-year rule).

## Per-year BASE vs EWMA (renormalised w; mean in bps, win = net>0 share)
| year | BASE n/mean/win/sum/raw/worst/DD/E | EWMA n/mean/win/sum/raw/worst/DD/E |
|---|---|---|
| 2021 | 990/38.1/.688/3.887/2.388/-0.720/0.720/5.40 | 988/41.5/.684/3.410/2.024/-0.576/0.576/5.92 |
| 2022 | 1045/3.8/.695/0.272/0.183/-1.082/1.699/0.16 | 1075/10.2/.705/1.273/0.862/-0.869/1.579/0.81 |
| 2023 | 1330/39.7/.773/5.725/3.810/-0.400/0.409/14.01 | 1157/27.9/.753/4.443/3.039/-0.542/0.625/7.11 |
| 2024 | 989/41.1/.699/3.959/2.579/-0.332/0.332/11.92 | 932/39.2/.689/3.745/2.334/-0.277/0.409/9.15 |
| 2025 | 1144/13.4/.656/1.210/0.712/-0.903/1.130/1.07 | 1024/11.1/.648/0.951/0.548/-1.216/1.443/0.66 |
| FULL | 5498/27.4/.705/15.138/—/-1.138/1.787/8.47 | 5176/25.6/.698/13.913/—/-1.107/1.688/8.24 |

## EWMA share (coin-bars with sg_ewma > sg360, among BASE-tradable bars)
| year | coin_bars | frac ewma>360 | median ewma/360 |
|---|---|---|---|
| 2021 | 10950 | 0.385 | 0.96 |
| 2022 | 10950 | 0.385 | 0.94 |
| 2023 | 10980 | 0.454 | 0.98 |
| 2024 | 10950 | 0.396 | 0.96 |
| 2025 | 10950 | 0.448 | 0.97 |
| FULL | 54780 | 0.414 | 0.96 |

## Decision (PROMISING = sum not lower in >=4/5 yrs AND maxDD not worse in >=4/5)
| check | score | pass? |
|---|---|---|
| S_ewma >= S_base | 1/5 (only 2022, +1.00) | NO |
| DD_ewma <= DD_base | 2/5 (pass 2021, 2022) | NO |
| PROMISING | | NO |

## Notes
- Unlike max() (ADAPT, -30% fills) the EWMA keeps ~94% of fills because it is
  slightly TIGHTER than sigma360 on average (median ratio 0.96, above only
  41% of bars), so levels sit marginally closer and the n detector marginally
  more sensitive — the opposite direction from the intended widening.
- The only win is 2022 (+1.00 sum, DD 1.70 -> 1.58); in 2023-2025 EWMA loses
  on both gates (2023 sum 5.73 -> 4.44 with DD 0.41 -> 0.62; 2025 worst day
  -0.90 -> -1.22, DD 1.13 -> 1.44). Full-path sum 15.14 -> 13.91 and
  efficiency 8.47 -> 8.24 both fall on raw sums too, so the verdict does not
  hinge on renormalisation.
- Repro: `research/tournament/oc_ewmasig/{PLAN.md,ewma.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_ewmasig.py` (11 tests pass);
  one process, peak RAM ~0.5 GB (float32 1m arrays).

## Verdict
VERDICT: NOT PROMISING — EWMA sigma beats BASE on yearly sum in only 1/5 years and on maxDD in only 2/5 years, so the half-life-60 EWMA dip sigma is rejected and sigma360 stands.
