# oc_kpi_d13 REPORT — user goal metrics for R2B1D13BF, with R2B1D17BFG2 (G2) next to it (2026-10-06; PLAN pre-registered before any outcome)

REPORTING task (no selection rule, no verdict). D13 = R2B1D13BF = registry v424
(dips x1.3 inv-rule corr_size F=2.5, sleeve_risk_budget 0.26*1.3, bear-book filter,
no gross cap, no rung drop; see v424_stretch_combo.py RUNS["R2B1D13BF"]). G2 =
R2B1D17BFG2 oc_kpi_g2 numbers (research/tournament/oc_kpi_g2/{REPORT.md,results.json})
repeated verbatim as the neighbour column; D13 is computed by the exact oc_kpi_g2
scripts (run_kpi.py from v424_runs.pkl, run_kpi_trades.py replicas kd=1.3 without
the sleeve_gross_cap line, compute_kpi.py). Equity source of truth:
research/parallel/rounds/parallel-20260906-r2/v424/v424_runs.pkl
(shifts s=0..3, R2B1D13BF, keys exactly {t,eq,eq_min}); s=0..3 replicas re-run
with events/bars one process at a time; 4h-close equity matches the pkl to rel
diff 0.0 (<= 1e-9) on all 10944 bars of every shift. Mix = v388.mix hourly +
reset_metric.year_reset (1/4-capital reset per anchor year), g1 = 2026-09-23
12:00 UTC. All five years are research data; findings need prospective
validation. Repro: research/tournament/oc_kpi_d13/{PLAN.md,run_kpi.py,
run_kpi_trades.py,compute_kpi.py,results.json,results_equity.json}; test
tests/test_tournament_oc_kpi_d13.py. results.json embeds the full G2 results.json
as reference_G2.

## (1) Monthly returns of the continuous 4-phase mix, calendar months % (2021-09 partial from 09-24, 2026-09 partial to 09-23 12:00)

| month | D13 % | G2 % | month | D13 % | G2 % | month | D13 % | G2 % | month | D13 % | G2 % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2021-09 | 0.00 | 0.00 | 2022-12 | 8.24 | 8.71 | 2024-03 | 18.62 | 22.97 | 2025-06 | -2.01 | -1.63 |
| 2021-10 | 0.67 | 0.71 | 2023-01 | 26.43 | 28.43 | 2024-04 | -2.70 | -2.43 | 2025-07 | 12.66 | 14.32 |
| 2021-11 | 0.24 | 0.82 | 2023-02 | -0.89 | -1.07 | 2024-05 | -0.61 | -0.07 | 2025-08 | 4.90 | 1.74 |
| 2021-12 | 5.13 | 4.86 | 2023-03 | 5.15 | 5.43 | 2024-06 | -0.52 | -0.12 | 2025-09 | 8.71 | 8.40 |
| 2022-01 | 7.54 | 10.16 | 2023-04 | -1.52 | -2.98 | 2024-07 | -3.04 | -1.85 | 2025-10 | 5.45 | 4.77 |
| 2022-02 | 2.82 | 3.78 | 2023-05 | 1.75 | 3.03 | 2024-08 | 7.09 | 7.83 | 2025-11 | 4.13 | 4.55 |
| 2022-03 | 1.30 | 2.14 | 2023-06 | -4.95 | -7.17 | 2024-09 | -3.63 | -3.08 | 2025-12 | 1.66 | 1.54 |
| 2022-04 | 2.17 | 3.52 | 2023-07 | 16.70 | 17.72 | 2024-10 | 1.13 | 2.82 | 2026-01 | -1.46 | -2.19 |
| 2022-05 | 2.46 | 0.54 | 2023-08 | -5.10 | -6.27 | 2024-11 | 58.37 | 63.83 | 2026-02 | 6.72 | 7.04 |
| 2022-06 | 5.15 | 5.63 | 2023-09 | -5.91 | -5.25 | 2024-12 | 9.62 | 11.00 | 2026-03 | -1.56 | -1.47 |
| 2022-07 | 3.35 | 1.67 | 2023-10 | 15.57 | 17.62 | 2025-01 | 5.87 | 9.09 | 2026-04 | 0.53 | 0.51 |
| 2022-08 | 1.90 | 0.48 | 2023-11 | 17.67 | 21.22 | 2025-02 | 9.66 | 11.84 | 2026-05 | 6.16 | 7.01 |
| 2022-09 | -2.86 | -3.00 | 2023-12 | 14.22 | 17.24 | 2025-03 | 8.36 | 9.28 | 2026-06 | 11.26 | 12.34 |
| 2022-10 | 3.63 | 4.25 | 2024-01 | -5.25 | -4.76 | 2025-04 | -0.48 | -0.57 | 2026-07 | -7.02 | -7.06 |
| 2022-11 | -1.98 | -1.80 | 2024-02 | 16.81 | 19.15 | 2025-05 | 9.51 | 9.48 | 2026-08 | 24.58 | 23.52 |
| | | | | | | | | | 2026-09 | 7.36 | 7.95 |

D13 months >= +5%: 27/61 (44.3%; 26/59 = 44.1% on full months only). G2: 25/61
(41.0%; 24/59 = 40.7%). D13 months >= 0%: 43/61 (70.5%; 41/59 = 69.5% full only).
G2: 43/61 (70.5%; 41/59 = 69.5% full only). D13 longest consecutive losing (< 0%)
streak: 4 months (2024-04..2024-07). G2: 4 months (2024-04..2024-07).
Monthly compounding reproduces the 5y net exactly (D13 residual 7.1e-15, G2 -3.6e-15).

