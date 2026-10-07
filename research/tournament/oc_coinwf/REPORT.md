# oc_coinwf REPORT: walk-forward per-coin dip weights (idea #12)

## Setup

Majors (BTC/ETH/SOL/BNB/XRP) x R2 rungs (`x1` in {2.5,3,3.5,4,5}) from
`research/tournament/ext/fills_U_ext.parquet`: 6876 fills, outcome `y1.0`
(exact net at TP 1.0 sigma, fees/funding in). Years = 5 anchors
2021-09-24..2025-09-24, `[anchor, anchor+365d)` keyed by `t_fill`
(990/1045/1330/989/1144 fills; T = t_fill - f verified on 4h boundaries).
Per anchor k: training pool = fills with `t_fill` in (2020-08-01, A_k - 7d);
`score_c = mean(y1.0)/std(y1.0, ddof=1)` per coin; `w_raw = clip(score /
mean(score), 0.5, 1.5)`; `w = w_raw / mean(w_raw)` (mean 1). Weights applied
to every R2 rung of the coin in year k. No fallback triggered (5/5 finite
positive-mean scores every year). Script `compute_coinwf.py` -> `results.json`
(this file renders it). Definitions frozen in PLAN.md before outcomes.
All five years are research data per assignment; a PROMISING result would still
need prospective validation.

## 1. Weights per year (score = mean/std of y1.0 over history; XRP shown)

| year | BTC w (score) | ETH w (score) | SOL w (score) | BNB w (score) | XRP w (score) |
|---|---|---|---|---|---|
| 2021-09-24 | 0.804 (0.159) | 1.163 (0.230) | 0.495 (0.089) | 1.412 (0.279) | 1.126 (0.223) |
| 2022-09-24 | 0.855 (0.168) | 1.179 (0.231) | 0.800 (0.157) | 1.167 (0.229) | 0.999 (0.196) |
| 2023-09-24 | 0.888 (0.133) | 1.304 (0.195) | 0.497 (0.070) | 1.139 (0.170) | 1.171 (0.175) |
| 2024-09-24 | 0.995 (0.163) | 1.258 (0.206) | 0.782 (0.128) | 1.022 (0.167) | 0.944 (0.155) |
| 2025-09-24 | 1.021 (0.174) | 1.161 (0.197) | 0.898 (0.153) | 0.950 (0.161) | 0.970 (0.165) |

Pattern: ETH overweight every year (1.16-1.30); SOL underweight every year
(0.50-0.90); XRP near 1 except 2021/2023 overweight (~1.13-1.17). History
depth grows 1345 -> 5704 rows (per-coin n in results.json).

## 2. Weighted vs unweighted per year (sums in y1.0 units; win = P(y1.0>0))

| year | n | S_u | S_w | S_w vs 95% S_u | win | worst_u | worst_w | maxDD_u | maxDD_w | DD<= |
|---|---|---|---|---|---|---|---|---|---|---|
| 2021-09-24 | 990 | 3.7766 | 3.3669 (89.2%) | FAIL | 0.688 | -0.4301 | -0.5041 | 0.4354 | 0.5041 | FAIL |
| 2022-09-24 | 1045 | 0.3934 | 0.5341 (135.8%) | PASS | 0.695 | -1.9236 | -1.9209 | 2.2818 | 2.3049 | FAIL |
| 2023-09-24 | 1330 | 5.2761 | 4.7647 (90.3%) | FAIL | 0.773 | -0.4963 | -0.6501 | 0.4963 | 0.6501 | FAIL |
| 2024-09-24 | 989 | 4.0658 | 3.8815 (95.5%) | PASS | 0.699 | -0.5070 | -0.5451 | 0.5070 | 0.5451 | FAIL |
| 2025-09-24 | 1144 | 1.5380 | 1.4981 (97.4%) | PASS | 0.656 | -1.0180 | -1.0145 | 1.2686 | 1.2611 | PASS |

Win rate is identical weighted/unweighted by construction (all w > 0, sign
preserved). Worst day / maxDD from the UTC-calendar daily-sum path (cumsum
from 0, peak includes 0). Mean y1.0 per coin per year (bps): 2021 SOL best
(+79.6, weight 0.50); 2022 XRP best (+39.4, weight 1.00) but SOL worst
(-28.7, weight 0.80); 2023 SOL best (+94.8, weight 0.50); 2024 SOL best
(+69.3, weight 0.78); 2025 XRP best (+44.4, weight 0.97) — the scheme
systematically underweights the realised best coin (SOL) in 3 of 5 years.

## 3. Decision (PROMISING = maxDD_w <= maxDD_u in >=4/5 AND S_w >= 0.95 S_u in >=4/5)

DD pass 1/5 (only 2025-26) AND sum95 pass 3/5 (2022/2024/2025) -> NOT PROMISING.

## Caveats / post-hoc log

1. No post-hoc change: formula, pools, metrics, and rule are exactly PLAN.md;
   single run, no variant iteration.
2. History filter follows the assignment literally (`t_fill` < anchor - 7d);
   `t_exit` (hours later) is not filtered, so a fill days before the embargo
   edge could exit after it — negligible given exits land within the bar/day,
   but a strict `t_exit` embargo would be the cleaner walk-forward rule.
3. Year keyed by `t_fill`; harness keys by `T` (<= 4h earlier). Boundary
   crossings are negligible here (same per-year counts 990/1045/1330/989/1144).
4. `mean(w) = 1` equalises average weight, not year exposure: coin counts
   differ within a year, so total weighted exposure drifts slightly.
5. All-mean-positive history scores keep weights in [0.50, 1.42]; no fallback
   year occurred (fallback path is unit-tested but unused).

## One-line verdict

NOT PROMISING: Sharpe-weighted per-coin dip sizes cut drawdown in only 1/5
years and keep >=95% of the unweighted sum in only 3/5 years — keep equal coin
exposure.
