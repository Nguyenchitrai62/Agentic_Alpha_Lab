# oc_agentskip — REPORT (SKIP gate on R2 dip size agent, phase s=0, idea #57)

Fixed variant: size 0 when BOTH HGB halves predict y1.0 < -0.002, else S1
unchanged; TP unchanged; same features/windows/embargo/anchors/seeds as V0.

## Base reproduction gate (must pass before screening)

| check | value |
|---|---|
| ref rows (v376 hidden s0) | 273850 |
| base rows / skip rows | 273850 / 273850 |
| overlap rows | 273850 |
| ref-only / base-only | 0 / 0 |
| size_match | 1.0000 |
| tp_match | 1.0000 |

Base reproduces v376/tables_hidden/r2_table_s0.parquet EXACTLY. Screening
proceeds. mus match oc_rlbear (0.00725/0.00514/0.00336/0.00292/0.00281).
Skip converts 12,008 table rows (4.38%) to size 0, all from would-be 0.5
(0.5: 22036->10028; 1.0/1.5 unchanged); TP counts identical base vs skip.

## Rung-level screen (majors x rungs 2.5..5.0, outcome = size * y_tableTP, daily sums by exit date)

| year | n | sum base | sum skip | skip not lower? | maxDD base | maxDD skip | DD ok? | fillWR base/skip | worstDay base/skip |
|---|---|---|---|---|---|---|---|---|---|
| 2021 | 990 | 4.4849 | 4.5283 | yes (+0.0435) | 0.5389 | 0.5389 | yes | 0.671/0.666 | -0.434/-0.434 |
| 2022 | 1045 | 0.9238 | 0.9395 | yes (+0.0157) | 1.9145 | 1.9100 | yes | 0.692/0.644 | -1.914/-1.910 |
| 2023 | 1330 | 6.6272 | 6.4853 | no (-0.1420) | 0.5754 | 0.5840 | no | 0.765/0.739 | -0.575/-0.584 |
| 2024 | 989 | 4.2650 | 4.1350 | no (-0.1301) | 0.7025 | 0.7025 | yes | 0.688/0.630 | -0.703/-0.703 |
| 2025 | 1144 | 1.9059 | 1.7524 | no (-0.1535) | 0.5881 | 0.4133 | yes | 0.656/0.536 | -0.498/-0.373 |

Years skip sum>=base: 2/5 (2021, 2022). Years maxDD not worse: 4/5 (all but 2023).

## Skip diagnostics (kept fills per year)

| year | skip share | skipped n | skipped rungs' realised mean (base outcome) |
|---|---|---|---|
| 2021 | 0.0091 | 9 | -0.004828 |
| 2022 | 0.0651 | 68 | -0.000230 |
| 2023 | 0.0308 | 41 | +0.003463 |
| 2024 | 0.0890 | 88 | +0.001478 |
| 2025 | 0.1582 | 181 | +0.000848 |

Only in 2021 (and ~zero in 2022) were the gated rungs truly losers; in
2023-2025 the gate removed rungs with POSITIVE realised mean, costing
0.13-0.15 sum per year. 2025 DD improves (0.588->0.413) but only by skipping
winners too. Dropped fills with missing table rows: 0 every year.

## Verdict

NOT PROMISING: skip sum is not lower in 2/5 years and DD is not worse in 4/5 years, below the frozen >=4/5 + >=4/5 bar.

## Caveats / leakage notes

- Rung-level counterfactual screen only (no engine replay, no costs beyond
  the y's embedded maker/taker/funding, no B1 sizing); prospective logs
  still required for any winner (none here).
- maxDD is of the cumulative daily-sum path from 0 (absolute units, identical
  for base/skip); fill WR = mean(out>0), day WR over exit days.
- Leakage checklist: table state at bar-open minutes only; fits/mu/rules on
  t_exit < A-7d; skip gate uses ONLY bar-open pa/pb (no fill-minute or
  future data); seeds/clip/threshold fixed upfront (-0.002, no tuning); no
  test-year statistic used. Base 100% match confirms pipeline faithfulness.
- One fixed variant only, scored once; no iteration on test-year scores.
