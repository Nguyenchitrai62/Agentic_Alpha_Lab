# oc_postflush REPORT: post-flush recovery book overlay (idea #30)

## Setup
Event at 4h close C (bar T = C-4h): >= 3 majors with hourly low
`L < O*(1-2.5*sigma4)` AND hourly close `Cc > O*(1-1.0*sigma4)`, sigma4 =
v293 (std of 4h-open pct_change, rolling 360, min 120, shifted 1; opens from
`research/tournament/ext/hourly_ext.parquet`). Signal: next bar long each
recovered coin equal weight; entry 1m OPEN at C+5min (maker 0.0002), exit 1m
OPEN at C+4h (taker 0.00055); longs pay 0.0001 iff exit hour in {0,8,16}
(gate adverse funding). Event valid only if ALL recovered legs priced
(34 raw events, 34 valid, 0 dropped). Years keyed by C in
[A, A+365d), A = 2021-09-24..2025-09-24; exits <= 2026-09-24 00:00 UTC.
Script: `compute_postflush.py` -> `events_postflush.parquet`, `results.json`
(this file renders it). All five years are research data per assignment;
a PROMISING overlay would still need prospective validation. Definitions
frozen in PLAN.md before any outcome was computed. No post-hoc changes.

## 1. Per anchor year: next-bar net return (equal-weight recovered legs)
Cost context: entry+exit fees 7.5 bps, +10 bps when a funding settlement is
held; event means below are net.

| year | n | mean (bps) | median (bps) | win rate | t-stat | worst event (net bps @ C, coins) | total |
|---|---|---|---|---|---|---|---|
| 2021-09-24 | 10 | -33.3 | -84.1 | 0.400 | -0.21 | -736.9 @ 2022-05-12 (BTC+SOL+BNB+XRP) | -0.0333 |
| 2022-09-24 | 5 | -291.1 | -34.5 | 0.400 | -1.01 | -1409.3 @ 2022-11-08 (BTC+ETH+SOL) | -0.1456 |
| 2023-09-24 | 7 | -24.1 | +3.4 | 0.571 | -0.31 | -278.2 @ 2024-08-05 (ETH+BNB+XRP) | -0.0169 |
| 2024-09-24 | 2 | +25.8 | +25.8 | 1.000 | NaN | +25.6 @ 2024-11-11 (ETH+SOL+BNB, min of 2) | +0.0052 |
| 2025-09-24 | 10 | +7.5 | +34.5 | 0.500 | +0.16 | -280.5 @ 2026-06-04 (all 5) | +0.0075 |

Mean recovered-set size 3.0-3.9 coins/event. Win rate >= 0.5 in 2/5 years.

## 2. LOYO + dip-stream correlation
LOYO (parameter-free overlay: held-out year mean == sequential mean):
passes 2024, 2025 only -> 2/5. Dip correlation = Pearson(overlay C-day P&L,
dip T-day `sum(size_dep*y_dep)` via harness5.load, calendar days incl. zeros):
+0.052 / +0.024 / +0.376 / +0.205 / -0.108 for 2021..2025 (365 days each).
No consistent hedge or amplifier relationship; 2023's +0.38 comes with a
negative overlay mean.

## 3. Decision (PROMISING = mean>0 in >=4/5 AND LOYO >=4/5 AND >=10 events/year)

| check | result |
|---|---|
| mean net > 0 years | 2/5 (2024, 2025) |
| LOYO pass years | 2/5 (2024, 2025) |
| min events per year | 2 (2024: 2, 2022: 5, 2023: 7) -> floor FAIL |

## Caveats
1. Rare events: 34 in 5 years; 2022's -291 bps mean is one FTX-flush
   left-tail (-1409 bps, 2022-11-08) dominating n=5 — the overlay adds
   crash exposure, not diversification.
2. The two positive years are tiny (+25.8 bps on n=2; +7.5 bps, t=+0.16)
   and below/near the ~7.5-17.5 bps round-trip + funding cost.
3. Hourly-low proxy for "traded": a 1m wick below the hourly low would only
   ADD B1 triggers, not remove the losing left tail.

## Verdict
NOT PROMISING: post-flush recovery book drift averages negative in 3/5 years (2/5 positive, LOYO 2/5) and events are too rare (2-10/year, floor needs >=10 every year) — do not hold recovered flush coins as a book long.
