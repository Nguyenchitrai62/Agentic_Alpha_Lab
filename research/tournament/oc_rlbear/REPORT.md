# oc_rlbear — REPORT (V2-lite bear flag on R2 dip agents, phase s=0)

## V0 reproduction gate (must pass before screening)

| check | value |
|---|---|
| ref rows (v376 hidden s0) | 273850 |
| V0 rows | 273850 |
| overlap rows | 273850 |
| ref-only / V0-only | 0 / 0 |
| size_match | 1.0000 |
| tp_match | 1.0000 |

V0 reproduces v376/tables_hidden/r2_table_s0.parquet EXACTLY (100% size and
TP match). Screening proceeds. V2 saved as r2bear_table_s0.parquet (273850
rows, same schema T/sym/rung/size/tp).

Table value counts — V0: size {1.0:211937, 1.5:39877, 0.5:22036},
tp {1.0:160602, 1.5:111403, 0.5:1845}; V2: size {1.0:216427, 1.5:33360,
0.5:24063}, tp {1.0:176112, 1.5:94994, 0.5:2744} (bear shifts mass to 1.0).

## Rung-level screen (majors x rungs 2.5..5.0, outcome = size * y_tableTP, daily sums by exit date)

| year | n | sum V0 | sum V2 | V2 win? | maxDD V0 | maxDD V2 | DD ok? | fillWR V0/V2 | worstDay V0/V2 |
|---|---|---|---|---|---|---|---|---|---|
| 2021 | 990 | 4.4849 | 4.5288 | yes (+0.0439) | 0.5389 | 0.5014 | yes | 0.671/0.680 | -0.434/-0.445 |
| 2022 | 1045 | 0.9238 | 0.9787 | yes (+0.0549) | 1.9145 | 1.9246 | no | 0.692/0.692 | -1.914/-1.925 |
| 2023 | 1330 | 6.6272 | 6.4906 | no (-0.1366) | 0.5754 | 0.6941 | no | 0.765/0.768 | -0.575/-0.694 |
| 2024 | 989 | 4.2650 | 4.0893 | no (-0.1757) | 0.7025 | 0.6900 | yes | 0.688/0.692 | -0.703/-0.690 |
| 2025 | 1144 | 1.9059 | 1.9783 | yes (+0.0724) | 0.5881 | 0.5947 | no | 0.656/0.647 | -0.498/-0.507 |

Years V2 sum>V0: 3/5 (2021, 2022, 2025). Years maxDD not worse: 2/5 (2021, 2024).

## Divergence V2 vs V0 (bear vs non-bear bars)

| year | bear_frac | size-diff bear/nonbear | tp-diff bear/nonbear |
|---|---|---|---|
| 2021 | 0.824 | 0.086/0.029 | 0.315/0.155 |
| 2022 | 0.371 | 0.085/0.117 | 0.077/0.117 |
| 2023 | 0.217 | 0.059/0.132 | 0.191/0.220 |
| 2024 | 0.081 | 0.075/0.074 | 0.213/0.188 |
| 2025 | 0.734 | 0.061/0.076 | 0.182/0.214 |

The bear flag moves decisions (6-13% size, 8-32% TP differ), most visibly TP
in bear bars in 2021, but the moves do not convert into a consistent gain.

## Verdict

NOT PROMISING: V2-lite sum wins in 3/5 years and DD is not worse in 2/5 years, below the frozen >=4/5 + >=4/5 bar.

## Caveats / leakage notes

- Rung-level counterfactual screen only (no engine replay, no costs beyond
  the y's embedded maker/taker/funding, no B1 sizing); prospective logs still
  required for any winner (none here).
- maxDD is of the cumulative daily-sum path from 0 (absolute units, identical
  for V0/V2); fill WR = mean(out>0), day WR over exit days.
- Leakage checklist: bear from opens <= decision bar only; fits/mu/rules on
  t_exit < A-7d; table state at bar-open minutes only; seeds/clip/rules fixed
  from build_tables.py; no test-year statistic used. V0 100% match confirms
  the pipeline is faithful.
- Dropped fills with missing table rows: 0 in every year.
