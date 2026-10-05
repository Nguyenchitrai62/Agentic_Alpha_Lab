# R2-4P robustness over five years (per-year reset metric)

Baseline = `r2_decompose5/runs.pkl` run R2 (4-phase harness, pipe v321, win_start 5).
Metric = `reset_metric.year_reset` per anchor year (sub-accounts reset to 1/4 at each anchor).
Columns: per-year %/month / DD, 5-year geometric mean of the yearly monthly rates, max year DD,
full-path conservative DD of the equal 1/4 mix from 2021-09-24 (`v388.mix`).

| scenario | 2021 | 2022 | 2023 | 2024 | 2025 | mean5y | maxDD | fullDD |
|---|---|---|---|---|---|---|---|---|
| baseline | 1.956 / 14.04 | 3.765 / 15.93 | 4.005 / 25.05 | 10.633 / 9.17 | 3.949 / 18.82 | 4.820 | 25.05 | 23.08 |
| S1 | 1.122 / 14.67 | 2.898 / 16.85 | 3.203 / 25.34 | 9.756 / 9.45 | 3.251 / 21.06 | 4.005 | 25.34 | 23.24 |
| S2 | 1.733 / 14.06 | 3.635 / 16.07 | 3.695 / 25.00 | 10.600 / 8.81 | 3.753 / 19.80 | 4.640 | 25.00 | 23.32 |
| S3 | 1.166 / 14.04 | 1.619 / 17.56 | 2.856 / 24.93 | 9.700 / 9.47 | 3.984 / 17.49 | 3.820 | 24.93 | 22.72 |
| S4 | 1.656 / 14.12 | 3.203 / 16.26 | 3.243 / 27.39 | 10.503 / 10.07 | 3.626 / 21.50 | 4.401 | 27.39 | 24.59 |
| S5 | 1.294 / 13.45 | 2.982 / 17.78 | 3.536 / 27.82 | 10.608 / 9.71 | 3.968 / 17.83 | 4.430 | 27.82 | 26.68 |

Baseline: mean5y 4.820, maxDD 25.05, fullDD 23.08, fullMonthly 5.129, finalX 20.111.
S5 window from 2021-11-15: S5 monthly 4.816, DD 26.68, finalX 15.518; baseline same window: monthly 5.238, DD 23.08, finalX 19.612. S5 year 2021 is a short window (starts 2021-11-15).
Reproduction: phase-0 R2 final equity 51.602514, mix year_stats match r2_decompose5.json: True, hourly final match: True -> reproduced=True.

Verdict: the >= 0 per-year floor is broken by none; DD above 25 is reached by S1 (maxDD 25.34, fullDD 23.24), S4 (maxDD 27.39, fullDD 24.59), S5 (maxDD 27.82, fullDD 26.68). Baseline itself sits at maxDD 25.05 / fullDD 23.08 under the reset metric, so frictions that add drawdown trip the 25 line first; S2 sits exactly on the line (25.00) and S3 just under it (24.93).
