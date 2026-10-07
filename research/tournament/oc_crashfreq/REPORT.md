# oc_crashfreq REPORT - one-bar dip crashes, all four phases (2026-10-05; PLAN pre-registered)

## Setup
R2B1D17BF replicas (oc_ddanat4p s0..s3, live 2021-09-24..2026-09-23; 1m/hourly read to 2026-09-24 00:00 UTC; all five years research data, prospective validation still needed). Per-phase 4h bars (hour%4==s%4); dip_loss(s,T)=100*sum(weight*ret) over rung exits with exit_t in (T-4h,T], by exit kind; BTC 4h = hourly C(T-1h)/C(T-5h)-1; others = wall-clock (T-4h,T] rung sums per other phase. Repro: research/tournament/oc_crashfreq/{PLAN.md,compute_crashfreq.py,make_report.py,results.json,REPORT.md}. No post-hoc definition changes.

N>=3% one-bar dip losses: 82 (phase-bars over 10956 grid bars/phase x4). Negative-bar dip sum -869.2pp over 840 bars; top-10 carry 15.9%.

## Counts per anchor year (>=3 / 5 / 10 / 15% one-bar dip loss, all phases pooled)
| year | >=3% | >=5% | >=10% | >=15% |
|---|---|---|---|---|
| 2021-09-24..2022-09-24 | 22 | 10 | 1 | 0 |
| 2022-09-24..2023-09-24 | 24 | 7 | 1 | 0 |
| 2023-09-24..2024-09-24 | 21 | 11 | 7 | 3 |
| 2024-09-24..2025-09-24 | 7 | 2 | 0 | 0 |
| 2025-09-24..2026-09-24 | 8 | 3 | 0 | 0 |

Per phase >=3/5/10/15: s0 18/5/1/0; s1 19/10/3/1; s2 21/9/1/1; s3 24/9/4/1.

