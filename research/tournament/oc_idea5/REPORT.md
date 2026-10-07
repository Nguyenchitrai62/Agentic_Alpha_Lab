# oc_idea5 REPORT: premium-gated book flips (veto reversals into dislocated tape)

## Setup

Book = `forward_v205.research_books_d2` (rebuilt exactly, same math/files as
oc_bookvol); opens = v154 4h perp opens; grid 2021-09-24..2026-09-23
(10956 bars, 10955 scored after dropping the last no-forward bar).
Metric per bar: `pn[t] = sum_c ws_c[t]*r_c[t] - 0.0005*TO[t]`,
`r = open[t+1]/open[t]-1`, `TO = sum|ws[t]-ws[t-1]|` (first vs flat, each
variant's own turnover). Equity compounded from 1.0. BASE = deployed 60d
book-vol scale (0.25/sig, cap 2; mean scale 1.47 — bit-identical to oc_bookvol
V0, see test). GATE = BASE with per-coin 1-bar veto of strict reversals
(`sign(w[T])*sign(w[T-1])<0`, zero never flips) INTO a |z|>2 dislocation:
long into z>+2 / short into z<-2, max 1-bar delay, no stacking, per-coin
independent. Premium: `p(h)=1e4*ln(CB/BN)` bps (Coinbase hourly close /
hourly_ext perp close); `x(T)=p(T-1h)` (hour completed at T);
`z(T)=(x-mean(W))/std(W)`, W = up to 540 prior 4h x in [T-90d,T), min 270.
Every input bar has START < T; bars with START >= 2026-09-24 00:00 UTC
dropped. BNB has no Coinbase listing (veto never fires); NaN z never fires.
Full numbers in `results.json`. No post-hoc change to any definition,
threshold, or the decision rule.

## 1. Coverage / fire rates (descriptive, no outcomes)

x/z coverage on scored grid: BTC 99.97/99.97%, ETH 99.97/99.97%,
SOL 99.97/99.97%, XRP 63.9/61.5%, BNB 0/0%.
XRP is blind 2021-09-24..2023-07-13 19:00 UTC (Coinbase US delisting gap;
resumes 2023-07-13 20:00; 15798/43824 window hours missing) — pre-registered
fail-safe, no veto there. SOL x starts 2021-06-17 so z is warm by grid start
(90d+ history via the extended 4h axis).

| year | flip rate (coin-bars) | vetoes (coin-bars) | veto rate |
|---|---|---|---|
| 2021-09-24 | 1.89% | 3 | 0.027% |
| 2022-09-24 | 1.28% | 2 | 0.018% |
| 2023-09-24 | 1.52% | 3 | 0.027% |
| 2024-09-24 | 2.04% | 11 | 0.101% |
| 2025-09-24 | 1.61% | 6 | 0.055% |
| 5y total | — | 25 / 54775 | 0.046% |

The gate fires 25 times in 5 years (~2.5% of ~1000 strict reversals):
|z|>2 reversals INTO the dislocation are rare at 4h-book frequency.

## 2. Per anchor year: net return / max DD / Sharpe (sqrt(2190))

BASE deployed 60d (reproduces oc_bookvol V0 exactly):

| year | ret | max DD | Sharpe | worst day |
|---|---|---|---|---|
| 2021-09-24 | +0.3049 | 0.2281 | 1.07 | -0.0678 |
| 2022-09-24 | +0.6417 | 0.1051 | 1.92 | -0.0565 |
| 2023-09-24 | +0.9678 | 0.1530 | 2.54 | -0.0491 |
| 2024-09-24 | +1.1556 | 0.1046 | 2.93 | -0.0540 |
| 2025-09-24 | +0.8179 | 0.1359 | 2.24 | -0.1390 |
| pooled 5y | +15.52x | 0.2281 | 2.14 | -0.1390 |

GATED |z|>2 (single variant):

| year | ret | max DD | Sharpe | worst day |
|---|---|---|---|---|
| 2021 | +0.3048 | 0.2281 | 1.07 | -0.0678 |
| 2022 | +0.6393 | 0.1051 | 1.91 | -0.0565 |
| 2023 | +0.9649 | 0.1544 | 2.54 | -0.0491 |
| 2024 | +1.1513 | 0.1046 | 2.93 | -0.0540 |
| 2025 | +0.8169 | 0.1359 | 2.24 | -0.1390 |
| pooled | +15.43x | 0.2281 | 2.13 | -0.1390 |

Turnover cost drag (5y total): BASE 0.25824, GATE 0.25818 (saves 0.00005 —
3 fewer unit-turnovers in 5y, as expected from 25 held coin-bars).

## 3. Decision (pre-registered: dDD>0 in >=4/5 AND LOYO-DD >=4/5 AND worst-day-not-worse >=4/5)

| year | dDD (BASE-GATE, + = less DD) | dRet (GATE-BASE) | dSharpe | worst-day GATE>=BASE |
|---|---|---|---|---|
| 2021 | +0.000000 | -0.000052 | -0.0001 | yes (equal) |
| 2022 | +0.000000 | -0.002378 | -0.0053 | yes (equal) |
| 2023 | -0.001422 | -0.002950 | -0.0051 | yes (equal) |
| 2024 | +0.000005 | -0.004287 | -0.0080 | yes (equal) |
| 2025 | +0.000000 | -0.000965 | -0.0015 | yes (equal) |

dDD>0 in 1/5 years (only 2024, by 0.5 bps of DD); LOYO-DD 0/5;
worst-day-not-worse 5/5 (all equal — the 25 held bars never contain the
yearly worst day). Return and Sharpe are negative in 5/5 years (tiny:
-5..-43 bps/yr). First-four-year sensitivity (descriptive): dDD 1/4,
tail 4/4 — same conclusion.

## Verdict

NOT PROMISING: the |z|>2 veto fires 25 coin-bars in 5y and moves nothing —
dDD>0 in 1/5 (LOYO 0/5) with return/Sharpe negative in 5/5; the worst-day bar
(5/5 equal) is met trivially because the gate is nearly never active.
Keep the un-gated book; close this direction for the veto form (a lower
threshold would be a new pre-registered direction, not a tune of this one).

## Caveats / post-hoc log

1. No post-hoc change to definitions, universe, windows, threshold (2.0),
   flip/veto/hold logic, or the decision rule. Only additions after the run:
   pooled stats, turnover-cost row, first-four sensitivity, XRP delisting
   dates (descriptive, rule untouched).
2. XRP blind 2021-09-24..2023-07-13 (delisting) + BNB always blind: the gate
   covers 3.6/5 coins on average. A per-coin-threshold or BTC-proxy-for-BNB
   variant was NOT tested (would be a new direction).
3. Strict-reversal only (entries/exits via zero never vetoed) + max 1-bar
   delay with no queue and no stacking: a vetoed flip executes at the latest
   one bar later at the then-current BASE (disclosed delay-not-queue).
4. Vectorised open-to-open P&L only (no spread beyond 0.05%/turnover, no
   funding, no governor/SL/TP/sleeve subtleties beyond `prod`); timing
   identical to oc_bookvol/oc_idea9 so the RELATIVE (GATE-BASE) is the object,
   not the absolute level.
5. All five years were available when the rule was frozen (assignment); no
   hidden year remains — any adoption needs prospective validation.
6. Repro: `research/tournament/oc_idea5/{PLAN.md,compute_idea5.py,
   results.json,REPORT.md}` (hourly data only, one process, RAM < 1 GB) +
   `tests/test_oc_idea5.py`.
