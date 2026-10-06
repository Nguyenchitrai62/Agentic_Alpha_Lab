# oc_seasondepth REPORT (idea #70: intraday-seasonal rung depth, 2026-10-06)

Method: exact oc_dipexit D0 replica + oc_b1deeper B1 sizes (w = 1/(1+n)) on
majors x R2 depths {2.5,3,3.5,4,5}, 5 anchor years, 4 clock phases
(4h grids from 2020-08-01 00:00 + 0/1/2/3h). BASE uses bar sigma_4h; RULE uses
sigma_eff = sigma_4h x sqrt(s), s = walk-forward per-coin hour-of-week factor
(mean |1m logret| in the bar's weekly 4h slot / overall mean, window
[anchor-365d, anchor), 5x5x42 table, fallback s=1). TP/stops in arm-sigma
units. Unpaired arms (own fills, NaN nets dropped per arm). Sums = raw w*y;
side row renormalised. Fees maker 0.0002 / taker 0.00055, longs pay 0.0001 at
00/08/16-UTC timeouts. Ledger: 43,424 fills, checksum 8ee7c1bdc9afed87.

## 4-phase-mean per year (S=sum w*y, Sr=renorm sum, n=trades, win=y>0 share, W=worst day, DD=maxDD)

| year | BASE S / Sr / n / win / W / DD | RULE S / Sr / n / win / W / DD | S_rule>=S_base | DD_rule<=DD_base+0.01 |
|---|---|---|---|---|
| 2021-09-24 | 0.911 / 1.507 / 1043 / 0.660 / -0.740 / 0.856 | 0.514 / 0.842 / 1029 / 0.655 / -0.808 / 0.924 | NO | NO (+0.068) |
| 2022-09-24 | 0.833 / 1.247 / 1015 / 0.699 / -0.726 / 0.951 | 0.877 / 1.331 / 966 / 0.705 / -0.701 / 0.962 | YES | NO (+0.011) |
| 2023-09-24 | 2.100 / 3.169 / 1338 / 0.748 / -0.735 / 0.800 | 1.777 / 2.738 / 1246 / 0.754 / -0.957 / 1.074 | NO | NO (+0.274) |
| 2024-09-24 | 3.197 / 4.885 / 990 / 0.734 / -0.274 / 0.354 | 2.975 / 4.581 / 916 / 0.738 / -0.254 / 0.305 | NO | YES (-0.050) |
| 2025-09-24 | 0.677 / 1.147 / 1193 / 0.661 / -0.508 / 0.607 | 0.479 / 0.791 / 1122 / 0.665 / -0.567 / 0.678 | NO | NO (+0.071) |

Score: PASS_sum 1/5, PASS_dd 1/5. Renormalised side row agrees (RULE Sr < BASE Sr in 4/5 years).

## Factor range per anchor (s, and sqrt(s) effective-sigma multiplier)

| anchor | s min-max (all coins x 42 slots) | sqrt(s) min-max |
|---|---|---|
| 2021-09-24 | 0.77-1.38 | 0.88-1.17 |
| 2022-09-24 | 0.67-1.36 | 0.82-1.17 |
| 2023-09-24 | 0.50-1.59 | 0.71-1.26 |
| 2024-09-24 | 0.54-1.55 | 0.74-1.24 |
| 2025-09-24 | 0.51-1.58 | 0.71-1.26 |

Factors behave as designed (quiet slots ~0.5x, loud slots ~1.6x) but the rule
loses fills (RULE n < BASE n every year) and net sum in 4/5 years. Phase
dispersion stays extreme under both arms (e.g. 2021 BASE per-phase sums
2.39/0.92/0.73/-0.39), so clock phase dominates the seasonal depth effect.

## Verdict

NOT PROMISING: seasonal sigma scaling (sqrt-shrunk hour-of-week factor) beats the base 4-phase-mean sum in 1/5 years and meets the +1pp DD bound in 1/5 years; direction closed, no prospective validation warranted.
