# oc_kpi_g2 REPORT — user goal metrics for R2B1D17BFG2, with R2B1D17BF next to it (2026-10-06; PLAN pre-registered before any outcome)

REPORTING task (no selection rule, no verdict). G2 = R2B1D17BFG2 = registry v421
(R2B1D17BF + dip gross-notional cap G = 2.0; see v421_gross_cap.py). BF = R2B1D17BF
oc_kpi numbers (research/tournament/oc_kpi/{REPORT.md,results.json}) repeated
verbatim as the neighbour column; G2 is computed by the exact oc_kpi scripts
(run_kpi.py from v421_runs.pkl, run_kpi_trades.py replicas + sleeve_gross_cap 2.0,
compute_kpi.py). Equity source of truth: research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl
(shifts s=0..3, R2B1D17BFG2, keys exactly {t,eq,eq_min}); s=0..3 replicas re-run
with events/bars one process at a time; 4h-close equity matches the pkl to rel
diff 0.0 (<= 1e-9) on all 10944 bars of every shift. Mix = v388.mix hourly +
reset_metric.year_reset (1/4-capital reset per anchor year), g1 = 2026-09-23
12:00 UTC. All five years are research data; findings need prospective
validation. Repro: research/tournament/oc_kpi_g2/{PLAN.md,run_kpi.py,
run_kpi_trades.py,compute_kpi.py,results.json,results_equity.json}; test
tests/test_tournament_oc_kpi_g2.py. results.json embeds the full BF results.json
as reference_BF.

## (1) Monthly returns of the continuous 4-phase mix, calendar months % (2021-09 partial from 09-24, 2026-09 partial to 09-23 12:00)

| month | G2 % | BF % | month | G2 % | BF % | month | G2 % | BF % | month | G2 % | BF % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2021-09 | 0.00 | 0.00 | 2022-12 | 8.71 | 8.75 | 2024-03 | 22.97 | 16.02 | 2025-06 | -1.63 | -1.63 |
| 2021-10 | 0.71 | 0.71 | 2023-01 | 28.43 | 29.50 | 2024-04 | -2.43 | -0.79 | 2025-07 | 14.32 | 14.99 |
| 2021-11 | 0.82 | 0.82 | 2023-02 | -1.07 | -1.09 | 2024-05 | -0.07 | 0.09 | 2025-08 | 1.74 | 6.54 |
| 2021-12 | 4.86 | 4.86 | 2023-03 | 5.43 | 5.98 | 2024-06 | -0.12 | -2.92 | 2025-09 | 8.40 | 9.83 |
| 2022-01 | 10.16 | 10.07 | 2023-04 | -2.98 | -1.59 | 2024-07 | -1.85 | -3.23 | 2025-10 | 4.77 | 4.98 |
| 2022-02 | 3.78 | 3.78 | 2023-05 | 3.03 | 3.05 | 2024-08 | 7.83 | 4.79 | 2025-11 | 4.55 | 4.52 |
| 2022-03 | 2.14 | 2.18 | 2023-06 | -7.17 | -7.19 | 2024-09 | -3.08 | -3.21 | 2025-12 | 1.54 | 1.52 |
| 2022-04 | 3.52 | 3.52 | 2023-07 | 17.72 | 17.71 | 2024-10 | 2.82 | 2.23 | 2026-01 | -2.19 | -2.04 |
| 2022-05 | 0.54 | 0.55 | 2023-08 | -6.27 | -6.39 | 2024-11 | 63.83 | 63.79 | 2026-02 | 7.04 | 6.95 |
| 2022-06 | 5.63 | 5.63 | 2023-09 | -5.25 | -5.16 | 2024-12 | 11.00 | 10.76 | 2026-03 | -1.47 | -1.50 |
| 2022-07 | 1.67 | 1.67 | 2023-10 | 17.62 | 19.52 | 2025-01 | 9.09 | 9.05 | 2026-04 | 0.51 | 0.51 |
| 2022-08 | 0.48 | 3.48 | 2023-11 | 21.22 | 21.76 | 2025-02 | 11.84 | 11.92 | 2026-05 | 7.01 | 7.25 |
| 2022-09 | -3.00 | -2.93 | 2023-12 | 17.24 | 18.18 | 2025-03 | 9.28 | 9.36 | 2026-06 | 12.34 | 12.42 |
| 2022-10 | 4.25 | 4.47 | 2024-01 | -4.76 | -7.50 | 2025-04 | -0.57 | -0.68 | 2026-07 | -7.06 | -7.07 |
| 2022-11 | -1.80 | -2.47 | 2024-02 | 19.15 | 14.05 | 2025-05 | 9.48 | 9.72 | 2026-08 | 23.52 | 27.76 |
| | | | | | | | | | 2026-09 | 7.95 | 8.44 |

G2 months >= +5%: 25/61 (41.0%; 24/59 = 40.7% on full months only). BF: 25/61
(41.0%; 24/59 = 40.7%). G2 months >= 0%: 43/61 (70.5%; 41/59 = 69.5% full only).
BF: 44/61 (72.1%; 42/59 = 71.2% full only). G2 longest consecutive losing (< 0%)
streak: 4 months (2024-04..2024-07). BF: 2 months (never three in a row).
Monthly compounding reproduces the 5y net exactly (G2 residual -3.6e-15, BF 1.4e-14).

