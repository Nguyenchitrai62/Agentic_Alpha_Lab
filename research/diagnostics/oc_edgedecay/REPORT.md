# oc_edgedecay REPORT — is the G2 edge decaying? (2026-10-06)

DIAGNOSTIC only: no trading rule, no variant selection. G2 = R2B1D17BFG2
(registry v421 = R2B1D17BF + dip gross-notional cap G=2.0).
Sources (read-only, no engine reruns, one process): v421_runs.pkl per-phase
hourly equity, oc_kpi_g2 events_s0..3 (book + rung exits, equity replica
cross-check), hourly_ext majors (market context), oc_rolling17 (context).
All five years are research data; findings need prospective validation.
Repro: research/diagnostics/oc_edgedecay/{run_edgedecay.py,results.json};
test tests/test_oc_edgedecay.py.

## Setup + reproduction proof
Continuous 4-phase mix e = mean of phase equities (v388.mix, hourly grid
2021-09-24 04:00 .. 2026-09-23 12:00 UTC). Calendar-month returns exactly as
oc_kpi_g2/run_kpi.py; replica matches oc_kpi_g2 results_equity.json on all 61
months to 0.00. Analysis universe = 60 months 2021-10..2026-09 (the 2021-09
partial bar is 0.00% by construction, excluded). Yearly rows use
reset_metric.year_reset (sub-accounts reset to 1/4 at each anchor):
2021: 2.59/10.86, 2022: 3.28/16.91, 2023: 6.05/15.81, 2024: 10.68/8.27,
2025: 4.65/12.90 (R %/mo, 1m DD %; match v421_result.json). Components from
exits (rung FIFO pairs + v213 book episodes; pooled win rates match oc_kpi_g2:
book 0.5154, rungs 0.6858, all 0.6533). Event weights are equity fractions
(stationary gross/equity ratios while equity grows 26.4x), so each leg is
scaled by sub-account equity at its fill; mix P&L = sum/4 over month-start mix.

## (1) Monthly trend, 60 months (plot-free)
Full-sample monthly %: mean 6.10, median 3.65, std 11.10, min -7.17,
p10 -3.01 / p25 -0.69 / p75 9.33 / p90 17.86, max 63.83.
OLS slope vs time: +0.067 pp/month (+0.80 pp/year) with moving-block
bootstrap CI (block 3m, B=5000, seed 7) [-0.158, +0.160] pp/mo, i.e.
[-1.89, +1.92] pp/yr; P(no positive trend) = 0.48. CI covers 0 comfortably.
First 30m (2021-10..2024-03): mean 5.59, median 3.27, >=5% 36.7%, >=0% 73.3%.
Last 30m (2024-04..2026-09): mean 6.61, median 4.66, >=5% 46.7%, >=0% 66.7%.
Difference last-first: +1.02 pp, block CI [-5.40, +5.51], P(diff<=0) = 0.50.
Last 6m (2026-04..09) mean 7.38: 65th pct of all months, 78th pct of the 55
rolling-6m means (p10 alert line 1.61). Last 12m (2025-10..2026-09) mean 4.87:
58th pct of months, 43rd pct of the 49 rolling-12m means (p10 line 3.08).

## (2) Component split (exit-time attribution; residual = funding + open marks)
Monthly-mean attribution: dip +4.80 pp, book +1.99 pp, residual -0.68 pp
(sum 6.10 = total). Component trends: dip -0.008, book +0.024 pp/mo (~flat).

| half | book n/win | rung n/win (sl/tp/to) | all win | TP | rung bp | book bp | tpm |
|---|---|---|---|---|---|---|---|
| H0 21-09..22-03 | 468/0.474 | 1797/0.671 (0.05/0.47/0.48) | 0.631 | 0.473 | +27 | +1 | 378 |
| H1 22-03..22-09 | 458/0.533 | 2278/0.612 (0.06/0.43/0.52) | 0.598 | 0.429 | -5 | +38 | 456 |
| H2 22-09..23-03 | 452/0.535 | 2177/0.714 (0.04/0.54/0.42) | 0.683 | 0.537 | +32 | +35 | 438 |
| H3 23-03..23-09 | 409/0.487 | 1764/0.659 (0.09/0.50/0.41) | 0.626 | 0.502 | -22 | +59 | 362 |
| H4 23-09..24-03 | 507/0.542 | 2864/0.771 (0.05/0.59/0.36) | 0.737 | 0.590 | +33 | +137 | 562 |
| H5 24-03..24-09 | 495/0.487 | 2115/0.679 (0.07/0.46/0.46) | 0.643 | 0.463 | -6 | -60 | 435 |
| H6 24-09..25-03 | 669/0.525 | 2454/0.745 (0.02/0.57/0.41) | 0.697 | 0.573 | +63 | +144 | 521 |
| H7 25-03..25-09 | 494/0.482 | 1393/0.675 (0.00/0.44/0.56) | 0.624 | 0.435 | +34 | +11 | 315 |
| H8 25-09..26-03 | 575/0.576 | 2916/0.608 (0.04/0.44/0.51) | 0.603 | 0.444 | -9 | +91 | 582 |
| H9 26-03..26-09 | 537/0.497 | 1755/0.713 (0.01/0.51/0.48) | 0.663 | 0.513 | +26 | +77 | 382 |
| trend/half | +0.002 | +0.002 | +0.001 | +0.000 | +1.2bp | +6.0bp | +3.9 |

