# oc_bullshort REPORT: mirror bear-filter — gate book SHORTS in bull regimes (5y vectorised)

Book = `forward_v205.research_books_d2` (rebuilt exactly); opens = v154 4h
opens; grid 2021-09-24..2026-09-23 (10955 bars; bear 46.6% / bull 53.4% of
bars). Metric per bar: `pn[t] = sum_c ws_c[t]*r_c[t] - 0.0005*TO[t]`,
`r = open[t+1]/open[t]-1`, `TO = sum|ws[t]-ws[t-1]|` (first vs flat), per-variant
deployed scale `s = min(2, 0.25/sig)`, `sig = std(own u[t-360..t-1])*sqrt(2190)`
(min 120). Equity compounded from 1.0; year stats on year-rebased equity.
Legs = scaled gross `ws*r` by sign(ws) before costs. Full numbers in `results.json`.

## 1. Per anchor year: net return / max DD / Sharpe / long-short legs

B0 baseline (v410 bear-long filter: longs x0.5 in bear; mean|w| 0.106, cost 0.244):

| year | ret | max DD | Sharpe | long | short |
|---|---|---|---|---|---|
| 2021-09-24 | +0.332 | 0.145 | 1.40 | +0.109 | +0.236 |
| 2022-09-24 | +0.523 | 0.105 | 1.70 | +0.464 | +0.037 |
| 2023-09-24 | +0.984 | 0.153 | 2.57 | +0.850 | -0.073 |
| 2024-09-24 | +1.102 | 0.105 | 2.85 | +0.723 | +0.119 |
| 2025-09-24 | +0.795 | 0.136 | 2.26 | +0.389 | +0.284 |
| pooled 5y | +14.18x | 0.172 | 2.18 | | |

B1 (B0 + shorts x0.5 in bull; mean|w| 0.099, cost 0.229):

| year | ret | max DD | Sharpe | long | short |
|---|---|---|---|---|---|
| 2021 | +0.297 | 0.166 | 1.28 | +0.109 | +0.210 |
| 2022 | +0.535 | 0.114 | 1.72 | +0.463 | +0.043 |
| 2023 | +0.947 | 0.148 | 2.52 | +0.850 | -0.097 |
| 2024 | +0.953 | 0.112 | 2.57 | +0.721 | +0.041 |
| 2025 | +0.779 | 0.137 | 2.22 | +0.390 | +0.275 |
| pooled | +12.47x | 0.177 | 2.09 | | |

B2 (B0 + shorts x0 in bull; mean|w| 0.090, cost 0.210):

| year | ret | max DD | Sharpe | long | short |
|---|---|---|---|---|---|
| 2021 | +0.262 | 0.188 | 1.16 | +0.109 | +0.181 |
| 2022 | +0.518 | 0.133 | 1.68 | +0.442 | +0.047 |
| 2023 | +0.909 | 0.142 | 2.45 | +0.840 | -0.111 |
| 2024 | +0.803 | 0.139 | 2.26 | +0.701 | -0.026 |
| 2025 | +0.761 | 0.133 | 2.19 | +0.391 | +0.263 |
| pooled | +10.62x | 0.188 | 1.98 | | |

## 2. Decision (pre-registered: dRet > 0 AND dDD > 0 in >= 4/5 years AND LOYO >= 4/5 each)

| variant | dRet/y (V-B0) | Ret + | LOYO-Ret | dDD/y (B0-V, + = less DD) | DD + | LOYO-DD | verdict |
|---|---|---|---|---|---|---|---|
| B1 x0.5 | -0.034/+0.012/-0.037/-0.149/-0.017 | 1/5 | 0/5 | -0.021/-0.009/+0.005/-0.007/-0.001 | 1/5 | 0/5 | FAIL |
| B2 x0 | -0.069/-0.005/-0.075/-0.298/-0.034 | 0/5 | 0/5 | -0.043/-0.028/+0.011/-0.034/+0.003 | 2/5 | 0/5 | FAIL |

First-four-year sensitivity (descriptive): B1 Ret 1/4 DD 1/4; B2 Ret 0/4 DD 1/4 — same conclusion.

## Caveats / post-hoc log

1. No post-hoc change to definitions, universe, windows, or the decision
   rule. Only addition after the run: pooled stats and the first-four-year
   sensitivity (descriptive, rule untouched).
2. The motivating 2023 short leg got WORSE under the gate (B0 -0.073 ->
   B1 -0.097 -> B2 -0.111 scaled gross): halving bull shorts also halves the
   bull-short winners inside 2023, and each variant's own vol rescaling
   (mean scale ~1.58 all rows) partly re-levers the remainder — so the mirror
   of the long-side filter does not mirror its economics.
3. Vectorised open-to-open P&L only (0.05%/turnover, no funding, no
   governor/SL/TP/sleeve); timing identical to oc_bookic/bookvol so the
   RELATIVE ranking is the object of study, not the absolute level.
4. All five years were available when the rule was frozen (assignment); no
   hidden year remains — any adoption needs prospective validation.

## One-line verdict

NOT PROMISING for either mirror variant: halving (B1) or flattening (B2) book
shorts in bull regimes loses return in 4-5/5 years and raises drawdown in 3-4/5
years (LOYO 0/5) — keep book shorts unchanged on top of the v410 bear-long filter.
