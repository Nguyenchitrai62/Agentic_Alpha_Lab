# oc_stresshist — stress weeks of R2B1D17BFG2 (G2, gross-cap 2.0) vs R2B1D17BF (D17BF)

Method: 4-phase mean of the frozen runs pkls (v421 / v411), each phase divided by its
value at the anchor, yearly reset to 1.00 (same code path as
research/diagnostics/r2_decompose5/reset_metric.py). Per window: start = year-equity
at window open, trough = window minimum, week = window net %, DD = 1-trough/prior-peak
(each config vs its OWN prior peak — the like-for-like column), rec = days from trough
back to the prior peak (searched to year end; "never" = not recovered within the year).
Start/trough levels are NOT directly comparable across configs (different year-to-date
growth); DD and week are. Full numbers in results.json.

## Named stress windows

| window | cfg | start | trough | week % | DD % | rec d | DD G2-BF (pp) |
|---|---|---|---|---|---|---|---|
| 2021-12-04 (7d) | G2 | 1.033 | 1.001 | -1.8 | 3.3 | 10.3 | 0.0 |
| 2021-12-04 (7d) | BF | 1.033 | 1.001 | -1.8 | 3.3 | 10.3 | |
| LUNA 2022-05-09..15 | G2 | 1.308 | 1.237 | -3.0 | 9.7 | 38.8 | 0.0 |
| LUNA 2022-05-09..15 | BF | 1.308 | 1.237 | -3.0 | 9.7 | 38.8 | |
| 3AC 2022-06-13..19 | G2 | 1.322 | 1.314 | +3.6 | 4.1 | 7.0 | +0.0 |
| 3AC 2022-06-13..19 | BF | 1.321 | 1.313 | +3.6 | 4.1 | 7.0 | |
| FTX 2022-11-07..14 | G2 | 1.031 | 0.947 | -2.2 | 9.2 | 37.0 | -0.8 |
| FTX 2022-11-07..14 | BF | 1.033 | 0.946 | -2.8 | 10.0 | 36.7 | |
| 2023-08-17 (7d) | G2 | 1.626 | 1.484 | -7.6 | 9.4 | never | -0.1 |
| 2023-08-17 (7d) | BF | 1.669 | 1.520 | -7.8 | 9.6 | never | |
| 2024-01-03 (7d) | G2 | 1.610 | 1.390 | -11.1 | 14.1 | 54.1 | -2.4 |
| 2024-01-03 (7d) | BF | 1.659 | 1.392 | -13.8 | 16.5 | 56.0 | |
| 2024-03-05 (7d) | G2 | 1.845 | 1.678 | +1.2 | 11.0 | 6.9 | +3.0 |
| 2024-03-05 (7d) | BF | 1.725 | 1.611 | +0.4 | 8.0 | 7.3 | |
| 2024-08-04..07 | G2 | 2.030 | 2.025 | +6.3 | 7.3 | 32.5 | -1.5 |
| 2024-08-04..07 | BF | 1.760 | 1.754 | +4.6 | 8.7 | never | |
| 2025-10-10..11 | G2 | 1.177 | 1.076 | -8.6 | 10.5 | 139.5 | -0.1 |
| 2025-10-10..11 | BF | 1.187 | 1.083 | -8.7 | 10.7 | 139.4 | |

## Worst 5 weeks of each config (rolling 7d, scored under both)

| whose worst 5 | week | cfg | week % | DD % | rec d | DD G2-BF (pp) |
|---|---|---|---|---|---|---|
| G2 (-12.5) | 2023-12-27..2024-01-03 | G2 | -12.3 | 13.9 | 54.1 | -2.4 |
| G2 (-12.5) | 2023-12-27..2024-01-03 | BF | -14.7 | 16.3 | 56.0 | |
| G2 (-9.8) | 2025-10-10..17 | G2 | -9.7 | 11.6 | 134.0 | +0.1 |
| G2 (-9.8) | 2025-10-10..17 | BF | -9.6 | 11.5 | 134.0 | |
| G2 (-9.8) | 2024-07-09..16 | G2 | -9.6 | 11.9 | 52.8 | +0.7 |
| G2 (-9.8) | 2024-07-09..16 | BF | -9.0 | 11.1 | never | |
| G2 (-9.7) | 2023-06-03..10 | G2 | -8.6 | 13.0 | 37.9 | +1.2 |
| G2 (-9.7) | 2023-06-03..10 | BF | -8.9 | 11.8 | 33.5 | |
| G2 (-8.9) | 2024-06-05..12 | G2 | -8.9 | 9.4 | 22.6 | -1.7 |
| G2 (-8.9) | 2024-06-05..12 | BF | -10.7 | 11.1 | never | |
| BF (-14.9) | 2023-12-27..2024-01-03 | G2 | -12.3 | 13.9 | 54.1 | -2.4 |
| BF (-14.9) | 2023-12-27..2024-01-03 | BF | -14.7 | 16.3 | 56.0 | |
| BF (-10.7) | 2024-06-05..12 | G2 | -8.9 | 9.4 | 22.6 | -1.7 |
| BF (-10.7) | 2024-06-05..12 | BF | -10.7 | 11.1 | never | |
| BF (-9.9) | 2023-06-03..10 | G2 | -8.6 | 13.0 | 37.9 | +1.2 |
| BF (-9.9) | 2023-06-03..10 | BF | -8.9 | 11.8 | 33.5 | |
| BF (-9.7) | 2025-10-10..17 | G2 | -9.7 | 11.6 | 134.0 | +0.1 |
| BF (-9.7) | 2025-10-10..17 | BF | -9.6 | 11.5 | 134.0 | |
| BF (-9.3) | 2024-07-08..15 | G2 | -9.5 | 11.3 | 53.1 | +0.4 |
| BF (-9.3) | 2024-07-08..15 | BF | -9.2 | 10.9 | never | |

Notes: both configs agree on 4 of 5 worst weeks (same events). "never" = prior peak not
retaken before the anchor year ends. 2025-10 recovers only via the long grind into 2026
(~134-139 d). All five years are research data; nothing here selects a variant.

Verdict: a bad week loses roughly a tenth of year-equity (-9..-15% week, 9..16% DD from the
prior peak, 1-2 months to recover, longer after 2025-10); G2 is no worse than D17BF in 7 of
9 named windows (notably -2.4 pp DD in Jan-2024) but worse in Mar-2024 (+3.0 pp DD, kept open
as the single counter-example).