## Largest 15 one-bar dip losses
| # | bar_end UTC | s | dip% | stops/exits | sl/tp/to | BTC4h% | others>=3% | coins (pp, worst first) |
|---|---|---|---|---|---|---|---|---|
| 1 | 2024-01-03 14:00 | 2 | -21.70 | 22/25 | sl -22.1 / tp 0.43 / to 0.00 | -6.24 | s1,s3 | BTC -7.1, ETH -4.6, XRP -4.5, SOL -3.5, BNB -1.9 |
| 2 | 2024-01-03 15:00 | 3 | -21.01 | 22/25 | sl -21.4 / tp 0.41 / to 0.00 | -6.58 | s1,s2 | BTC -7.3, ETH -5.0, BNB -3.3, XRP -2.8, SOL -2.6 |
| 3 | 2024-01-03 13:00 | 1 | -17.47 | 18/25 | sl -18.3 / tp 0.81 / to 0.00 | -5.37 | s2,s3 | BTC -7.0, ETH -4.7, SOL -3.1, XRP -2.2, BNB -0.5 |
| 4 | 2023-08-18 01:00 | 1 | -13.25 | 19/25 | sl -13.7 / tp 0.35 / to 0.10 | -3.40 | s0,s2,s3 | ETH -7.4, XRP -3.9, BTC -1.3, BNB -1.1, SOL 0.4 |
| 5 | 2024-03-05 21:00 | 1 | -13.09 | 15/25 | sl -10.3 / tp 0.44 / to -3.20 | -5.59 | - | ETH -4.2, XRP -2.8, BTC -2.6, BNB -1.9, SOL -1.6 |
| 6 | 2024-06-07 20:00 | 0 | -11.14 | 5/21 | sl -13.5 / tp 1.93 / to 0.45 | -2.62 | s3 | XRP -13.5, BTC 0.1, BNB 0.6, ETH 0.7, SOL 1.0 |
| 7 | 2024-04-13 23:00 | 3 | -10.90 | 17/25 | sl -11.1 / tp 0.22 / to 0.02 | -4.31 | s1,s2 | BNB -5.3, SOL -2.1, ETH -1.2, BTC -1.2, XRP -1.1 |
| 8 | 2024-06-07 19:00 | 3 | -10.75 | 5/23 | sl -10.8 / tp 0.65 / to -0.56 | -3.19 | s0,s1 | XRP -10.8, BNB -0.2, BTC 0.0, SOL 0.0, ETH 0.3 |
| 9 | 2021-12-04 07:00 | 3 | -10.64 | 18/25 | sl -11.1 / tp 0.52 / to -0.03 | -10.64 | s2 | BNB -3.5, XRP -3.3, ETH -2.7, BTC -1.1, SOL -0.0 |
| 10 | 2025-10-11 01:00 | 1 | -8.06 | 23/25 | sl -8.1 / tp 0.04 / to 0.00 | -1.52 | s0,s2,s3 | BNB -3.2, SOL -2.9, BTC -1.2, XRP -0.6, ETH -0.2 |
| 11 | 2022-05-11 13:00 | 1 | -7.79 | 14/25 | sl -7.4 / tp 0.30 / to -0.73 | -6.68 | s0,s2,s3 | SOL -4.4, XRP -1.6, BNB -0.9, ETH -0.4, BTC -0.4 |
| 12 | 2024-02-28 21:00 | 1 | -7.69 | 4/25 | sl -11.2 / tp 3.59 / to -0.11 | -3.30 | s0 | XRP -11.0, BNB 0.4, ETH 0.8, BTC 0.8, SOL 1.4 |
| 13 | 2024-04-13 22:00 | 2 | -7.41 | 7/25 | sl -8.3 / tp 1.38 / to -0.50 | -5.74 | s1,s3 | BNB -7.1, XRP -0.7, BTC -0.4, ETH -0.1, SOL 0.9 |
| 14 | 2021-12-04 06:00 | 2 | -7.36 | 15/25 | sl -7.9 / tp 0.46 / to 0.08 | -10.35 | s0,s3 | XRP -3.3, BNB -2.2, ETH -1.3, BTC -1.0, SOL 0.4 |
| 15 | 2025-10-10 22:00 | 2 | -7.32 | 16/25 | sl -8.0 / tp 0.71 / to 0.00 | -3.69 | s0,s1,s3 | BTC -2.9, SOL -1.6, ETH -1.2, BNB -1.1, XRP -0.4 |

## Concentration
Sum over all negative (s,T) bars: -869.2pp (840 bars). Top-10 most-negative bars sum -138.0pp = 15.9% of all dip-sleeve losses. Tail is concentrated but not single-event dominated outside the 2024-01-03 trio (top 3 = -60.2pp, 6.9% of the negative sum).

