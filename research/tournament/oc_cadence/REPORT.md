# oc_cadence REPORT: slower book cadence (idea #47)

Book = `forward_v205.research_books_d2` (rebuilt exactly, cell-checked vs
oc_dvolshort formula); opens = v154 4h opens. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins. BASE = raw book with the v410 bear-long filter FIRST (longs x0.5
when BTC 4h open < 1200-bar mean on FULL history, strict, NaN -> False;
shorts/flat unchanged; share bear 0.14-0.80 by year). 8H = BASE with 8h
cadence (ordinal `i` in the sorted grid, `i=0` = 2021-09-24 00:00 UTC;
only even `i` may CHANGE a coin's target, odd rows hold the previous
target per coin); 12H sensitivity = only `i % 3 == 0` may change.
Screen = open-to-open 4h returns with 0.05% per unit turnover, each path
its own prev (first prev = 0): net cell = `W*R1 - 0.0005*|W - W_prev|`.
Equity per year reset to 1, `eq *= 1 + sum_s net`; maxDD peak-to-trough;
worst week = min 42-bar return. Full tables in `results.json`.
No post-hoc change to PLAN.md definitions or the decision rule.

## Verdict

NOT PROMISING (as assigned): net 8h > net base in 2/5 years and maxDD 8h
<= maxDD base in 1/5 years (needs >= 4/5 on both).

## Per-year screen, BASE vs 8H (net; costs included)

| year | bear share | gross base / 8h | turnover base / 8h | cost base / 8h | net base / 8h | worst week base / 8h | maxDD base / 8h | P&L higher | DD not worse |
|---|---|---|---|---|---|---|---|---|---|
| 21-22 | 0.763470 | 0.300669 / 0.327707 | 43.546746 / 40.250784 | 0.021773 / 0.020125 | 0.278895 / 0.307582 | -0.055289 / -0.055939 | 0.092278 / 0.080162 | yes | yes |
| 22-23 | 0.407306 | 0.263059 / 0.262129 | 55.230048 / 50.951540 | 0.027615 / 0.025476 | 0.235444 / 0.236653 | -0.047268 / -0.047485 | 0.073721 / 0.075618 | yes | no |
| 23-24 | 0.217213 | 0.577463 / 0.542288 | 66.625366 / 60.883390 | 0.033313 / 0.030442 | 0.544150 / 0.511846 | -0.069471 / -0.070073 | 0.087902 / 0.097175 | no | no |
| 24-25 | 0.138356 | 0.554096 / 0.514911 | 72.805032 / 67.626921 | 0.036403 / 0.033813 | 0.517693 / 0.481098 | -0.045930 / -0.047581 | 0.065296 / 0.074019 | no | no |
| 25-26 | 0.803563 | 0.426197 / 0.418999 | 62.945961 / 58.449786 | 0.031473 / 0.029225 | 0.394724 / 0.389774 | -0.075345 / -0.074509 | 0.087166 / 0.087415 | no | no |

Counts (8h vs base): P&L higher 2/5; DD not worse 1/5. LOYO on the net
difference (descriptive, not for selection): 0/5. Full 5y path (context,
compounded from year-1 start): net 1.970907 -> 1.926953 (8h); maxDD
0.104644 -> 0.114915 (8h). Totals: turnover 301.15 -> 278.16 (8h, -7.6%);
cost 0.150577 -> 0.139081 (saves 0.0115 over 5y).

## 12h sensitivity (reported only, NOT for selection)

| year | gross 12h | turnover 12h | cost 12h | net 12h | net base | worst week 12h | maxDD 12h | P&L higher | DD not worse |
|---|---|---|---|---|---|---|---|---|---|
| 21-22 | 0.327806 | 37.183254 | 0.018592 | 0.309214 | 0.278895 | -0.056207 | 0.075672 | yes | yes |
| 22-23 | 0.304536 | 47.156856 | 0.023578 | 0.280957 | 0.235444 | -0.045122 | 0.068184 | yes | yes |
| 23-24 | 0.531761 | 56.146603 | 0.028073 | 0.503688 | 0.544150 | -0.069560 | 0.096108 | no | no |
| 24-25 | 0.528858 | 62.002847 | 0.031001 | 0.497857 | 0.517693 | -0.044977 | 0.063471 | no | yes |
| 25-26 | 0.414209 | 53.820468 | 0.026910 | 0.387299 | 0.394724 | -0.072301 | 0.083467 | no | yes |

12h vs base: P&L higher 2/5; DD not worse 3/5. Full 5y: net 1.979015
(+0.008 over base); maxDD 0.103196 (marginally better). No monotonic
cadence edge: the cost saving (~0.011 for 8h, ~0.022 for 12h over 5y) is
an order of magnitude smaller than the gross-P&L moves from staleness
(e.g. 2023 gross -0.035 for 8h), so turnover is not the binding cost.

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, cadence masks,
   thresholds, or the decision rule. PLAN.md was written before
   `compute_cadence.py` ran.
2. Vectorised open-to-open screen only (no vol target, governor, dip
   sleeve, funding, SL/TP, or engine limit path); 0.0005/unit turnover
   with each path's own prev. Short/long membership for attribution is
   the BASE sign; cadence never flips a sign by itself, it only delays.
3. Parity is ordinal in the scored grid (`i=0` = 2021-09-24 00:00 UTC);
   the grid is gap-free 4h so this equals wall-clock 8h/12h alignment up
   to the fixed offset. Row 0 updates on all paths.
4. Bear filter is the oc_bullbook full-history MA1200 (causal,
   `open[T]`-inclusive), not v410's truncated-books-index rolling; early
   2021 flags therefore use pre-2021 opens (all pre-anchor, causal).
5. All five years were available when scored (assignment override);
   finding needs prospective validation; in-sample walk-forward style
   with no fitted parameter (masks are fixed).

## One-line verdict

NOT PROMISING: 8h book cadence beats net base P&L in only 2/5 years with DD not worse in only 1/5 (cost saving dwarfed by stale-gross drag; 12h sensitivity 2/5 and 3/5) — close the direction.
