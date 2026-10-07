# oc_dombook — REPORT: walk-forward BTC-dominance book scaler (5y vectorised)

Book = `forward_v205.research_books_d2` (rebuilt exactly); opens = v154 4h
opens; grid 2021-09-24..2026-09-23 (10955 bars, 6 orphans excluded).
Regime `dom30[t]` = BTC 30d log return minus equal-weight majors 30d log
return (180 bars, full opens history, causal). Scaler (ONE, pre-registered):
book weights x1.25 in top `dom30` tercile / x0.75 bottom / x1.0 middle,
cuts = 33rd/67th pct over bars strictly before each anchor. Both legs carry
the deployed vol scale (0.25 / trailing-60d realised vol of unscaled book
P&L, cap 2; mean scale 1.35-1.61). Net per bar:
`pn[t] = sum ws[t]*r[t] - 0.0005*sum|ws[t]-ws[t-1]|`, `r = open[t+1]/open[t]-1`,
equity compounded from 1.0 per year. Full numbers in `results.json`.

## 1. Per anchor year: net return / max DD / Sharpe (ANN x sqrt(2190))

| year | base ret | scaled ret | dRet | base DD | scaled DD | dDD | base Sh | scaled Sh |
|---|---|---|---|---|---|---|---|---|
| 2021-09-24 | +0.305 | +0.311 | +0.006 | 0.228 | 0.257 | -0.028 | 1.07 | 1.10 |
| 2022-09-24 | +0.642 | +0.672 | +0.030 | 0.105 | 0.105 | +0.000 | 1.92 | 1.86 |
| 2023-09-24 | +0.960 | +1.135 | +0.176 | 0.153 | 0.152 | +0.002 | 2.53 | 2.73 |
| 2024-09-24 | +1.156 | +1.260 | +0.105 | 0.105 | 0.128 | -0.023 | 2.94 | 2.96 |
| 2025-09-24 | +0.818 | +0.871 | +0.054 | 0.136 | 0.136 | +0.000 | 2.24 | 2.27 |
| pooled 5y | +15.45x | +18.79x | +3.34 | 0.228 | 0.257 | -0.028 | 2.13 | 2.19 |

Cuts (lo/hi) per year: 2021 -0.058/+0.053 (8798 hist bars), 2022
-0.055/+0.050, 2023 -0.046/+0.053, 2024 -0.041/+0.046, 2025 -0.040/+0.046.
Tercile sizes stay in the hundreds (min 171). Turnover-cost drag per year:
base 0.038-0.062 vs scaled 0.041-0.073 — the tilt trades more, ranking
unaffected. Base leg reproduces oc_bookvol BASE to the year-definition
tolerance (literal +365d here drops 6 orphan bars from 2023-24).

## 2. Decision (pre-registered: return sign >= 4/5 AND return-LOO >= 4/5 AND DD not-worse >= 4/5)

| leg | walk-forward | LOO holds | gate |
|---|---|---|---|
| return (dRet > 0) | 5/5 (+0.006/+0.030/+0.176/+0.105/+0.054) | 4/5 (miss: 2024 fold, pooled-train excess -0.15) | PASS |
| DD (scaled <= base) | 3/5 (2021 -0.028, 2024 -0.023 worse) | 0/5 descriptive (every train mean dragged by 2021/2024) | FAIL |

First-four-year sensitivity (descriptive): return 4/4, DD 2/4 — same
conclusion. The tilt adds return every year but buys it with deeper
drawdowns in exactly the two years (2021, 2024) where the extra size meets
the book's worst slides; the pooled 5y DD rises 0.228 -> 0.257.

## Caveats / post-hoc log

1. Bug fix after first run (code did not match PLAN, same class as the
   oc_ethbtc caveat-1 fix): per-year cut-offs were quantiled on the
   books-grid `dom` (starts 2021-09-24, empty history for 2021 -> NaN cuts,
   scaled == base in 2021) instead of the full opens-history `dom_full`
   from 2017 as PLAN requires. Fixed; 2021 now uses 8798 prior bars.
   Outcome inspected before the fix beyond the NaN plus this log entry.
2. LOO turnover clarification (no definition change): LOO folds recompute
   the L1 turnover from the LOO-cut scaled weights with the same formula
   (turnover must follow the weights actually held); `s0` and returns are
   bit-identical to the walk-forward run.
3. Vectorised open-to-open P&L only (0.05%/turnover, no funding/governor/
   SL/TP/sleeve); year-rebased equity per year; the RELATIVE scaled-vs-base
   ranking is the object of study, not the absolute level.
4. All five years were available when the rule was frozen (assignment); no
   hidden year remains — any adoption needs prospective validation.

## One-line verdict

NOT PROMISING as assigned: the dominance tilt lifts net return in 5/5 years
(LOO 4/5) but draws down worse in 2/5 years (2021: 0.228 -> 0.257, 2024:
0.105 -> 0.128; DD gate 3/5 < 4/5, DD-LOO 0/5) — do not scale the book on
dom30 terciles without a drawdown guard, direction closed pending one.
