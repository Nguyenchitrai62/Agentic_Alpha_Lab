# oc_kpi REPORT — user goal metrics for the deployment pick R2B1D17BF (2026-10-05; PLAN pre-registered before any outcome)

REPORTING task (no selection rule, no verdict). Deployment pick R2B1D17BF =
registry v411 (dips x1.7 inv-rule corr_size, sleeve budget 0.26x1.7, bear-book
filter: BTC-open < rolling-1200-mean rows have positive book entries x0.5, R2
dip agents, v216 grid trade policy, win_start=5). Equity source of truth:
research/parallel/rounds/parallel-20260906-r2/v411/v411_runs.pkl (shifts
s=0..3, R2B1D17BF). The pkl holds only {t, eq, eq_min} (verified), so the
s=0..3 replicas were re-run with events/bars via run_kpi_trades.py (exact v411
worker, one process at a time); 4h-close equity matches the pkl to rel diff
0.0 (<= 1e-9) on all 10944 bars of every shift. Mix = v388.mix hourly +
reset_metric.year_reset (1/4-capital reset per anchor year), g1 = 2026-09-23
12:00 UTC. All five years are research data; findings need prospective
validation. Repro: research/tournament/oc_kpi/{PLAN.md,run_kpi.py,
run_kpi_trades.py,compute_kpi.py,results.json}; test
tests/test_tournament_oc_kpi.py.

## (1) Monthly returns of the continuous 4-phase mix, calendar months % (2021-09 partial from 09-24, 2026-09 partial to 09-23 12:00)

| month | % | month | % | month | % | month | % | month | % |
|---|---|---|---|---|---|---|---|---|---|
| 2021-09 | 0.00 | 2022-10 | 4.47 | 2023-11 | 21.76 | 2024-12 | 10.76 | 2026-01 | -2.04 |
| 2021-10 | 0.71 | 2022-11 | -2.47 | 2023-12 | 18.18 | 2025-01 | 9.05 | 2026-02 | 6.95 |
| 2021-11 | 0.82 | 2022-12 | 8.75 | 2024-01 | -7.50 | 2025-02 | 11.92 | 2026-03 | -1.50 |
| 2021-12 | 4.86 | 2023-01 | 29.50 | 2024-02 | 14.05 | 2025-03 | 9.36 | 2026-04 | 0.51 |
| 2022-01 | 10.07 | 2023-02 | -1.09 | 2024-03 | 16.02 | 2025-04 | -0.68 | 2026-05 | 7.25 |
| 2022-02 | 3.78 | 2023-03 | 5.98 | 2024-04 | -0.79 | 2025-05 | 9.72 | 2026-06 | 12.42 |
| 2022-03 | 2.18 | 2023-04 | -1.59 | 2024-05 | 0.09 | 2025-06 | -1.63 | 2026-07 | -7.07 |
| 2022-04 | 3.52 | 2023-05 | 3.05 | 2024-06 | -2.92 | 2025-07 | 14.99 | 2026-08 | 27.76 |
| 2022-05 | 0.55 | 2023-06 | -7.19 | 2024-07 | -3.23 | 2025-08 | 6.54 | 2026-09 | 8.44 |
| 2022-06 | 5.63 | 2023-07 | 17.71 | 2024-08 | 4.79 | 2025-09 | 9.83 | | |
| 2022-07 | 1.67 | 2023-08 | -6.39 | 2024-09 | -3.21 | 2025-10 | 4.98 | | |
| 2022-08 | 3.48 | 2023-09 | -5.16 | 2024-10 | 2.23 | 2025-11 | 4.52 | | |
| 2022-09 | -2.93 | 2023-10 | 19.52 | 2024-11 | 63.79 | 2025-12 | 1.52 | | |

Months >= +5%: 25/61 (41.0%; 24/59 = 40.7% on full months only). Months >= 0%:
44/61 (72.1%; 42/59 = 71.2% full only). Longest consecutive losing (< 0%)
streak: 2 months (never three in a row). Monthly compounding reproduces the
5y net exactly (residual 0.0).

## Per anchor year, reset metric (each sub-account restarts the year with 1/4 of capital)

| year | monthly geo mean R | DD 4h-close | DD 1m-marked |
|---|---|---|---|
| 2021-09-24 | 2.83 | 9.70 | 12.42 |
| 2022-09-24 | 3.51 | 15.43 | 16.23 |
| 2023-09-24 | 4.67 | 16.48 | 18.33 |
| 2024-09-24 | 11.27 | 6.58 | 8.26 |
| 2025-09-24 | 5.06 | 11.67 | 12.81 |

R and 1m DD match v411_result.json exactly. No losing year. Full path
(continuous mix, no reset): 4h-close DD 15.34, 1m-marked DD 16.90, gate
(max) 16.90; 5y net +2533.9% (26.34x).

## (2) Trade win rates after fees, pooled over the 4 phase sub-accounts (year = ENTRY time in anchor year)

Book = v213 position episodes (limit entry -> flat/sign-change: stop/TP/limit
close; maker entries/TP/close, taker stops; funding excluded). Rungs = FIFO
fill->exit pairs (engine ret already net of rung fees). All = book + rungs.

| year | book n / win | rungs n / win (sl/tp/timeout) | all n / win |
|---|---|---|---|
| 2021 | 934 / 0.500 | 4109 / 0.640 (208/1856/2045) | 5043 / 0.614 |
| 2022 | 870 / 0.516 | 4060 / 0.691 (242/2130/1688) | 4930 / 0.660 |
| 2023 | 880 / 0.511 | 4545 / 0.729 (287/2438/1820) | 5425 / 0.694 |
| 2024 | 1175 / 0.508 | 3946 / 0.725 (50/2090/1806) | 5121 / 0.675 |
| 2025 | 1096 / 0.537 | 4729 / 0.652 (137/2247/2345) | 5825 / 0.631 |
| pooled 5y | 4955 / 0.515 | 21389 / 0.687 (924/10761/9704) | 26344 / 0.655 |

Per shift: book win 0.513/0.506/0.522/0.519 (s=0..3), rung win
0.699/0.697/0.679/0.671, 0 unpaired exits, 4-5 book positions still open at
the live end (excluded, same as trade_stats). s=0 book episodes cross-check
vs v213.trade_stats dev+hidden: 0.5126 vs 0.5123 (rounding).

## (4) Open positions and gross exposure / equity (43,776 phase-bars; dip concurrency from rung [fill, exit) intervals)

- Book positions at 4h-bar ends: avg 2.65 coins of 5 open (per shift
  2.84/2.54/2.73/2.51), max 5.
- Book gross / equity per bar (|qty*open|/equity): avg 0.117 (per shift
  0.080/0.099/0.117/0.170), max 1.313 (per shift 0.665/0.640/0.832/1.313).
- Dip rungs: avg concurrent 0.097 rungs (notional 0.011 of equity), max
  concurrent 25 (s=0/1/2; 24 on s=3).
- Combined: avg 2.75 open positions; max 29 simultaneous (2023-12-11 02:13
  UTC); max combined gross 6.40 of equity (shift 3, 2025-08-14 12:34 UTC:
  book 0.12 + ~6.3 dip notional across ~13 low-sigma large-notional rungs;
  risk-budget binding is stop-distance based, liq count 0 on all shifts).

Summary: R2B1D17BF compounds 26.3x over the five years with no losing year or
3-month losing streak, full-path DD 16.9, book win rate 0.515 and all-trade
win rate 0.655; exposure averages 2.7 open positions at 0.13 of equity with
brief dip-driven gross spikes (max 6.4) that never liquidate.
