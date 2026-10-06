# oc_stoptf REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
Stop-TIMEFRAME counterfactuals on dip rungs (idea #72): D0 = deployed
close5 stop, S15 = close15 stop ((m+1)%15==0 on the bar clock = absolute
15m closes, base%15==0 all phases), S1 = every-1m-close stop. Stop LEVEL
(4sg below fill), 8sg backstop on 1m lows, TP 1sg, timeout at next-bar
open, fees (maker 0.0002 / taker 0.00055), v293 settle funding and
stop-first priority all identical to the oc_dipexit D0 replica; fills are
identical across variants by construction (same lv fill rule). B1 sizes
w = 1/(1+n_fill) (oc_b1deeper-exact n), raw w*y sums, no renormalisation.
Majors x R2 depths (2.5/3/3.5/4/5), 4 clock phases (4h grid +0/1/2/3h),
bars with open in [2021-09-24, 2026-09-24) (5 anchor years). Paired rungs
(kept only if D0+S15+S1 all finite): 22312 (phase0 = 5498 = dipexit count
to the tick per coin 1067/1126/952/1179/1174; phase-0 D0 raw sums
2.388/0.183/3.810/2.579/0.712 = oc_b1deeper B1 raw sums 2.39/0.18/3.81/
2.58/0.71 — replica validated). Daily sums by exit date UTC; maxDD of the
cumulative daily-sum path from 0 (w*y units). All 5 years are research
data: a PROMISING variant would still need prospective validation
(disclosed vs RULES.md hidden-year rule).

## 4-phase means per year (S = mean_p sum(w*y); n/win/stop/W/DD = means across p)
| year | D0 S/n/win/stop_n/stopbps/W/DD | S15 S/stop_n/stopbps/W/DD | S1 S/stop_n/stopbps/W/DD |
|---|---|---|---|
| 2021 | 0.911/1042.8/.660/41.0/-757/-0.740/0.856 | 0.868/23.3/-742/-0.920/0.956 | 1.014/56.0/-701/-0.671/0.762 |
| 2022 | 0.833/1014.8/.699/40.5/-768/-0.726/0.951 | 0.919/29.3/-838/-0.730/0.978 | 0.850/65.5/-690/-0.644/0.851 |
| 2023 | 2.100/1338.0/.748/51.0/-629/-0.735/0.800 | 2.419/24.8/-555/-0.574/0.656 | 1.764/98.8/-628/-0.574/0.697 |
| 2024 | 3.197/989.5/.734/10.8/-736/-0.274/0.355 | 3.204/4.3/-891/-0.321/0.402 | 3.148/13.3/-759/-0.264/0.345 |
| 2025 | 0.677/1193.0/.661/20.0/-629/-0.508/0.607 | 0.899/10.0/-510/-0.494/0.593 | 0.572/40.3/-553/-0.422/0.616 |

Per-phase D0 sums (p0/p1/p2/p3): 2021 2.388/0.916/0.733/-0.392;
2022 0.183/1.374/1.313/0.461; 2023 3.810/1.591/2.546/0.453;
2024 2.579/3.219/3.497/3.495; 2025 0.712/0.440/0.676/0.881.
(S15: 2021 2.335/0.877/0.730/-0.471; 2022 0.406/1.285/1.337/0.648;
2023 3.772/2.040/2.924/0.942; 2024 2.833/3.046/3.435/3.503;
2025 0.873/0.730/0.831/1.164. S1: 2021 2.249/0.910/1.005/-0.108;
2022 0.177/1.410/1.461/0.352; 2023 3.261/1.395/1.991/0.410;
2024 2.603/3.200/3.485/3.306; 2025 0.702/0.228/0.687/0.670.)

## Cascade table: pooled-across-phases daily w*y on the 10 worst D0 days
| date | D0 | S15 | S1 |
|---|---|---|---|
| 2023-08-17 | -2.883 | -2.883 | -2.576 |
| 2021-12-04 | -2.870 | -3.679 | -2.682 |
| 2024-04-13 | -2.331 | -1.510 | -1.729 |
| 2024-01-03 | -2.291 | -1.687 | -1.770 |
| 2022-05-11 | -2.126 | -2.364 | -1.928 |
| 2025-10-10 | -2.034 | -1.977 | -1.632 |
| 2023-06-10 | -1.534 | -1.531 | -1.035 |
| 2022-11-08 | -0.921 | -0.934 | -0.910 |
| 2023-06-05 | -0.802 | -0.982 | -0.731 |
| 2024-08-05 | -0.780 | -0.774 | -0.817 |

## Decision (PROMISING = 4-phase-mean sum >= D0 in >=4/5 yrs AND maxDD not worse by >1pp in >=4/5)
| variant | years sum >= D0 | years DD not worse +0.01 | verdict |
|---|---|---|---|
| S15 close15 | 4/5 (all but 2021) | 2/5 (worse 2021 +0.100, 2022 +0.027, 2024 +0.047) | NOT PROMISING |
| S1 close1 | 2/5 (only 2021, 2022) | 5/5 | NOT PROMISING |

## Notes
- S15 halves stop count (fewer, mostly smaller stops: -555 vs -629 bps in
  2023) and mitigates some cascade days (2024-04-13: -1.51 vs -2.33;
  2024-01-03: -1.69 vs -2.29) but concentrates tail: worst-mean-day worse
  in 2021 (-0.92 vs -0.74) with one pooled day far worse (2021-12-04:
  -3.68 vs -2.87), so full-path DD rises in 3/5 years.
- S1 fires ~1.5-2x more stops at slightly smaller size (-690 vs -768 bps
  in 2022) and softens most cascade days, but bleeds in 2023/2024/2025
  (whipsawed exits in trends) and loses the sum test 3/5 years.
- Repro: research/tournament/oc_stoptf/{PLAN.md,stoptf.py,run.py,
  results.json,fills.parquet} + tests/test_oc_stoptf.py (14 tests pass);
  one process, majors 1m O/C float32 + one-coin H/L loop.

## Verdict
VERDICT: Neither stop timeframe is PROMISING — S15 wins sums 4/5 but worsens DD in 3/5, S1 holds DD 5/5 but wins sums only 2/5 — so the deployed close5 stop stands.
