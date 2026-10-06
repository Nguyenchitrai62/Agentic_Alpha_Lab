# oc_bookcoinbrake REPORT — per-coin book drawdown brake (idea #45)

Book = `forward_v205.research_books_d2` (rebuilt exactly, cell-checked vs
oc_dvolshort); opens = v154 4h opens. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins = 54775 rows. BASE = v410 BTC-only bear filter FIRST (longs x0.5 when
BTC 4h open < 1200-bar mean, rolling 1200 min 600, open[T] inclusive).
RULE = latching per-coin brake on BASE nets: `S30[T,s]` = trailing-30d sum
of BASE net cells over rows `< T`; `M[T,s]` = median(|S30|) over rows in
`[T-365d, T)` (min 200 values else NaN/off); enter when `S30 < -2*M`, exit
when `S30 > 0`; while ON that coin's LONG target x0.5, shorts/flats
bit-identical. Screen = open-to-open 4h returns with gate costs, exactly as
oc_dvolshort: net cell = `w*R1 - 0.0002*|w - w_prev|` per sym (first prev =
0; each path its own prev chain). No recursion (trigger uses BASE nets
only). Equity per year reset to 1 and compounded as `eq *= 1 + sum_s pnl`;
maxDD = peak-to-trough; worst week = min 42-bar compounded return. Full
tables in `results.json`; `panel.parquet` holds per-(T,sym) rows. PLAN.md
was written before `compute_bookcoinbrake.py` ran; no post-hoc changes.

## Verdict

PROMISING (as assigned): book maxDD not worse in 4/5 years AND book P&L >=
95% of base in 4/5 years (fails: DD in 2024-25, P&L in 2025-26).

## Per-year screen (net, portfolio-return units; costs included)

| year | bear share | brake-on share BNB/BTC/ETH/SOL/XRP | book P&L base / rule | worst week base / rule | maxDD base / rule | DD ok | P&L ok |
|---|---|---|---|---|---|---|---|
| 21-22 | 0.763 | 0.000/0.137/0.000/0.042/0.089 | 0.291959 / 0.295561 | -0.055143 / -0.055143 | 0.086514 / 0.084166 | yes | yes |
| 22-23 | 0.407 | 0.195/0.273/0.237/0.132/0.150 | 0.252013 / 0.245017 | -0.046676 / -0.046458 | 0.071462 / 0.064194 | yes | yes |
| 23-24 | 0.217 | 0.131/0.045/0.089/0.116/0.136 | 0.564138 / 0.546050 | -0.069232 / -0.069232 | 0.087278 / 0.087278 | yes | yes |
| 24-25 | 0.138 | 0.236/0.129/0.048/0.181/0.095 | 0.539535 / 0.523878 | -0.045264 / -0.043536 | 0.062817 / 0.067278 | no | yes |
| 25-26 | 0.804 | 0.000/0.142/0.061/0.238/0.049 | 0.413608 / 0.389160 | -0.074825 / -0.074906 | 0.085657 / 0.084619 | yes | no |

Counts: DD not worse 4/5; P&L >= 95% 4/5. Full 5y path (context,
compounded from year-1 start): maxDD 0.100471 -> 0.089101 rule; total P&L
2.061253 -> 1.999665 rule (-3.0%).

## Gate window 2023-04-17..2023-06-15 (354 bars, net sums)

book loss base -0.050424 vs rule -0.035405 (delta +0.015019); long-leg loss
base -0.075081 vs rule -0.060063. The brake cuts ~30% of the window book
loss (~20% of the long-leg loss) while shorts are untouched.

Read: the brake trims DD in 2021 (-0.23pp), 2022 (-0.73pp) and 2025
(-0.10pp), is neutral in 2023 (equal DD), and worsens DD in 2024 (+0.45pp
despite a better worst week). P&L cost is nil-to-small except 2025 (-5.9%,
just below the 95% line; 0.95*0.413608 = 0.392928 vs 0.389160). Brake fires
13-27% of bars on bleeding coins in 2022-2024, near-zero on BNB in the
bookends (BNB brake 0.000 in 21-22 and 25-26). Worst-week changes are
negligible.

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, thresholds, or the
   decision rule. One code fix after the first run (year-membership
   `.to_numpy()` on an already-numpy mask) with no effect on economics.
2. Vectorised open-to-open screen only (no vol target, governor, dip
   sleeve, funding, SL/TP, or engine limit path); maker cost only
   (0.0002/unit turnover, each path's own chain). Needs prospective
   validation; thresholds are strictly walk-forward per (T,s) but all five
   years were available when the idea was scored.
3. `M` needs >= 200 trailing S30 values, so the brake is mechanically off
   in the first ~33 days of the sample; year-1 brake shares are
   correspondingly light.

## One-line verdict

PROMISING (as assigned): per-coin DD brake (S30 < -2x trailing median-abs,
exit on S30 > 0, longs x0.5) leaves DD not worse in 4/5 years and P&L >=
95% in 4/5, cutting the 2023-04-17..06-15 book loss by ~30% (-0.0504 to
-0.0354); fails DD in 2024-25 and P&L in 2025-26.
