# oc_bookvol REPORT: book-level volatility-targeting variants (5y vectorised)

Book = `forward_v205.research_books_d2` (rebuilt exactly); opens = v154 4h
opens; grid 2021-09-24..2026-09-23 (10955 bars). Metric per bar:
`pn[t] = sum_c ws_c[t]*r_c[t] - 0.0005*TO[t]`, `r = open[t+1]/open[t]-1`,
`TO = sum|ws[t]-ws[t-1]|` (first vs flat). Equity compounded from 1.0.
All scales use ONLY bars strictly before `t`. Full numbers in `results.json`.

## 1. Per anchor year: net return / max DD / Sharpe (annualised x sqrt(2190))

BASE deployed 60d book-vol (0.25/sig, cap 2; mean scale 1.47):

| year | ret | max DD | Sharpe |
|---|---|---|---|
| 2021-09-24 | +0.305 | 0.228 | 1.07 |
| 2022-09-24 | +0.642 | 0.105 | 1.92 |
| 2023-09-24 | +0.968 | 0.153 | 2.54 |
| 2024-09-24 | +1.156 | 0.105 | 2.93 |
| 2025-09-24 | +0.818 | 0.136 | 2.24 |
| pooled 5y | +15.52x | 0.228 | 2.14 |

(a) risk-parity 30d per-coin tilt (no book scale; mean|w| 0.084 vs 0.112):

| year | ret | max DD | Sharpe |
|---|---|---|---|
| 2021 | +0.293 | 0.149 | 1.27 |
| 2022 | +0.331 | 0.095 | 1.55 |
| 2023 | +0.734 | 0.082 | 2.79 |
| 2024 | +0.668 | 0.081 | 2.77 |
| 2025 | +0.573 | 0.110 | 2.18 |
| pooled | +6.83x | 0.149 | 2.09 |

(b) slow 120d book-vol (mean scale 1.37):

| year | ret | max DD | Sharpe |
|---|---|---|---|
| 2021 | +0.372 | 0.173 | 1.28 |
| 2022 | +0.658 | 0.098 | 2.07 |
| 2023 | +0.814 | 0.140 | 2.43 |
| 2024 | +1.213 | 0.088 | 3.13 |
| 2025 | +0.784 | 0.130 | 2.17 |
| pooled | +15.28x | 0.173 | 2.21 |

(c) semivariance 60d downside target (mean scale 1.52):

| year | ret | max DD | Sharpe |
|---|---|---|---|
| 2021 | +0.317 | 0.219 | 1.08 |
| 2022 | +0.678 | 0.131 | 1.83 |
| 2023 | +1.070 | 0.159 | 2.54 |
| 2024 | +1.218 | 0.103 | 2.95 |
| 2025 | +0.900 | 0.127 | 2.30 |
| pooled | +18.28x | 0.219 | 2.13 |

Turnover cost drag (5y total): BASE 0.258, (a) 0.177, (b) 0.234, (c) 0.265
units of equity — small vs multi-x gross, ranking unaffected.

## 2. Decision (pre-registered: improvement > 0 in >= 4/5 years AND LOYO >= 4/5, on EACH of Sharpe and DD)

| variant | dSharpe/y (V-BASE) | Sharpe + | LOYO-Sh | dDD/y (BASE-V, + = less DD) | DD + | LOYO-DD | verdict |
|---|---|---|---|---|---|---|---|
| (a) riskparity | +0.19/-0.37/+0.25/-0.16/-0.06 | 2/5 | 0/5 | +0.079/+0.010/+0.071/+0.024/+0.026 | 5/5 | 5/5 | FAIL (Sharpe) |
| (b) slow120 | +0.21/+0.15/-0.11/+0.19/-0.06 | 3/5 | 3/5 | +0.055/+0.008/+0.013/+0.016/+0.006 | 5/5 | 5/5 | FAIL (Sharpe 3/5) |
| (c) semi60 | +0.01/-0.09/-0.00/+0.02/+0.06 | 3/5 | 0/5 | +0.009/-0.026/-0.006/+0.002/+0.009 | 3/5 | 0/5 | FAIL (both) |

First-four-year sensitivity (repo selection window, descriptive): (a) Sharpe
2/4 DD 4/4; (b) Sharpe 3/4 DD 4/4; (c) Sharpe 2/4 DD 2/4 — same conclusion.

## Caveats / post-hoc log

1. No post-hoc change to definitions, universe, windows, or the decision
   rule. Only addition after the run: pooled stats, turnover-cost row and the
   first-four-year sensitivity (descriptive, rule untouched).
2. Grid starts 2021-09-24 (books availability), so year-1 scales run on
   partial windows for ~60d (120d: ~120d; min_periods 120/240, scale 1.0
   before that) — causal but colder start; year-1 DD leads every variant.
3. Turnover is undrifted L1 (`|ws[t]-ws[t-1]|`, no drift compounding) — a
   disclosed simplification; costs are small either way (see row above).
4. Vectorised open-to-open P&L only (no spread beyond 0.05%/turnover, no
   funding, no governor/SL/TP/sleeve/compounding subtleties beyond `prod`);
   timing convention identical to oc_bookic so the RELATIVE ranking is the
   object of study, not the absolute level.
5. All five years were available when the rule was frozen (assignment); no
   hidden year remains — any adoption needs prospective validation.

## One-line verdict

NOT PROMISING for any variant as assigned: slower-120d and risk-parity cuts
drawdown in 5/5 years (LOYO 5/5) but neither improves Sharpe in >= 4/5 years
(3/5 and 2/5), and the semivariance target fails on both — keep the deployed
60d book-level target.
