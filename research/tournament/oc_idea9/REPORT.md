# oc_idea9 REPORT: US-equity overnight-gap book tilt (5y vectorised)

Book = `forward_v205.research_books_d2` (rebuilt exactly, BASE matches
oc_bookvol V0 to the printed digit); opens = v154 4h opens; grid
2021-09-24..2026-09-23 (10955 bars). Per bar:
`pn[t] = sum_c ws_c[t]*r_c[t] - 0.0005*TO[t]`, `r = open[t+1]/open[t]-1`,
equity compounded from 1.0. TILT = BASE x dial, dial = 0.75 iff the SPX
prior-session log-return (latest `^GSPC` close strictly before T) is below
the pre-anchor 25th pct (expanding history from 2016-01-01, 7d embargo),
else 1.0. Fire rate 28.6% (5y). All dial inputs strictly before T.
Full numbers in `results.json`; SPX file + manifest in
`data/raw/newinfo_idea9/`.

## 1. Per anchor year: net return / max DD / Sharpe (x sqrt(2190))

BASE deployed 60d book-vol (mean scale 1.47):

| year | ret | max DD | Sharpe | worst day |
|---|---|---|---|---|
| 2021-09-24 | +0.305 | 0.228 | 1.07 | -0.0678 |
| 2022-09-24 | +0.642 | 0.105 | 1.92 | -0.0565 |
| 2023-09-24 | +0.968 | 0.153 | 2.54 | -0.0491 |
| 2024-09-24 | +1.156 | 0.105 | 2.93 | -0.0540 |
| 2025-09-24 | +0.818 | 0.136 | 2.24 | -0.1390 |
| pooled 5y | +15.52x | 0.228 | 2.14 | -0.1390 |

TILT gap-dial x0.75 (fire 39/32/21/24/26% by year):

| year | ret | max DD | Sharpe | worst day |
|---|---|---|---|---|
| 2021 | +0.266 | 0.202 | 1.02 | -0.0508 |
| 2022 | +0.546 | 0.105 | 1.78 | -0.0565 |
| 2023 | +0.797 | 0.155 | 2.38 | -0.0491 |
| 2024 | +1.038 | 0.102 | 2.84 | -0.0540 |
| 2025 | +0.677 | 0.135 | 2.10 | -0.1393 |
| pooled 5y | +11.02x | 0.202 | 2.02 | -0.1393 |

Turnover cost drag (5y total): BASE 0.258, TILT 0.263 units — negligible.

## 2. Decision (pre-registered: dDD > 0 in >= 4/5 AND LOYO-DD >= 4/5 AND worst-day not worse in >= 4/5)

| metric | per-year (2021..2025) | score | LOYO |
|---|---|---|---|
| dDD (BASE-TILT) | +0.0260/+0.0004/-0.0024/+0.0025/+0.0007 | 4/5 | 4/5 |
| worst-day not worse | T/T/T/T/F (2025 worse by 0.0003) | 4/5 | — |
| dRet (descriptive) | -0.038/-0.096/-0.170/-0.118/-0.141 | neg 5/5 | — |
| dSharpe (descriptive) | -0.05/-0.14/-0.16/-0.10/-0.14 | neg 5/5 | — |

First-four-year sensitivity (descriptive): dDD 3/4, tail 4/4.

## Caveats / post-hoc log

1. No post-hoc change to definitions, thresholds, windows, or the rule.
2. The DD gain is tiny outside 2021 (<= 0.25 pp; 2021 cuts 2.6 pp off the
   highest-DD year) while return/Sharpe fall EVERY year (pooled 15.52x ->
   11.02x; Sharpe -0.05..-0.16/yr) — a steeper price than the idea's
   expected -0.2..0.0 pp/mo, so the mechanical pass should not drive
   adoption without a cheaper dial.
3. 2025 worst day is marginally worse (turnover churn on dial steps).
4. Vectorised open-to-open P&L only (no funding/governor/sleeve effects);
   timing convention identical to oc_bookvol, so the RELATIVE row is the
   object of study, not the absolute level.
5. All five years were available when frozen (assignment); any adoption
   needs prospective validation.

## One-line verdict

PROMISING by the pre-registered bar (dDD 4/5, LOYO-DD 4/5, worst-day 4/5),
but the DD buy is small outside 2021 and costs return/Sharpe in all five
years — keep as a documented weak dial, do not adopt as-is.