## All 82 bars with dip_loss <= -3% (sorted worst first)
| bar_end UTC | s | dip% | stops/exits | sl/tp/to | BTC4h% | others>=3% (wall sums) | coins |
|---|---|---|---|---|---|---|---|
| 2024-01-03 14:00 | 2 | -21.70 | 22/25 | sl -22.1 / tp 0.43 / to 0.00 | -6.24 | s1:-17.2,s3:-21.0 | BTC -7.1, ETH -4.6, XRP -4.5, SOL -3.5, BNB -1.9 |
| 2024-01-03 15:00 | 3 | -21.01 | 22/25 | sl -21.4 / tp 0.41 / to 0.00 | -6.58 | s1:-16.8,s2:-21.4 | BTC -7.3, ETH -5.0, BNB -3.3, XRP -2.8, SOL -2.6 |
| 2024-01-03 13:00 | 1 | -17.47 | 18/25 | sl -18.3 / tp 0.81 / to 0.00 | -5.37 | s2:-21.7,s3:-21.0 | BTC -7.0, ETH -4.7, SOL -3.1, XRP -2.2, BNB -0.5 |
| 2023-08-18 01:00 | 1 | -13.25 | 19/25 | sl -13.7 / tp 0.35 / to 0.10 | -3.40 | s0:-7.3,s2:-5.7,s3:-4.0 | ETH -7.4, XRP -3.9, BTC -1.3, BNB -1.1, SOL 0.4 |
| 2024-03-05 21:00 | 1 | -13.09 | 15/25 | sl -10.3 / tp 0.44 / to -3.20 | -5.59 | - (max s2:0.0) | ETH -4.2, XRP -2.8, BTC -2.6, BNB -1.9, SOL -1.6 |
| 2024-06-07 20:00 | 0 | -11.14 | 5/21 | sl -13.5 / tp 1.93 / to 0.45 | -2.62 | s3:-10.7 | XRP -13.5, BTC 0.1, BNB 0.6, ETH 0.7, SOL 1.0 |
| 2024-04-13 23:00 | 3 | -10.90 | 17/25 | sl -11.1 / tp 0.22 / to 0.02 | -4.31 | s1:-3.3,s2:-7.4 | BNB -5.3, SOL -2.1, ETH -1.2, BTC -1.2, XRP -1.1 |
| 2024-06-07 19:00 | 3 | -10.75 | 5/23 | sl -10.8 / tp 0.65 / to -0.56 | -3.19 | s0:-11.8,s1:-4.3 | XRP -10.8, BNB -0.2, BTC 0.0, SOL 0.0, ETH 0.3 |
| 2021-12-04 07:00 | 3 | -10.64 | 18/25 | sl -11.1 / tp 0.52 / to -0.03 | -10.64 | s2:-7.1 | BNB -3.5, XRP -3.3, ETH -2.7, BTC -1.1, SOL -0.0 |
| 2025-10-11 01:00 | 1 | -8.06 | 23/25 | sl -8.1 / tp 0.04 / to 0.00 | -1.52 | s0:-3.9,s2:-6.7,s3:-6.6 | BNB -3.2, SOL -2.9, BTC -1.2, XRP -0.6, ETH -0.2 |
| 2022-05-11 13:00 | 1 | -7.79 | 14/25 | sl -7.4 / tp 0.30 / to -0.73 | -6.68 | s0:-4.4,s2:-3.3,s3:-6.8 | SOL -4.4, XRP -1.6, BNB -0.9, ETH -0.4, BTC -0.4 |
| 2024-02-28 21:00 | 1 | -7.69 | 4/25 | sl -11.2 / tp 3.59 / to -0.11 | -3.30 | s0:-4.1 | XRP -11.0, BNB 0.4, ETH 0.8, BTC 0.8, SOL 1.4 |
| 2024-04-13 22:00 | 2 | -7.41 | 7/25 | sl -8.3 / tp 1.38 / to -0.50 | -5.74 | s1:-3.3,s3:-10.1 | BNB -7.1, XRP -0.7, BTC -0.4, ETH -0.1, SOL 0.9 |
| 2021-12-04 06:00 | 2 | -7.36 | 15/25 | sl -7.9 / tp 0.46 / to 0.08 | -10.35 | s0:-3.0,s3:-10.7 | XRP -3.3, BNB -2.2, ETH -1.3, BTC -1.0, SOL 0.4 |
| 2025-10-10 22:00 | 2 | -7.32 | 16/25 | sl -8.0 / tp 0.71 / to 0.00 | -3.69 | s0:-3.1,s1:-9.5,s3:-8.3 | BTC -2.9, SOL -1.6, ETH -1.2, BNB -1.1, XRP -0.4 |
| 2023-08-18 00:00 | 0 | -7.15 | 21/25 | sl -7.4 / tp 0.20 / to 0.00 | -4.59 | s1:-13.2,s2:-5.6,s3:-3.9 | ETH -2.6, XRP -1.7, BTC -1.3, BNB -1.0, SOL -0.5 |
| 2024-11-12 13:00 | 1 | -6.87 | 5/25 | sl -4.6 / tp 1.36 / to -3.64 | -3.37 | - (max s0:2.7) | XRP -3.7, SOL -2.1, BNB -0.8, ETH -0.3, BTC 0.1 |
| 2023-11-09 19:00 | 3 | -6.87 | 5/20 | sl -3.2 / tp 0.19 / to -3.81 | -4.03 | - (max s2:3.0) | SOL -2.6, XRP -2.6, BTC -1.3, BNB -0.3 |
| 2025-10-10 23:00 | 3 | -6.77 | 17/25 | sl -7.3 / tp 0.51 / to 0.00 | -3.05 | s0:-3.1,s1:-9.5,s2:-6.2 | SOL -1.8, BNB -1.6, BTC -1.5, ETH -1.2, XRP -0.7 |
| 2022-05-11 15:00 | 3 | -6.68 | 19/25 | sl -7.3 / tp 0.67 / to 0.00 | -0.06 | s0:-4.0,s1:-7.8,s2:-3.0 | SOL -3.2, BNB -1.7, XRP -1.1, ETH -0.4, BTC -0.3 |
| 2022-11-08 21:00 | 1 | -6.18 | 16/25 | sl -7.1 / tp 0.91 / to 0.00 | -10.94 | - (max s0:-0.2) | SOL -3.4, BTC -1.3, ETH -0.7, BNB -0.5, XRP -0.3 |
| 2022-05-12 06:00 | 2 | -6.01 | 16/25 | sl -6.4 / tp 0.58 / to -0.21 | -7.18 | s1:-4.6 | BNB -2.6, XRP -1.8, ETH -1.6, BTC -0.5, SOL 0.4 |
| 2023-04-19 10:00 | 2 | -5.97 | 0/23 | sl 0.0 / tp 1.48 / to -7.45 | -3.53 | - (max s3:3.2) | XRP -3.4, ETH -1.5, BNB -0.8, SOL -0.2, BTC -0.1 |
| 2022-09-19 00:00 | 0 | -5.93 | 2/6 | sl -3.8 / tp 0.52 / to -2.65 | -1.58 | s3:-4.8 | XRP -6.0, BNB 0.1 |
| 2021-11-10 22:00 | 2 | -5.92 | 7/25 | sl -6.1 / tp 0.71 / to -0.54 | -6.41 | s3:-4.1 | XRP -5.0, BTC -0.7, BNB -0.3, ETH -0.2, SOL 0.3 |
| 2024-07-05 06:00 | 2 | -5.90 | 12/24 | sl -5.9 / tp 0.17 / to -0.21 | -4.16 | s0:-3.3,s1:-3.9 | BNB -4.0, XRP -1.5, ETH -0.4, BTC -0.1, SOL 0.1 |
| 2022-05-11 21:00 | 1 | -5.76 | 6/24 | sl -5.4 / tp 0.62 / to -0.99 | -6.14 | s2:-4.5,s3:-3.4 | SOL -4.7, XRP -0.8, BNB -0.3, ETH -0.2, BTC 0.3 |
| 2023-08-17 22:00 | 2 | -5.62 | 19/25 | sl -5.8 / tp 0.17 / to -0.03 | -6.14 | s0:-7.2,s1:-13.5,s3:-4.1 | ETH -2.1, XRP -1.3, BNB -1.0, BTC -0.6, SOL -0.6 |
| 2023-06-05 19:00 | 3 | -5.24 | 9/25 | sl -5.3 / tp 0.87 / to -0.84 | -4.61 | s1:-4.4,s2:-4.7 | BNB -3.3, XRP -0.9, SOL -0.7, BTC -0.4, ETH 0.1 |
| 2024-12-03 16:00 | 0 | -5.21 | 3/11 | sl -6.7 / tp 1.44 / to 0.00 | 0.73 | - (max s3:4.4) | XRP -5.7, ETH 0.0, SOL 0.2, BNB 0.2 |
| 2022-01-24 11:00 | 3 | -5.20 | 0/18 | sl 0.0 / tp 0.30 / to -5.50 | -5.63 | - (max s1:0.8) | ETH -3.8, BNB -1.0, XRP -0.2, BTC -0.2, SOL -0.0 |
| 2023-04-26 20:00 | 0 | -5.08 | 0/22 | sl 0.0 / tp 0.00 / to -5.08 | -6.48 | - (max s3:0.5) | BTC -1.9, ETH -1.8, BNB -0.7, XRP -0.4, SOL -0.2 |
| 2022-05-12 05:00 | 1 | -5.07 | 14/25 | sl -5.3 / tp 0.85 / to -0.57 | -6.83 | s2:-5.2 | XRP -2.2, BNB -1.9, BTC -0.7, ETH -0.6, SOL 0.3 |
| 2023-06-10 07:00 | 3 | -4.91 | 12/23 | sl -4.9 / tp 0.35 / to -0.33 | -2.98 | s0:-4.0,s1:-3.7,s2:-3.7 | BNB -1.9, XRP -1.6, SOL -1.2, ETH -0.2, BTC -0.1 |
| 2023-06-10 05:00 | 1 | -4.86 | 5/19 | sl -4.3 / tp 0.67 / to -1.19 | -2.64 | s0:-3.1 | BNB -2.8, XRP -1.1, SOL -0.8, BTC -0.1, ETH -0.0 |
| 2022-09-18 23:00 | 3 | -4.82 | 0/6 | sl 0.0 / tp 0.14 / to -4.96 | -0.99 | - (max s0:0.4) | XRP -5.0, BNB 0.1 |
| 2023-06-05 18:00 | 2 | -4.71 | 8/25 | sl -5.0 / tp 0.78 / to -0.44 | -3.64 | s1:-4.6,s3:-4.4 | BNB -3.7, SOL -1.0, BTC -0.2, XRP 0.1, ETH 0.2 |
| 2022-09-23 11:00 | 3 | -4.71 | 0/5 | sl 0.0 / tp 0.79 / to -5.50 | -1.91 | - (max s0:0.6) | XRP -4.7 |
| 2025-02-03 05:00 | 1 | -4.66 | 12/24 | sl -6.1 / tp 1.41 / to 0.00 | -3.83 | s0:-3.6,s2:-4.5 | XRP -2.5, BNB -2.1, ETH -1.2, BTC 0.1, SOL 1.0 |
| 2023-06-05 17:00 | 1 | -4.64 | 6/25 | sl -5.0 / tp 0.87 / to -0.55 | -3.33 | s0:-3.3,s2:-4.3,s3:-4.4 | BNB -4.1, SOL -0.6, BTC -0.2, ETH 0.1, XRP 0.1 |
| 2024-12-20 12:00 | 0 | -4.49 | 0/22 | sl 0.0 / tp 0.45 / to -4.94 | -5.22 | - (max s1:1.9) | BNB -2.2, XRP -1.0, ETH -0.9, BTC -0.4, SOL 0.1 |
| 2023-04-26 23:00 | 3 | -4.48 | 4/25 | sl -4.9 / tp 1.19 / to -0.75 | -4.88 | s0:-5.1 | BTC -3.2, ETH -1.6, SOL -0.1, BNB 0.0, XRP 0.4 |
| 2023-06-14 21:00 | 1 | -4.46 | 0/24 | sl 0.0 / tp 1.33 / to -5.79 | -3.99 | - (max s3:0.6) | ETH -3.7, BTC -0.5, BNB -0.3, SOL -0.2, XRP 0.2 |
| 2026-08-20 21:00 | 1 | -4.38 | 2/5 | sl -2.7 / tp 0.00 / to -1.63 | -0.23 | - (max s0:0.4) | XRP -4.4 |
| 2022-11-09 12:00 | 0 | -4.32 | 6/23 | sl -6.0 / tp 1.65 / to 0.02 | -2.33 | s3:-4.0 | SOL -4.7, ETH -0.1, BNB -0.0, XRP 0.2, BTC 0.3 |
| 2025-07-24 07:00 | 3 | -4.26 | 2/15 | sl -2.0 / tp 0.00 / to -2.27 | -1.27 | s2:-3.5 | BNB -3.0, XRP -0.7, SOL -0.5, ETH 0.0 |
| 2025-02-02 19:00 | 3 | -4.23 | 0/15 | sl 0.0 / tp 0.00 / to -4.23 | -2.13 | - (max s1:1.4) | XRP -1.9, BNB -1.9, SOL -0.4, ETH -0.1 |
| 2024-02-28 20:00 | 0 | -4.11 | 4/18 | sl -10.6 / tp 6.52 / to 0.00 | 0.05 | s1:-7.6 | XRP -10.1, BTC 0.7, BNB 0.7, SOL 2.2, ETH 2.4 |
| 2021-10-27 11:00 | 3 | -4.10 | 5/21 | sl -5.1 / tp 1.17 / to -0.17 | -2.88 | s2:-3.6 | XRP -4.1, BNB -0.8, ETH -0.1, BTC 0.2, SOL 0.7 |
| 2026-09-15 22:00 | 2 | -4.04 | 3/16 | sl -4.3 / tp 1.24 / to -0.96 | -1.97 | - (max s3:1.7) | XRP -5.0, BNB 0.1, BTC 0.2, ETH 0.3, SOL 0.4 |
| 2023-06-10 08:00 | 0 | -4.01 | 7/23 | sl -4.1 / tp 0.84 / to -0.73 | -2.57 | s1:-3.4,s2:-3.8,s3:-4.9 | SOL -1.9, BNB -1.4, ETH -0.7, XRP -0.0, BTC 0.0 |
| 2021-11-10 23:00 | 3 | -4.00 | 4/23 | sl -5.3 / tp 1.26 / to 0.06 | -3.97 | s2:-5.9 | XRP -4.5, BNB -0.2, BTC 0.1, ETH 0.2, SOL 0.3 |
| 2022-11-09 11:00 | 3 | -3.99 | 7/23 | sl -4.6 / tp 0.70 / to -0.06 | -3.35 | s0:-4.4 | SOL -4.0, ETH -0.1, BNB -0.1, XRP 0.1, BTC 0.1 |
| 2022-05-11 16:00 | 0 | -3.99 | 13/25 | sl -5.1 / tp 1.14 / to 0.00 | -1.73 | s1:-7.8,s3:-6.4 | SOL -2.7, XRP -0.7, BNB -0.7, ETH -0.1, BTC 0.2 |
| 2022-01-21 23:00 | 3 | -3.98 | 2/24 | sl -2.1 / tp 0.80 / to -2.69 | -5.65 | - (max s1:1.1) | SOL -2.7, BNB -1.0, ETH -0.4, BTC 0.0, XRP 0.2 |
| 2023-06-10 06:00 | 2 | -3.96 | 9/24 | sl -3.4 / tp 0.28 / to -0.83 | -3.33 | s0:-3.8,s1:-4.2,s3:-4.5 | XRP -2.0, BNB -0.9, SOL -0.5, ETH -0.4, BTC -0.1 |
| 2023-08-17 23:00 | 3 | -3.93 | 19/25 | sl -4.2 / tp 0.22 / to 0.04 | -3.89 | s0:-7.2,s1:-13.2,s2:-5.6 | ETH -1.0, BTC -1.0, SOL -0.7, BNB -0.7, XRP -0.5 |
| 2022-09-19 01:00 | 1 | -3.86 | 0/5 | sl 0.0 / tp 0.00 / to -3.86 | -1.34 | s0:-5.9,s3:-4.8 | XRP -3.9 |
| 2024-07-05 04:00 | 0 | -3.65 | 6/22 | sl -4.1 / tp 0.60 / to -0.19 | -3.21 | s2:-5.6 | BNB -3.7, BTC -0.1, ETH -0.1, XRP 0.1, SOL 0.1 |
| 2021-10-27 10:00 | 2 | -3.65 | 6/23 | sl -3.7 / tp 0.50 / to -0.45 | -3.31 | s3:-3.9 | XRP -3.4, ETH -0.3, BNB -0.3, BTC 0.1, SOL 0.3 |
| 2025-10-17 10:00 | 2 | -3.62 | 1/16 | sl -1.2 / tp 0.07 / to -2.45 | -3.55 | - (max s3:0.6) | BNB -3.0, BTC -0.6, XRP -0.1, ETH -0.0, SOL 0.0 |
| 2024-07-05 05:00 | 1 | -3.56 | 12/24 | sl -3.8 / tp 0.51 / to -0.25 | -6.00 | s0:-3.3,s2:-5.9 | BNB -2.4, ETH -0.5, XRP -0.4, BTC -0.3, SOL 0.1 |
| 2025-07-24 06:00 | 2 | -3.52 | 0/12 | sl 0.0 / tp 0.00 / to -3.52 | -1.26 | - (max s0:0.0) | BNB -2.2, XRP -1.1, SOL -0.3 |
| 2024-08-05 04:00 | 0 | -3.51 | 14/25 | sl -3.3 / tp 0.22 / to -0.43 | -7.36 | - (max s1:-1.1) | BNB -1.3, ETH -0.9, BTC -0.8, XRP -0.5, SOL 0.1 |
| 2023-06-13 16:00 | 0 | -3.48 | 3/10 | sl -4.1 / tp 0.72 / to -0.07 | -1.63 | - (max s1:0.9) | XRP -3.4, SOL -0.0, BNB -0.0 |
| 2025-10-11 00:00 | 0 | -3.41 | 12/25 | sl -4.1 / tp 0.69 / to 0.00 | -3.34 | s1:-10.1,s2:-6.4,s3:-6.9 | BNB -1.2, XRP -1.0, SOL -0.8, BTC -0.3, ETH -0.1 |
| 2023-02-13 10:00 | 2 | -3.35 | 2/7 | sl -2.4 / tp 0.26 / to -1.25 | -1.14 | - (max s0:0.4) | BNB -3.4, XRP 0.0, ETH 0.0 |
| 2023-12-11 03:00 | 3 | -3.33 | 2/25 | sl -2.0 / tp 0.83 / to -2.16 | -4.21 | - (max s1:1.7) | ETH -2.4, BTC -1.0, XRP -0.7, BNB 0.0, SOL 0.8 |
| 2023-06-07 15:00 | 3 | -3.31 | 2/5 | sl -1.2 / tp 0.00 / to -2.12 | -0.57 | - (max s2:0.1) | BNB -3.3 |
| 2023-06-05 16:00 | 0 | -3.28 | 4/16 | sl -3.4 / tp 0.80 / to -0.69 | -2.87 | s1:-3.9,s2:-3.5 | BNB -3.1, SOL -0.5, BTC -0.0, ETH 0.0, XRP 0.3 |
| 2024-04-13 21:00 | 1 | -3.23 | 14/25 | sl -3.3 / tp 0.26 / to -0.15 | -8.34 | s2:-7.4,s3:-9.8 | BNB -1.2, SOL -0.9, XRP -0.4, BTC -0.4, ETH -0.3 |
| 2023-10-24 18:00 | 2 | -3.23 | 4/18 | sl -3.1 / tp 0.91 / to -1.05 | -1.88 | - (max s3:-0.2) | XRP -3.0, ETH -0.5, BNB -0.4, SOL 0.1, BTC 0.6 |
| 2022-05-11 19:00 | 3 | -3.20 | 3/25 | sl -1.1 / tp 0.39 / to -2.49 | -6.01 | - (max s0:1.2) | BNB -1.7, SOL -0.9, ETH -0.5, BTC -0.2, XRP 0.1 |
| 2022-01-21 02:00 | 2 | -3.19 | 0/11 | sl 0.0 / tp 0.00 / to -3.19 | -3.80 | - (max s3:0.1) | SOL -1.9, BNB -0.7, ETH -0.6, BTC -0.0, XRP 0.0 |
| 2022-05-11 14:00 | 2 | -3.16 | 15/25 | sl -3.8 / tp 0.60 / to 0.00 | -1.64 | s0:-4.0,s1:-7.8,s3:-6.7 | XRP -1.8, BNB -0.8, ETH -0.4, BTC -0.1, SOL -0.0 |
| 2023-11-02 16:00 | 0 | -3.12 | 0/10 | sl 0.0 / tp 0.81 / to -3.93 | -2.07 | - (max s3:0.5) | SOL -3.5, ETH -0.0, BNB 0.0, XRP 0.1, BTC 0.3 |
| 2023-03-22 20:00 | 0 | -3.12 | 0/17 | sl 0.0 / tp 0.18 / to -3.30 | -6.76 | - (max s2:1.0) | BTC -2.2, ETH -0.7, SOL -0.2, BNB -0.0, XRP -0.0 |
| 2021-11-26 11:00 | 3 | -3.10 | 1/23 | sl -1.0 / tp 0.32 / to -2.46 | -5.52 | - (max s0:0.9) | ETH -1.5, XRP -0.8, BNB -0.7, SOL -0.1, BTC -0.0 |
| 2023-11-22 00:00 | 0 | -3.07 | 4/14 | sl -2.9 / tp 0.23 / to -0.37 | -3.39 | s1:-3.6 | BNB -2.8, BTC -0.3, ETH -0.0, SOL -0.0, XRP 0.1 |
| 2022-11-28 02:00 | 2 | -3.04 | 0/10 | sl 0.0 / tp 0.00 / to -3.04 | -2.62 | - (max s1:0.3) | BNB -2.8, XRP -0.2, ETH -0.0, BTC 0.0, SOL 0.0 |
| 2026-01-06 18:00 | 2 | -3.03 | 0/4 | sl 0.0 / tp 0.00 / to -3.03 | -2.27 | - (max s3:0.8) | XRP -3.0 |
| 2023-11-22 01:00 | 1 | -3.01 | 5/14 | sl -3.6 / tp 0.56 / to 0.05 | -2.25 | s0:-3.1 | BNB -3.6, BTC 0.1, ETH 0.1, XRP 0.1, SOL 0.3 |

