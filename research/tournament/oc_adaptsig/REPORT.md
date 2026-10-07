# oc_adaptsig REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
BASE (sigma360: pct_change of 4h opens, rolling 360 std ddof=1 min 120, shift 1)
vs ADAPT (sigma_eff = max(sigma360, sigma42); sigma42 = same over last 42 bars
min 30, shift 1; both known at bar open). Rung levels, close-stop (4sg),
backstop (8sg) and TP (1.0sg) all use the arm's own sigma; n counts other
majors with C(T+m-1) <= O(T)*(1-2.5*sg_arm(T)) (F=2.5, v399-exact). B1 static
bid, fill on strict low < lv in live minutes 16..238, size 1/(1+n_fill);
D0-from-fill exits; maker 0.0002 / taker 0.00055; longs pay 0.0001 on settling
timeouts. Majors x R2 depths (2.5/3/3.5/4/5), bars with open in
[2021-09-24, 2026-09-24) (5 anchor years); 4h grid from 2020-08-01 00:00 UTC.
Weights w renormalised per year-arm to mean 1 (primary); daily sums by exit
date UTC; maxDD of cumulative daily-sum path from 0; E = S/maxDD. BASE fills
5498 = oc_b1deeper B1 to the tick per coin (1067/1126/952/1179/1174) - replica
validated. ADAPT fills 3852 (-30%: 782/833/680/768/789). Ledger checksum
8184b41252837c40. All 5 years are research data: a PROMISING result would still
need prospective validation (disclosed vs RULES.md hidden-year rule).

## Per-year BASE vs ADAPT (renormalised w; mean in bps, win = net>0 share)
| year | BASE n/mean/win/sum/raw/worst/DD/E | ADAPT n/mean/win/sum/raw/worst/DD/E |
|---|---|---|
| 2021 | 990/38.1/.688/3.887/2.388/-0.720/0.720/5.40 | 753/55.3/.685/3.919/2.419/-0.650/0.650/6.03 |
| 2022 | 1045/3.8/.695/0.272/0.183/-1.082/1.699/0.16 | 759/17.3/.688/2.205/1.522/-1.053/1.083/2.04 |
| 2023 | 1330/39.7/.773/5.725/3.810/-0.400/0.409/14.01 | 914/33.4/.748/3.790/2.562/-0.394/0.418/9.06 |
| 2024 | 989/41.1/.699/3.959/2.579/-0.332/0.332/11.92 | 684/53.3/.713/3.900/2.504/-0.219/0.219/17.85 |
| 2025 | 1144/13.4/.656/1.210/0.712/-0.903/1.130/1.07 | 742/14.1/.658/0.983/0.590/-1.009/1.045/0.94 |
| FULL | 5498/27.4/.705/15.138/—/-1.138/1.787/8.47 | 3852/34.3/.700/14.839/—/-1.124/1.156/12.84 |

## Adaptive share (coin-bars with sg42 > sg360, among BASE-tradable bars)
| year | coin_bars | frac sg42>sg360 | median sgeff/sg360 |
|---|---|---|---|
| 2021 | 10950 | 0.337 | 1.00 |
| 2022 | 10950 | 0.303 | 1.00 |
| 2023 | 10980 | 0.385 | 1.00 |
| 2024 | 10950 | 0.365 | 1.00 |
| 2025 | 10950 | 0.368 | 1.00 |
| FULL | 54780 | 0.351 | 1.00 |

## Named-bar checks (4h grid; sg in frac, fills = rung fills that bar)
- 2024-01-03 12:00 UTC bar (the crash bar): sg42 < sg360 on BTC (0.00818 vs
  0.00854), ETH (0.01007 vs 0.01055), SOL (0.01962 vs 0.02562), XRP (0.00793
  vs 0.01157) so sg_eff = sg360 = no adaptation; only BNB adapts (0.01666 vs
  0.01321, +26%). Fills BASE/ADAPT: BTC 4/4, ETH 5/5, SOL 3/3, BNB 5/4,
  XRP 5/5. The 7-day window is still calm at the open, so max() cannot widen
  into a same-bar jump. Post-crash 16:00 bar sg42 > sg360 (BTC/XRP/BNB).
- 2023-08-17 20:00 UTC bar (crash): sg42 < sg360 on ALL five coins (e.g. BTC
  0.00440 vs 0.00661, ETH 0.00510 vs 0.00715), fills 5/5 identical both arms.
  sg42 exceeds sg360 only from 2023-08-18 04:00+ (BTC 0.00816 vs 0.00701).
  Same mechanism: adaptation lags the jump by construction.
- 2024-03-05 16:00 UTC bar: adaptive ACTIVE - sg42 > sg360 on BTC (+19%,
  0.01167 vs 0.00981), ETH (+0.2%), SOL (+26%), XRP (+76%); BNB not (0.00874
  vs 0.00935). Fills 5/5 both arms (levels deeper, n lower under ADAPT). Next
  day 2024-03-06 12:00: sg42 ~1.7-2x sg360 (BTC 0.01961 vs 0.01120); BASE
  fills 3/2/1/2 (BTC/ETH/SOL/BNB/XRP) vs ADAPT 0/0/0/0/0 - adaptation dodges
  the post-crash chop entirely.

## Decision (PROMISING = maxDD not worse in >=4/5 yrs AND efficiency better-or-equal in >=4/5)
| check | score | pass? |
|---|---|---|
| DD_adapt <= DD_base | 4/5 (fail only 2023: 0.418 vs 0.409) | PART |
| E_adapt >= E_base | 3/5 (pass 2021/2022/2024; fail 2023, 2025) | NO |
| PROMISING | | NO |

## Notes
- ADAPT raises per-fill quality (full mean 27.4 -> 34.3 bps) and cuts full-path
  DD 1.79 -> 1.16 (+52% full efficiency 8.47 -> 12.84), driven by 2022
  (+1.93 sum, DD 1.70 -> 1.08) and 2024 (DD 0.33 -> 0.22, E 11.9 -> 17.8).
- But it misses ~30% of fills, many winners: yearly sum loses in 4/5 years on
  raw sums too (2023 -1.25 raw, 2025 -0.12 raw), and the crash year 2023 fails
  both gates (sum 5.73 -> 3.79, DD slightly worse). The max() rule is stale
  exactly when needed (2024-01-03, 2023-08-17 pre-crash sg42 < sg360) and only
  bites after the loss is booked.
- Repro: `research/tournament/oc_adaptsig/{PLAN.md,adapt.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_adaptsig.py` (12 tests pass);
  one process, peak RAM ~0.5 GB (float32 1m arrays).

## Verdict
VERDICT: NOT PROMISING — vol-adaptive sigma cuts maxDD in 4/5 years but improves efficiency in only 3/5 years, so max(sigma360, sigma42) is rejected and sigma360 stands.