## Per anchor year, reset metric (each sub-account restarts the year with 1/4 of capital)

| year | G2 monthly geo mean R | G2 DD 4h-close | G2 DD 1m-marked | BF R | BF DD 4h | BF DD 1m |
|---|---|---|---|---|---|---|
| 2021-09-24 | 2.59 | 9.70 | 10.86 | 2.83 | 9.70 | 12.42 |
| 2022-09-24 | 3.28 | 16.15 | 16.91 | 3.51 | 15.43 | 16.23 |
| 2023-09-24 | 6.05 | 14.13 | 15.81 | 4.67 | 16.48 | 18.33 |
| 2024-09-24 | 10.68 | 6.57 | 8.27 | 11.27 | 6.58 | 8.26 |
| 2025-09-24 | 4.65 | 11.77 | 12.90 | 5.06 | 11.67 | 12.81 |

G2 R and 1m DD match v421_result.json row R2B1D17BFG2 exactly
(2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27, 4.648/12.90). No losing year
for either. Full path (continuous mix, no reset): G2 4h-close DD 16.05, 1m-marked
DD 16.82, gate (max) 16.82; 5y net +2538.7% (26.39x). BF: 15.34 / 16.90 / 16.90;
+2533.9% (26.34x).

## (2) Trade win rates after fees, pooled over the 4 phase sub-accounts (year = ENTRY time in anchor year)

Book = v213 position episodes (limit entry -> flat/sign-change: stop/TP/limit
close; maker entries/TP/close, taker stops; funding excluded). Rungs = FIFO
fill->exit pairs (engine ret already net of rung fees). All = book + rungs.

| year | G2 book n / win | G2 rungs n / win (sl/tp/timeout) | G2 all n / win | BF book n / win | BF rungs n / win (sl/tp/timeout) | BF all n / win |
|---|---|---|---|---|---|---|
| 2021 | 932 / 0.500 | 4075 / 0.638 (208/1827/2040) | 5007 / 0.612 | 934 / 0.500 | 4109 / 0.640 (208/1856/2045) | 5043 / 0.614 |
| 2022 | 863 / 0.511 | 3941 / 0.689 (240/2055/1646) | 4804 / 0.657 | 870 / 0.516 | 4060 / 0.691 (242/2130/1688) | 4930 / 0.660 |
| 2023 | 1002 / 0.519 | 4979 / 0.732 (291/2670/2018) | 5981 / 0.696 | 880 / 0.511 | 4545 / 0.729 (287/2438/1820) | 5425 / 0.694 |
| 2024 | 1171 / 0.508 | 3847 / 0.719 (50/2011/1786) | 5018 / 0.670 | 1175 / 0.508 | 3946 / 0.725 (50/2090/1806) | 5121 / 0.675 |
| 2025 | 1096 / 0.537 | 4671 / 0.648 (137/2197/2337) | 5767 / 0.627 | 1096 / 0.537 | 4729 / 0.652 (137/2247/2345) | 5825 / 0.631 |
| pooled 5y | 5064 / 0.515 | 21513 / 0.686 (926/10760/9827) | 26577 / 0.653 | 4955 / 0.515 | 21389 / 0.687 (924/10761/9704) | 26344 / 0.655 |

G2 per shift: book win 0.516/0.505/0.527/0.513 (s=0..3), rung win
0.695/0.694/0.683/0.670, 0 unpaired exits, 4-5 book positions still open at
the live end per shift (18 pooled, excluded, same as trade_stats). BF per shift:
book 0.513/0.506/0.522/0.519, rung 0.699/0.697/0.679/0.671, 0 unpaired, 18 open.

## (4) Open positions and gross exposure / equity (43,776 phase-bars; dip concurrency from rung [fill, exit) intervals)

- G2 book positions at 4h-bar ends: avg 2.72 coins of 5 open (per shift
  2.89/2.68/2.85/2.45), max 5. BF: avg 2.65 (2.84/2.54/2.73/2.51), max 5.
- G2 book gross / equity per bar (|qty*open|/equity): avg 0.119 (per shift
  0.083/0.102/0.117/0.175), max 1.421 (per shift 0.665/0.638/0.832/1.421). BF:
  avg 0.117 (0.080/0.099/0.117/0.170), max 1.313.
- G2 dip rungs: avg concurrent 0.098 rungs (notional 0.011 of equity), max
  concurrent 25 (s=1/2; 23 on s=0, 24 on s=3). BF: avg 0.097 (notional 0.011),
  max 25.
- G2 combined: avg 2.81 open positions; max 29 simultaneous (2025-10-10 21:16
  UTC); max combined gross 3.01 of equity (shift 3, 2024-11-10 21:12 UTC;
  liq count 0 on all shifts). BF: avg 2.75; max 29 (2023-12-11); max combined
  gross 6.40 (shift 3, 2025-08-14: book 0.12 + ~6.3 dip notional; liq 0).

Summary: R2B1D17BFG2 compounds 26.4x over the five years with no losing year,
full-path DD 16.8, book win rate 0.515 and all-trade win rate 0.653, longest
monthly losing streak 4 (2024-04..07); the G=2.0 cap halves the worst combined
gross (3.0 vs BF 6.4) at a monthly-mean cost of -0.01 to -0.02 pp vs BF, exposure
averages 2.8 open positions at 0.13 of equity with no liquidation on any shift.
