# oc_bookweekend REPORT: book flat on weekends (idea #50)

Book = `forward_v205.research_books_d2` (rebuilt exactly, cell-identical
formula to oc_dvolshort/oc_longcap); opens = v154 4h opens. Grid = 10955
bars (2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open)
x 5 coins = 54775 rows. BASE = raw book + v410 bear-long filter FIRST
(longs x0.5 where BTC 4h open < rolling-1200 mean, min_periods=600,
NaN -> not bear; flag at T uses open[T] inclusive). RULE (fixed in
PLAN.md): holding bars starting Sat 00:00..Mon 00:00 UTC (weekday 5/6, 12
bars per full weekend) -> target 0, else BASE. Screen = open-to-open 4h
returns with assignment costs: net cell = `w*R1 - 0.0005*|w - w_prev|`
per sym (first prev = 0; each path its own prev, so the Sat-00:00 close
and Mon-00:00 reopen turnover is charged to RULE). Weekend/weekday split
uses BASE net cells with bar-T cost attributed to bar T (Sat close cost in
weekend leg, Mon reopen cost in weekday leg). Equity per year reset to 1,
`eq *= 1 + sum_s pnl`; maxDD = peak-to-trough; worst week = min 42-bar
compounded return. Full tables in `results.json`; `panel.parquet` holds
per-(T,sym) rows.

## Verdict

NOT PROMISING (as assigned): net book P&L RULE >= BASE in 0/5 years and
maxDD not worse (RULE <= BASE) in 1/5 years (only 2024-25, by 0.07pp).

## Per-year screen (net, portfolio-return units; costs included)

| year | bars | wknd share | BASE weekend / weekday P&L | cost base / rule | book P&L base / rule | worst week base / rule | maxDD base / rule | P&L ok | DD ok |
|---|---|---|---|---|---|---|---|---|---|
| 21-22 | 2190 | 0.284932 | 0.095026 / 0.183869 | 0.021773 / 0.025815 | 0.278895 / 0.173980 | -0.055289 / -0.063615 | 0.092278 / 0.146666 | no | no |
| 22-23 | 2190 | 0.287671 | 0.093004 / 0.142441 | 0.027615 / 0.038395 | 0.235444 / 0.124258 | -0.047268 / -0.053776 | 0.073721 / 0.109818 | no | no |
| 23-24 | 2196 | 0.286885 | 0.130051 / 0.414099 | 0.033313 / 0.044483 | 0.544150 / 0.394722 | -0.069471 / -0.046843 | 0.087902 / 0.110954 | no | no |
| 24-25 | 2190 | 0.284932 | 0.257537 / 0.260156 | 0.036403 / 0.047407 | 0.517693 / 0.239540 | -0.045930 / -0.037071 | 0.065296 / 0.064613 | no | yes |
| 25-26 | 2189 | 0.285062 | 0.075520 / 0.319204 | 0.031473 / 0.039824 | 0.394724 / 0.301807 | -0.075345 / -0.085499 | 0.087166 / 0.113346 | no | no |

Counts: P&L not lower 0/5; DD not worse 1/5. Full 5y path (context,
compounded from year-1 start): total P&L 1.970907 -> 1.234306 RULE
(-0.7366 over 5y); maxDD 0.104644 -> 0.146666 RULE. LOYO stability
(descriptive, no fitted parameter): P&L indicator 5/5, DD indicator 4/5
— stably negative, not a near-miss.

Read: the weekend leg of BASE is positive in ALL five years
(+0.076..+0.258), so flattening it mechanically discards P&L every year
(-0.09..-0.28 linear units/year); RULE also pays MORE turnover every year
(+0.004..+0.011 from the weekly close/reopen churn); and maxDD worsens in
4/5 years because the flat weekends remove diversifying positive drift
while Monday gaps re-enter at worse levels (worst week improves only in
2023 and 2024). The hypothesis is rejected as stated.

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, weekend mask, costs, or
   the decision rule. PLAN.md was written before
   `compute_bookweekend.py` ran.
2. Performance-only fix toward PLAN (verified, not outcome-driven):
   `weekend = np.asarray(grid.weekday) >= 5` (pandas DatetimeIndex.weekday
   is already an ndarray; the first run raised AttributeError on
   `.to_numpy()` before any output was written). Math unchanged.
3. BASE here != oc_dvolshort totals by construction: this screen applies
   the v410 bear filter first and charges 0.0005/unit turnover per the
   assignment (vs raw book + 0.0002 in oc_dvolshort). Do not compare
   absolute P&L across studies; only BASE-vs-RULE within this screen.
4. Vectorised open-to-open screen only (no vol target, governor, dip
   sleeve, funding, SL/TP, or engine limit path). Needs no prospective
   validation effort beyond the rejection: in-sample walk-forward style
   screen (fixed calendar rule, no fitting) already fails 0/5 and 1/5.

## One-line verdict

NOT PROMISING: weekend-flat book loses net P&L in 5/5 years and worsens
maxDD in 4/5 years — close the direction.
