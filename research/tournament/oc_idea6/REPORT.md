# oc_idea6 REPORT: basis-momentum dip throttle (IDEAS.md idea #6)

Universe: majors (BTC/ETH/SOL/BNB/XRP) x R2 depths (2.5/3/3.5/4/5), 5498
fills, outcome y_dep (exact net at deployed TP, fees + adverse funding
inside). Anchor years 2021-09-24 .. 2025-09-24
(n = 990/1045/1330/989/1144). Market-wide signal per 4h bar T: mom(T) =
BTC front-quarterly annualised basis(T) - basis(T-24h); basis(S) = last 4h
qb close strictly before S (delivery 1h from data/raw/qbasis_20261003 BTC
legs, UM preferred else CM, FRONT = nearest expiry E > C + 7d,
qb = ln(F/P)*365/DTE vs hourly_ext BTCUSDT perp; no 1m loaded). ONE
pre-registered rule: m = 0.5 on ALL 5 majors fills iff mom(T) < p20 else
1.0; p20 = 20th pct of mom over 4h grid bars strictly < anchor.
size_new = size_dep x m, scored with harness5 equal-exposure
renormalisation per year (timing only). Coverage 100% in all 5 years;
hourly venue share 91% UM / 9% CM (CM covers pre-2021-03 + gaps); one
process, < 1 GB. Full numbers in `results.json`.

## Sequential screen (cut-offs from strictly previous grid bars; renorm sizes)

| year | n | p20 | train bars | thr share | S_dep | S_new | gain | pass? |
|---|---|---|---|---|---|---|---|---|
| 21-22 | 990 | -0.0211 | 2506 | 0.093 | 4.485 | 4.574 | +0.089 | YES |
| 22-23 | 1045 | -0.0121 | 4696 | 0.100 | 0.924 | 0.862 | -0.062 | NO |
| 23-24 | 1330 | -0.0086 | 6886 | 0.274 | 6.627 | 6.371 | -0.256 | NO |
| 24-25 | 989 | -0.0082 | 9082 | 0.181 | 4.265 | 4.854 | +0.588 | YES |
| 25-26 | 1144 | -0.0073 | 11272 | 0.030 | 1.906 | 1.844 | -0.062 | NO |

(units native size*y_dep; S_dep > 0 every year; raw retention
0.97/0.89/0.83/1.03/0.95 - descriptive, renorm isolates timing.)

## Tail: worst daily sum and yearly maxDD of the daily-sum path (renorm sizes)

| year | W_dep | W_new | wd pass? | DD_dep | DD_new | dd pass? | tail pass? |
|---|---|---|---|---|---|---|---|
| 21-22 | -0.434 | -0.432 | YES | -0.539 | -0.566 | NO | NO |
| 22-23 | -1.915 | -2.012 | NO | -1.915 | -2.012 | NO | NO |
| 23-24 | -0.577 | -0.737 | NO | -0.577 | -0.737 | NO | NO |
| 24-25 | -0.703 | -0.428 | YES | -0.703 | -0.428 | YES | YES |
| 25-26 | -0.498 | -0.505 | NO | -0.588 | -0.596 | NO | NO |

Full path (concatenated renormalised daily sums, descriptive):
worst day -1.91 -> -2.01 (worse, driven by 2022); maxDD -1.91 -> -2.01.

## LOYO gain (cut-offs from grid bars in the other 4 year windows, renorm inside held-out)

| held-out | p20 | gain | pass? |
|---|---|---|---|
| 21-22 | -0.0047 | -0.436 | NO |
| 22-23 | -0.0053 | +1.290 | YES |
| 23-24 | -0.0047 | +0.290 | YES |
| 24-25 | -0.0050 | +0.672 | YES |
| 25-26 | -0.0055 | -0.171 | NO |

(LOYO p20 -0.0047..-0.0055 sits above sequential p20 -0.021..-0.007: the
pre-2021 history carries a fatter negative-mom tail. The verdict does not
hinge on which pool is used - both families fail the 4/5 bar.)

## Descriptive (NOT part of the rule)

Per-coin gain split (renormalised sizes; throttle is market-wide so BTC is
throttled too):

| year | BTC | ETH | SOL | BNB | XRP |
|---|---|---|---|---|---|
| 21-22 | +0.070 | +0.023 | -0.005 | +0.008 | -0.008 |
| 22-23 | -0.044 | -0.069 | +0.165 | -0.058 | -0.056 |
| 23-24 | -0.091 | -0.068 | +0.011 | -0.110 | +0.002 |
| 24-25 | +0.065 | +0.177 | +0.088 | +0.118 | +0.141 |
| 25-26 | -0.027 | -0.011 | -0.015 | +0.007 | -0.017 |

Spearman rho(mom, y_dep): -0.09/-0.00/+0.00/+0.14/-0.02 - no consistent rank
relation; the 2024 gain is a timing coincidence, not a stable ordering
(2024 rho is the only positive one and the year still only passes because
one tail window was dodged).

## Decision (pre-registered: gain>0 in >=4/5 AND LOYO-gain >=4/5 AND tail >=4/5)

gain 2/5, LOYO 3/5, tail (worst-day AND maxDD not worse) 1/5.

## One-line verdict

NOT PROMISING: the basis-momentum throttle (x0.5 iff mom < pre-anchor p20)
gains in 2/5 years sequentially and 3/5 LOYO while deepening the worst day
and the yearly maxDD in 4/5 years - a fast basis collapse does not mark
worse dip fills; close this direction (impulse form as well as level form).

## Caveats / post-hoc log

1. No post-hoc change to the signal (mom = basis(T) - basis(T-24h), strict-<
   4h closes, UM-preferred/CM-fallback, 7-day roll), the single p20/x0.5
   market-wide rule, the bar-pool cut-offs, or the 3-part decision rule.
   Two definition-preserving code fixes before the first successful run
   (both before any outcome was produced): a missing parenthesis (syntax)
   and tz-aware vs tz-naive dtypes in the delivery/perp asof join. The
   scored run above is the first and only outcome computation.
2. No roll adjustment: mom windows spanning a quarterly front roll keep the
   raw annualised difference (disclosed in PLAN.md; rolls ~4/year by the
   7-day rule).
3. Rung-level equal-exposure screen is the cheap gate only (same harness as
   the v254 re-screen): sleeve/budget path effects matter live and no
   engine run is claimed here.
4. All five years were available when the rule was frozen (assignment); no
   hidden year remains - any adoption needs prospective validation.
5. Repro: `research/tournament/oc_idea6/{PLAN.md,analyze_idea6.py,
   features_idea6.parquet,results.json,REPORT.md}` (delivery-hourly +
   fills only, one process, RAM < 1 GB) + `tests/test_oc_idea6.py`.