## Per anchor year, reset metric (each sub-account restarts the year with 1/4 of capital)

| year | D13 monthly geo mean R | D13 DD 4h-close | D13 DD 1m-marked | G2 R | G2 DD 4h | G2 DD 1m |
|---|---|---|---|---|---|---|
| 2021-09-24 | 2.49 | 9.46 | 10.21 | 2.59 | 9.70 | 10.86 |
| 2022-09-24 | 3.29 | 14.17 | 14.98 | 3.28 | 16.15 | 16.91 |
| 2023-09-24 | 4.98 | 13.11 | 14.76 | 6.05 | 14.13 | 15.81 |
| 2024-09-24 | 9.53 | 6.59 | 7.33 | 10.68 | 6.57 | 8.27 |
| 2025-09-24 | 4.72 | 9.98 | 10.97 | 4.65 | 11.77 | 12.90 |

D13 R and 1m DD match v424_result.json row R2B1D13BF exactly
(2.485/10.21, 3.286/14.98, 4.975/14.76, 9.526/7.33, 4.723/10.97). No losing year
for either. Full path (continuous mix, no reset): D13 4h-close DD 14.07, 1m-marked
DD 14.86, gate (max) 14.86; 5y net +1852.9% (19.53x). G2: 16.05 / 16.82 / 16.82;
+2538.7% (26.39x).

## (2) Trade win rates after fees, pooled over the 4 phase sub-accounts (year = ENTRY time in anchor year)

Book = v213 position episodes (limit entry -> flat/sign-change: stop/TP/limit
close; maker entries/TP/close, taker stops; funding excluded). Rungs = FIFO
fill->exit pairs (engine ret already net of rung fees). All = book + rungs.

| year | D13 book n / win | D13 rungs n / win (sl/tp/timeout) | D13 all n / win | G2 book n / win | G2 rungs n / win (sl/tp/timeout) | G2 all n / win |
|---|---|---|---|---|---|---|
| 2021 | 951 / 0.505 | 4109 / 0.640 (208/1856/2045) | 5060 / 0.615 | 932 / 0.500 | 4075 / 0.638 (208/1827/2040) | 5007 / 0.612 |
| 2022 | 873 / 0.518 | 4060 / 0.691 (242/2130/1688) | 4933 / 0.661 | 863 / 0.511 | 3941 / 0.689 (240/2055/1646) | 4804 / 0.657 |
| 2023 | 1087 / 0.519 | 5354 / 0.737 (320/2924/2110) | 6441 / 0.700 | 1002 / 0.519 | 4979 / 0.732 (291/2670/2018) | 5981 / 0.696 |
| 2024 | 1175 / 0.503 | 3946 / 0.725 (50/2090/1806) | 5121 / 0.674 | 1171 / 0.508 | 3847 / 0.719 (50/2011/1786) | 5018 / 0.670 |
| 2025 | 1122 / 0.536 | 4729 / 0.652 (137/2247/2345) | 5851 / 0.630 | 1096 / 0.537 | 4671 / 0.648 (137/2197/2337) | 5767 / 0.627 |
| pooled 5y | 5208 / 0.516 | 22198 / 0.690 (957/11247/9994) | 27406 / 0.657 | 5064 / 0.515 | 21513 / 0.686 (926/10760/9827) | 26577 / 0.653 |

D13 per shift: book win 0.517/0.504/0.523/0.519 (s=0..3), rung win
0.699/0.697/0.686/0.680, 0 unpaired exits, 4-5 book positions still open at
the live end per shift (18 pooled, excluded, same as trade_stats). G2 per shift:
book 0.516/0.505/0.527/0.513, rung 0.695/0.694/0.683/0.670, 0 unpaired, 18 open.

## (4) Open positions and gross exposure / equity (43,776 phase-bars; dip concurrency from rung [fill, exit) intervals)

- D13 book positions at 4h-bar ends: avg 2.79 coins of 5 open (per shift
  2.89/2.75/2.84/2.69), max 5. G2: avg 2.72 (2.89/2.68/2.85/2.45), max 5.
- D13 book gross / equity per bar (|qty*open|/equity): avg 0.127 (per shift
  0.097/0.113/0.125/0.175), max 1.144 (per shift 0.735/0.727/0.853/1.144). G2:
  avg 0.119 (0.083/0.102/0.117/0.175), max 1.421.
- D13 dip rungs: avg concurrent 0.100 rungs (notional 0.0089 of equity), max
  concurrent 25 (s=0/1/2; 24 on s=3). G2: avg 0.098 (notional 0.011),
  max 25.
- D13 combined: avg 2.89 open positions; max 29 simultaneous (2023-12-11 02:13
  UTC); max combined gross 4.92 of equity (shift 3, 2025-08-14 12:34 UTC;
  liq count 0 on all shifts). G2: avg 2.81; max 29 (2025-10-10); max combined
  gross 3.01 (shift 3, 2024-11-10; liq 0).

Summary: R2B1D13BF compounds 19.5x over the five years with no losing year,
full-path DD 14.9, book win rate 0.516 and all-trade win rate 0.657, longest
monthly losing streak 4 (2024-04..07); against G2 it trades 0.8x the dip size at
a 5y monthly-mean cost of about -0.5 pp, with lower full-path DD (14.9 vs 16.8)
and a higher worst combined gross peak (4.9 vs 3.0, both on one 2025-08 bar),
exposure averages 2.9 open positions at 0.14 of equity with no liquidation on any shift.