## How often does a 2024-01-03-type event happen?
A 2024-01-03-type bar is fixed as dip_loss <= -15% (just below the smallest gate-crash bar -17.5%). There are 3 such phase-bars in 5 years x4 phases, all on one calendar date 2024-01-03 (s1 13:00 -17.5%, s2 14:00 -21.7%, s3 15:00 -21.0%; BTC 4h -5.4/-6.2/-6.6%; 18-22 stops each, BTC-led multi-coin). That is 0.15/phase-year and 0.6 phase-bars per calendar year, i.e. one synchronous triple-crash date in 5 years (~0.2 dates/year point estimate; Poisson 95% upper ~0.96 dates/year from a single observed date). For risk planning treat a ~-20% single-bar dip loss on any live phase, synchronous across phases in the same wall-clock hours, as a once-in-several-years event that dominates the yearly DD whenever it prints: cap same-bar dip inventory/loss per phase (e.g. ~-12% circuit-breaker) rather than relying on next-bar cooldowns, wider stops, or book hedges, which oc_ddanat4p showed cannot touch a same-bar 18-22-stop cascade.

## Verdict
VERDICT: One-bar dip crashes >=3% hit 82 phase-bars in 5y (7-24/year, 15 fully synchronous across all 4 phases in the same wall hours); the 2024-01-03-type (<=-15%) printed once - three -17/-22/-21% BTC-led multi-coin stop cascades on one date - and the top 10 bars carry 15.9% of all dip-sleeve losses, so risk planning must assume a synchronous ~-20% single-bar dip loss every few years.
