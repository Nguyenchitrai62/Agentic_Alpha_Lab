# oc_bookfunding REPORT: funding-crowding tilt for BOOK longs (idea #56)

Book = `forward_v205.research_books_d2` (rebuilt exactly, cell-checked vs
oc_dvolshort); opens = v154 4h opens. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins = 54775 rows. BASE = v410 BTC-only bear filter FIRST (longs x0.5
when BTC 4h open < rolling-1200 mean, min 600, open[T] inclusive).
Rule (fixed in PLAN.md): per (T, sym), `F7` = mean settled funding over
`[T-7d, T)` strictly before T (>= 14 settlements else NaN, millisecond-exact);
`q80_k[s]` = walk-forward 80th percentile of `F7[.,s]` over
`[2021-06-30, A_k)` (per coin, strictly pre-anchor); if `F7 > q80` then
`w_rule = 0.75 * w_base` on base longs, else identical (shorts/flats/NaN
unchanged; long-leg membership fixed by `w_base > 0`). Screen = open-to-open
4h returns with gate costs: net cell = `w*R1 - 0.0002*|w - w_prev|` per sym
(first prev = 0; each path own prev). Equity per year reset to 1, compounded
as `eq *= 1 + sum_s pnl`; maxDD = peak-to-trough; worst week = min 42-bar
compounded return. Full tables in `results.json`; `panel.parquet` holds
per-(T,sym) rows. Funding history starts 2020 (full 7d window by FEAT_START);
funding data ends 2026-08-31, so 2025 coverage is 94.4% (rest NaN, never tilted).

## Verdict

NOT PROMISING (as assigned): total book P&L >= 97% of base in only 3/5 years
and maxDD not worse in only 3/5 years (need >= 4/5 on both).

## Per-year screen (net, portfolio-return units; costs included)

| year | tilt-on share (base longs) | long P&L base / rule | total book P&L base / rule | worst week base / rule | maxDD base / rule | DD not worse | P&L >= 97% |
|---|---|---|---|---|---|---|---|
| 21-22 | 0.108 | 0.153468 / 0.144806 | 0.291959 / 0.283298 | -0.055143 / -0.052001 | 0.086514 / 0.081513 | yes | yes |
| 22-23 | 0.083 | 0.228949 / 0.227459 | 0.252013 / 0.250526 | -0.046676 / -0.044287 | 0.071462 / 0.070791 | yes | yes |
| 23-24 | 0.633 | 0.607182 / 0.519862 | 0.564138 / 0.476828 | -0.069232 / -0.069232 | 0.087278 / 0.087587 | no | no |
| 24-25 | 0.237 | 0.494588 / 0.422050 | 0.539535 / 0.466996 | -0.045264 / -0.042064 | 0.062817 / 0.061242 | yes | no |
| 25-26 | 0.124 | 0.235489 / 0.224796 | 0.413608 / 0.402919 | -0.074825 / -0.074825 | 0.085657 / 0.085741 | no | yes |

Counts: P&L >= 97% 3/5; DD not worse 3/5. Full 5y path (context, compounded
from year-1 start): maxDD 0.100471 -> 0.099608 rule; total P&L
2.061253 -> 1.880567 rule (-8.8%). Coverage F7 = 100% in 2021-2024, 94.4%
in 2025 (funding feed ends 2026-08-31). q80 per coin in `results.json`
(e.g. 2021 BTC 1.43e-4 … XRP 3.48e-4; 2023-2025 cluster near 1e-4 as settled
funding compresses to the 0.0001 cap).

Read: the tilt trims longs exactly when funding runs hot, but hot funding
coincides with the strongest book-long years (2023 tilt-on 63% of base longs,
long P&L -14%, total -15.5%; 2024 tilt-on 24%, total -13.4%), so it taxes
return without a compensating DD cut (DD improves only 0.03-0.50pp where it
improves; 2023/2025 DD slightly worse by ~0.0001-0.0003). 2025 tilt fires only
on BNB (other coins' F7 never clears q80 after the feed flattens), hence the
small effect there. No post-hoc change to hypothesis, definitions, thresholds,
or the decision rule.

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, thresholds, or the decision
   rule. PLAN.md was written before `compute_bookfunding.py` ran.
2. Vectorised open-to-open screen only (no vol target, governor, dip sleeve,
   funding deduction, SL/TP, or engine limit path); maker cost only
   (0.0002/unit turnover, each path's own turnover). Long-leg membership fixed
   by `w_base > 0`. Needs prospective validation; thresholds strictly
   pre-anchor, but all five years were available when the idea was scored.
3. 2023 is the clear failure (both legs); 2024 fails P&L while passing DD;
   2025 fails DD (by 8.4e-5) while passing P&L. The tilt is a return drag
   (-0.18 over 5y) for at best a marginal full-path DD improvement (-0.0009).

## One-line verdict

NOT PROMISING: funding-crowding long tilt (x0.75 longs when 7d funding > walk-forward p80) keeps >= 97% of book P&L in only 3/5 years with DD not worse in only 3/5 (2023 fails both; 5y total -8.8%) — crowded funding marks strong longs, not squeezes to fade.
