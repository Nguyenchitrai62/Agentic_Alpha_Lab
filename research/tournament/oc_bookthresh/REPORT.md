# oc_bookthresh REPORT: book signal-strength threshold (idea #48)

Book = `forward_v205.research_books_d2` (rebuilt exactly, cell-checked vs
oc_dvolshort); opens = v154 4h opens. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins = 54775 rows. BASE = raw book + v410 bear-long filter FIRST
(longs x0.5 when BTC 4h open < rolling-1200 mean on FULL opens history,
min 600, strict, NaN->False, open[T] inclusive). RULE (fixed in PLAN.md):
per (T, sym) in year k, with `q25_{k,s}` = walk-forward 25th percentile
of `|w_base|` over screened rows `U < A_k` per coin (zeros included),
`w_rule = 0` if `|w_base| < q25` else `w_base` (strict `<`; year 0 pool
empty -> rule inactive, base == rule). Screen = open-to-open 4h returns
with gate costs: net cell = `w*R1 - 0.0002*|w - w_prev|` per sym (first
prev = 0; each path its own prev). Equity per year reset to 1 and
compounded as `eq *= 1 + sum_s pnl`; maxDD = peak-to-trough; worst week
= min 42-bar compounded return. Full tables in `results.json`;
`panel.parquet` holds per-(T,sym) rows.

## Verdict

NOT PROMISING (as assigned): net book P&L higher (rule > base) in 1/5
years and maxDD not worse (rule <= base) in 3/5 years; LOYO sign
agreement 0/5. Year 0 ties on both legs by construction (empty training
pool, rule inactive).

## Per-year screen (net, portfolio-return units; costs included)

| year | q25 per coin (BNB/BTC/ETH/SOL/XRP) | share rows newly zeroed | book P&L base / rule | turnover cost base / rule | worst week base / rule | maxDD base / rule | P&L higher | DD not worse |
|---|---|---|---|---|---|---|---|---|
| 21-22 | undef (empty pool) | 0.000 | 0.291959 / 0.291959 | 0.008709 / 0.008709 | -0.055143 / -0.055143 | 0.086514 / 0.086514 | no (tie) | yes (tie) |
| 22-23 | 0.012853/0.008763/0.003738/0.007916/0.004441 | 0.114 | 0.252013 / 0.250472 | 0.011046 / 0.011043 | -0.046676 / -0.046831 | 0.071462 / 0.071634 | no | no |
| 23-24 | 0.013622/0.017274/0.013713/0.009146/0.007533 | 0.102 | 0.564138 / 0.567426 | 0.013325 / 0.013319 | -0.069232 / -0.069122 | 0.087278 / 0.087071 | yes | yes |
| 24-25 | 0.016160/0.026843/0.019837/0.014657/0.011112 | 0.173 | 0.539535 / 0.536856 | 0.014561 / 0.014552 | -0.045264 / -0.045400 | 0.062817 / 0.060669 | no | yes |
| 25-26 | 0.018554/0.033389/0.019305/0.014695/0.012093 | 0.207 | 0.413608 / 0.407092 | 0.012589 / 0.012616 | -0.074825 / -0.074935 | 0.085657 / 0.086396 | no | no |

Counts: P&L higher 1/5; DD not worse 3/5; LOYO (positive-effect sign
agreement, descriptive) 0/5. Full 5y path (context, compounded from
year-1 start): total P&L 2.061253 -> 2.053806 rule (-0.0074 over 5y);
maxDD 0.100471 -> 0.100296 rule; total turnover cost 0.060231 ->
0.060238 rule (no saving).

Read: zeroing the weakest ~10-21% of rows moves net P&L by only
-0.0065..+0.0033 per year and costs by ~1e-5 — the threshold fires on
weights too small to matter, while toggling in/out of zero adds its own
churn (2025 costs even rise). The single win (2023, +0.0033 with a small
DD trim) does not replicate in any other active year. Effect sizes are
noise against the ~0.01/year turnover scale.

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, thresholds, or the
   decision rule. PLAN.md was written before `compute_bookthresh.py`
   ran; the year-0 inactive rule and strict `>`/`<=` comparisons were
   fixed there.
2. Performance-only fix toward PLAN (verified, not outcome-driven): the
   first run crashed on a tz-naive vs tz-aware comparison in the
   training-mask construction (`grid.to_numpy()` vs tz-aware anchor);
   replaced with `np.asarray(grid < a0)`. No definition changed.
3. Vectorised open-to-open screen only (no vol target, governor, dip
   sleeve, funding, SL/TP, or engine limit path); maker cost only
   (0.0002/unit turnover, each path's own prev). Needs prospective
   validation; thresholds are strictly walk-forward, but all five
   years were available when the idea was scored.

## One-line verdict

NOT PROMISING: book signal-strength threshold (|w| < walk-forward per-coin
q25 -> 0, v410 bear filter first) raises net book P&L in only 1/5 years
with maxDD not worse in only 3/5 (LOYO 0/5; 5y net -0.0074, no cost saving).
