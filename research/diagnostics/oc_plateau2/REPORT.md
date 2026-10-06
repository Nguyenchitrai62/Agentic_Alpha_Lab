# oc_plateau2 REPORT — parameter plateau around R2B1D17BFG2 (2026-10-06; rows pre-registered before running)

## Setup
Harness = copy of research/diagnostics/oc_expiry4p/oc_expiry4p.py worker wiring
(pipe_setup "v321" with the R2 learned dip agents ON, bear-book filter x0.5 on
longs, kd budget scaling, reset metric via
research/diagnostics/r2_decompose5/reset_metric.py per anchor year, full-path
DD via v388.mix, win_start=5). Sequential: one engine process at a time
(fresh Pool(1) per shift), RAM-gated start (2 GB gate; one bounded 300 s wait,
then proceed-with-warning, logged). Every leg (shift, row) cached to
legs/leg_s{shift}_{row}.pkl right after finishing, so the restart resumed
(s0x7 + s1x4 from the first attempt, s1x3 + s2x7 + s3x7 on resume).
Reference R2B1D17BFG2 reproduced v421 run.log exactly
(5.41 / 2.588 / 16.91 / 16.82; per-shift eq 55.993 / 17.031 / 26.262 / 6.264).
Each variant changes ONE dip-sleeve parameter (TP_MULT scales the R2-learned
sleeve_tp lookup, phase_offset_full pipe_setup :91, and the m_sleeve_tp
fallback, engine_user :76/:705; close5 stop = kw["m_sleeve_sl"] after
pipe_setup, v321 KW_OVERRIDE backend/history_tm.py:46-47 = 4.0, applied at
engine_user :669/:706/:693; gross cap = kw["sleeve_gross_cap"],
v421_gross_cap.py:113-114, applied at engine_user :699-701).
Repro: research/diagnostics/oc_plateau2/{oc_plateau2.py,results.json,run.log}.
All five years are research data; deployment pick stays R2B1D17BFG2 regardless
(diagnostic only).

## Per-row summary (5y geometric %/month | worst year | max yearly DD | full-path DD | losing years | all-trade win 5y)
| row | 5y %/mo | worst | maxDD | fullDD | losing | win |
|---|---|---|---|---|---|---|
| R2B1D17BFG2 (ref) | 5.410 | 2.588 | 16.91 | 16.82 | 0 | 0.6533 |
| R2B1D17BFG2_TP08 (TP x0.8) | 5.183 | 2.698 | 15.84 | 15.82 | 0 | 0.6796 |
| R2B1D17BFG2_TP12 (TP x1.2) | 5.482 | 2.546 | 18.19 | 18.08 | 0 | 0.6326 |
| R2B1D17BFG2_SL35 (stop 3.5) | 5.324 | 2.617 | 17.15 | 17.06 | 0 | 0.6512 |
| R2B1D17BFG2_SL45 (stop 4.5) | 5.394 | 2.610 | 16.80 | 16.79 | 0 | 0.6545 |
| R2B1D17BFG2_G175 (G 1.75) | 5.503 | 2.527 | 16.74 | 16.68 | 0 | 0.6525 |
| R2B1D17BFG2_G225 (G 2.25) | 5.252 | 2.598 | 16.87 | 16.76 | 0 | 0.6540 |

## Per-year table ([%/mo, DD, win] per anchor year 2021..2025)
| row | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| R2B1D17BFG2 | [2.588, 10.86, 0.6129] | [3.282, 16.91, 0.6574] | [6.045, 15.81, 0.6956] | [10.677, 8.27, 0.6699] | [4.648, 12.90, 0.6267] |
| R2B1D17BFG2_TP08 | [2.698, 10.20, 0.6409] | [3.307, 15.84, 0.6856] | [5.507, 15.61, 0.7185] | [10.016, 8.09, 0.6965] | [4.545, 12.28, 0.6515] |
| R2B1D17BFG2_TP12 | [2.546, 12.41, 0.5925] | [3.250, 18.19, 0.6332] | [6.334, 16.22, 0.6760] | [11.068, 8.32, 0.6501] | [4.431, 13.96, 0.6079] |
| R2B1D17BFG2_SL35 | [2.617, 11.04, 0.6113] | [2.990, 17.15, 0.6523] | [5.922, 15.59, 0.6937] | [10.599, 8.27, 0.6699] | [4.684, 11.87, 0.6245] |
| R2B1D17BFG2_SL45 | [2.610, 11.01, 0.6143] | [3.359, 16.80, 0.6588] | [5.787, 15.86, 0.6972] | [10.722, 8.28, 0.6701] | [4.685, 13.08, 0.6278] |
| R2B1D17BFG2_G175 | [2.527, 10.94, 0.6130] | [3.240, 16.74, 0.6552] | [6.897, 15.06, 0.6959] | [10.505, 8.27, 0.6674] | [4.543, 12.94, 0.6250] |
| R2B1D17BFG2_G225 | [2.598, 10.71, 0.6129] | [3.390, 16.87, 0.6592] | [4.993, 16.81, 0.6962] | [10.737, 8.26, 0.6714] | [4.732, 12.88, 0.6280] |

## Verdict
VERDICT: ON a plateau in all three dip-sleeve dimensions — TP x0.8/x1.2 moves
5y return by -0.23/+0.07 %/mo and full-path DD by -1.00/+1.26 pp; stop
3.5/4.5 sigma moves 5y by -0.09/-0.02 %/mo and full-path DD by +0.24/-0.03 pp;
gross cap 1.75/2.25 moves 5y by +0.09/-0.16 %/mo and full-path DD by
-0.14/-0.06 pp. Every variant is within 0.3 %/mo (5y) and 1.5 pp (full-path
DD) of the base on BOTH sides. No losing year in any row; win rate moves with
TP width (0.68 at x0.8 vs 0.63 at x1.2, base 0.65) while SL/G leave it flat at
~0.65. No selection change (R2B1D17BFG2 stays deployed).

G2 dang nam tren mot vung bang phang (plateau) o ca ba chieu tham so da kiem
tra: nhan TP 0.8/1.2, stop close5 3.5/4.5 sigma va gioi han gross G 1.75/2.25
deu cho loi nhuan 5 nam chenh lech khong qua 0.3 %/thang va drawdown toan
chang chenh lech khong qua 1.5 diem phan tram so voi ban trien khai
R2B1D17BFG2 o ca hai phia; khong co nam thua lo o bat ky hang nao va ban trien
khai van giu nguyen R2B1D17BFG2.
