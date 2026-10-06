# oc_bearshort REPORT — bear-regime book short boost (idea #53)

Book = `forward_v205.research_books_d2` (rebuilt exactly, cell-checked vs
oc_dvolshort); opens = v154 4h opens. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins = 54775 rows. BASE = v410 BTC-only bear filter (longs x0.5 when BTC
4h open < 1200-bar mean, rolling 1200 min 600, open[T] inclusive). RULE =
BASE with bear-row SHORT targets x1.25 (bear longs stay x0.5 as v410;
non-bear rows bit-identical). Screen = open-to-open 4h returns with gate
costs, exactly as oc_dvolshort: net cell = `w*R1 - 0.0002*|w - w_prev|`
per sym (first prev = 0; each path its own prev chain). Short-leg sums use
BASE sign (`w_base < 0` == raw shorts) so base vs rule compare identical
rows. Equity per year reset to 1 and compounded as `eq *= 1 + sum_s pnl`;
maxDD = peak-to-trough; worst week = min 42-bar compounded return. Full
tables in `results.json`; `panel.parquet` holds per-(T,sym) rows. PLAN.md
was written before `compute_bearshort.py` ran; no post-hoc changes. Base
cross-check: per-year base P&L / maxDD / bear shares reproduce
oc_bookcoinbrake's v410 base exactly (2.061253 total, full-path DD
0.100471).

## Verdict

NOT PROMISING (as assigned): total book P&L higher in 3/5 years (needs
>= 4/5) AND maxDD not worse in 1/5 years (needs >= 4/5).

## Per-year screen (net, portfolio-return units; costs included)

| year | bear share | base shorts boosted | short P&L base / rule | total book P&L base / rule | worst week base / rule | maxDD base / rule | P&L higher | DD not worse |
|---|---|---|---|---|---|---|---|---|
| 21-22 | 0.763 | 0.886 | 0.138550 / 0.160727 | 0.291959 / 0.314106 | -0.055143 / -0.055143 | 0.086514 / 0.089416 | yes | no |
| 22-23 | 0.407 | 0.593 | 0.023087 / 0.029651 | 0.252013 / 0.258566 | -0.046676 / -0.046676 | 0.071462 / 0.076376 | yes | no |
| 23-24 | 0.217 | 0.453 | -0.043023 / -0.058738 | 0.564138 / 0.548412 | -0.069232 / -0.081831 | 0.087278 / 0.102328 | no | no |
| 24-25 | 0.138 | 0.281 | 0.044977 / 0.040134 | 0.539535 / 0.534682 | -0.045264 / -0.045264 | 0.062817 / 0.062817 | no | yes |
| 25-26 | 0.804 | 0.949 | 0.178139 / 0.217376 | 0.413608 / 0.452811 | -0.074825 / -0.075501 | 0.085657 / 0.086727 | yes | no |

Counts: P&L higher 3/5; DD not worse 1/5. Full 5y path (context,
compounded from year-1 start): maxDD 0.100471 -> 0.109458 rule (+0.90pp);
total P&L 2.061253 -> 2.108578 rule (+0.0473 over 5y).

Read: the boost does what it says — it amplifies the short leg in both
directions. In the three years base shorts were profitable (2021, 2022,
2025) total P&L rises (+0.0221, +0.0066, +0.0392), but maxDD worsens in
every one of those years (+0.29pp, +0.49pp, +0.11pp). In 2023, the one
year base shorts lost, the boost deepens the short loss by ~37%
(-0.0430 to -0.0587), cuts total P&L (-0.0157), worsens the worst week
(-0.0692 to -0.0818) and adds +1.50pp of maxDD — the single worst
interaction in the screen. In 2024 (13.8% bear share) the rule is nearly
neutral on both legs (extra turnover cost eats the small short gain).
Levering shorts x1.25 in bear rows buys return only by buying variance;
the DD leg fails 4/5.

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, multipliers, or the
   decision rule. PLAN.md was written before `compute_bearshort.py` ran.
2. Vectorised open-to-open screen only (no vol target, governor, dip
   sleeve, funding, SL/TP, or engine limit path); maker cost only
   (0.0002/unit turnover, each path's own chain). Short-leg membership
   fixed by base sign. Needs prospective validation; no threshold was
   fitted (fixed x1.25/x0.5 multipliers, fixed 1200-bar regime), so LOYO
   is N/A by construction, but all five years were available when the
   idea was scored.
3. The 2024-25 DD "not worse" is an exact tie (0.062817 both paths) passed
   under the 1e-12 tolerance, not an improvement.

## One-line verdict

NOT PROMISING: bear-regime short x1.25 raises total book P&L in only 3/5
years and worsens maxDD in 4/5 (2023 short loss deepened ~37%, DD +1.50pp)
— extra short size buys variance, not an edge.
