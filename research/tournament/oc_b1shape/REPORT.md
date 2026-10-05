# oc_b1shape REPORT: rung-level screen of correlation-aware sizing shapes

## n histogram (share of majors R2 fills with n = 0..4; 5498 fills in 5y)

| year | n=0 | n=1 | n=2 | n=3 | n=4 | fills |
|---|---|---|---|---|---|---|
| 2021-09-24 | 0.426 | 0.179 | 0.136 | 0.118 | 0.140 | 990 |
| 2022-09-24 | 0.493 | 0.181 | 0.145 | 0.098 | 0.084 | 1045 |
| 2023-09-24 | 0.496 | 0.171 | 0.120 | 0.104 | 0.110 | 1330 |
| 2024-09-24 | 0.465 | 0.185 | 0.140 | 0.141 | 0.070 | 989 |
| 2025-09-24 | 0.387 | 0.177 | 0.129 | 0.159 | 0.148 | 1144 |
| overall | 0.455 | 0.178 | 0.133 | 0.123 | 0.111 | 5498 |

## Yearly sums S = sum(w' * y1.0), equal exposure (mean w' = 1 per year)

| shape | 2021 | 2022 | 2023 | 2024 | 2025 | >= S1 |
|---|---|---|---|---|---|---|
| S0 flat | 3.777 | 0.393 | 5.276 | 4.066 | 1.538 | 3/5 |
| S1 1/(1+n) | 3.955 | 0.291 | 5.737 | 3.952 | 1.237 | — |
| S2 1/(1+n)^2 | 4.171 | 0.209 | 6.015 | 3.803 | 1.086 | 2/5 |
| S3 BTCx2 | 4.009 | 0.170 | 5.741 | 3.961 | 1.319 | 4/5 |
| S4 2.0σ detect | 3.449 | -0.115 | 5.541 | 4.000 | 1.487 | 2/5 |

## Tails (overall worst-day; full-path maxDD of cumulative daily sums)

| shape | worst-day | maxDD |
|---|---|---|
| S0 flat | -1.924 | -2.282 |
| S1 1/(1+n) | **-1.081** | **-1.698** |
| S2 1/(1+n)^2 | -1.162 | -1.973 |
| S3 BTCx2 | -1.096 | -1.761 |
| S4 2.0σ detect | -1.182 | -1.987 |

## Verdict

keep S1: no pre-registered shape beats its tails under yearly-S>=S1 in >=4/5y.

## Caveats

- S3 (BTC double weight) is the only challenger meeting the yearly constraint
  (4/5y, 2023 edge is +0.003), but both its tails are worse than S1's.
- S2 concentrates into calm years (best S in 2021/2023) yet deepens tails and
  loses 2022/2024/2025 vs S1; S4's wider detector turns 2022 negative.
- S1 halves S0's worst day (-1.08 vs -1.92) and cuts maxDD (-1.70 vs -2.28) at
  the cost of lower sums in 2022/2024/2025 — the v399 trade-off is confirmed.
- Diagnostics: all 5498 fills on-grid, f in 16..238, zero missing 1m/sigma legs
  inside the 5y window; n=4 share peaks in stress years (2021: 14%, 2025: 15%).