Avg dip fill rung per half: 3.11/3.13/3.15/3.13/3.07/3.14/3.07/2.99/3.11/3.02
(trend -0.012/half: negligible). No component trends down: win-rate and TP
slopes are ~0; the weakest halves (H1, H8 rung ret <= 0) both rebound after.

## (3) Market context per half (BTC ann. RV %; 2.5-sigma 4h flush counts)
| half | BTC RV | BTC/ETH/SOL/BNB/XRP flush | TOTAL (/mo) | reading |
|---|---|---|---|---|
| H0 | 65.5 | 16/19/19/21/13 | 88 (14.7) | baseline |
| H1 | 68.6 | 21/26/15/24/18 | 104 (17.3) | high vol |
| H2 | 50.9 | 18/18/20/22/18 | 96 (16.0) | normal |
| H3 | 38.4 | 20/15/17/20/13 | 85 (14.2) | calm, fewest trades (362/mo) yet rung win 0.66 |
| H4 | 48.4 | 16/13/9/12/17 | 67 (11.2) | fewest flushes, BEST rung win 0.77 / TP 0.59 |
| H5 | 52.1 | 22/16/16/13/12 | 79 (13.2) | normal |
| H6 | 53.5 | 20/21/17/20/18 | 96 (16.0) | normal, strong both sleeves |
| H7 | 36.6 | 14/18/16/20/14 | 82 (13.7) | calmest: FEWER opportunities (315 tpm), edge intact |
| H8 | 48.5 | 33/31/23/26/24 | 137 (22.8) | flush spike: MOST opportunities (582 tpm) but WORSE per-trade (rung -9bp, TP 0.44) |
| H9 | 38.7 | 14/22/11/20/16 | 83 (13.8) | normalises: win 0.71, TP 0.51 |

Volatility shows no regime shift (RV 36-69%, no trend). Flush counts separate
the two stories: H7 = fewer opportunities with intact edge; H8 = more
opportunities with weaker edge per opportunity, then H9 reverts to normal.

## Early warning (paper/live monitoring, trailing only; breach = investigate)
1. Trailing-6m mean monthly % < 1.61% (historical p10 of the 55 rolling-6m
   means; median 5.44). 2. A closed half-year dip TP rate < 0.434
   (historical p10 of the 10 halves). Reference: trailing-12m p10 = 3.08%.

## Ket luan (tieng Viet, binh dan)
Khong co bang chung thong ke nao cho thay edge cua G2 dang suy yeu dan:
do doc xu huong thang gan nhu bang 0 (+0.07 diem %/thang, khoang tin cay
chua ca so 0), 30 thang sau (6.61%/thang) con cao hon 30 thang dau
(5.59%/thang), 6 thang gan nhat (7.38%) nam trong nhom manh cua lich su, va
khong co sleeve nao (book hay dip) xuong doc don dieu — win rate va TP rate
dao dong quanh muc cu roi hoi phuc (nua yeu H1, H8 deu bat lai ngay sau).
Bien dong theo nua nam giai thich duoc bang co hoi thi truong: nua tram lang
H7 it co hoi (315 trade/thang) nhung edge con nguyen; nua nhieu flush H8
nhieu co hoi (582 trade/thang) nhung chat luong moi trade kem (rung -9bp)
roi H9 tro lai binh thuong. Giay bao dong som de theo doi paper/live:
(1) trung binh 6 thang gan nhat < 1.61%/thang, (2) TP rate dip cua mot nua
nam kheo kin < 0.434 — vo nguong la dieu tra, khong phai hanh dong giao dich.

VERDICT: No statistically meaningful decay in G2 over 2021-09-24..2026-09-23;
half-year wiggles are opportunity-driven (H7 fewer shots, H8 weaker shots at
record volume, H9 reversion), not edge decay. Watch trailing-6m mean < 1.61%
and half-year dip TP rate < 0.434.
