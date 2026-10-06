# oc_bookholdcap REPORT: maximum holding time for book positions (idea #65)

Book = `forward_v205.research_books_d2` (rebuilt exactly, cell-checked vs
oc_dvolshort formula); opens = v154 4h opens. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins = 54775 rows. BASE = audited v410 bear filter FIRST (BTC-only longs
x0.5 when BTC open < rolling-1200 mean, min 600, open[T] inclusive). RULE =
per sym, `RULE[T_i,s] = 0` where the previous 42 capped weights for that sym
are all strictly > 0 or all strictly < 0 (one-bar forced flat, then normal
targets resume; zeros break runs; first 42 bars per sym never forced;
history continuous across year boundaries). Screen = open-to-open 4h returns
with assignment costs: net cell = `w*R1 - 0.0005*|w - w_prev|` per sym
(first prev = 0 globally; each path its own prev, so the forced close and
resume reopen pay turnover). Equity per year reset to 1 and compounded as
`eq *= 1 + sum_s pnl`; maxDD = peak-to-trough; worst week = min 42-bar
compounded return. Full tables in `results.json`; `panel.parquet` holds
per-(T,sym) rows. PLAN.md was written before `compute_bookholdcap.py` ran;
no post-hoc change to hypothesis, definitions, or decision rule.

## Verdict

NOT PROMISING (as assigned): book P&L RULE >= 97% of BASE in only 2/5 years
and maxDD not worse (RULE <= BASE) in only 2/5 years.

## Per-year screen (net, portfolio-return units; costs included)

| year | n_forced (share) | cost base / rule | book P&L base / rule (ratio) | worst week base / rule | maxDD base / rule | P&L>=97% | DD not worse |
|---|---|---|---|---|---|---|---|
| 21-22 | 129 (0.011781) | 0.021773 / 0.027676 | 0.278895 / 0.279084 (1.000677) | -0.055289 / -0.052303 | 0.092278 / 0.093777 | yes | no |
| 22-23 | 182 (0.016621) | 0.027615 / 0.041942 | 0.235444 / 0.221869 (0.942341) | -0.047268 / -0.043990 | 0.073721 / 0.077703 | no | no |
| 23-24 | 184 (0.016758) | 0.033313 / 0.049258 | 0.544150 / 0.500830 (0.920389) | -0.069471 / -0.069918 | 0.087902 / 0.086987 | no | yes |
| 24-25 | 165 (0.015068) | 0.036403 / 0.053054 | 0.517693 / 0.504960 (0.975404) | -0.045930 / -0.044941 | 0.065296 / 0.061198 | yes | yes |
| 25-26 | 177 (0.016172) | 0.031473 / 0.044379 | 0.394724 / 0.377061 (0.955253) | -0.075345 / -0.076132 | 0.087166 / 0.088797 | no | no |

Counts: P&L >= 97% 2/5; DD not worse 2/5. LOYO stability (descriptive, not
part of the verdict; H = 42 fixed): pnl 3/5, dd 3/5. Full 5y path (context,
compounded from year-1 start): maxDD 0.104644 -> 0.113519 capped;
total P&L 1.970907 -> 1.883804 capped (-0.0871 over 5y).

Read: the cap fires on 1.2-1.7% of cells per year and always raises turnover
(+0.006 to +0.017/year, +45% total cost) since every forced close must be
reopened. Only 2024 passes both legs (P&L 97.5%, DD 0.0653 -> 0.0612);
2021 keeps P&L (+0.0002) but DD worsens; 2023 is the only other DD win
(0.0879 -> 0.0870) yet pays the largest P&L haircut (92.0%). Worst-week
changes are negligible (<= 0.33pp, mixed sign).

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, thresholds, or the
   decision rule. PLAN.md was written before the compute ran.
2. Vectorised open-to-open screen only (no vol target, governor, dip
   sleeve, funding, SL/TP, or engine limit path); 0.0005/unit turnover with
   each path's own prev. BASE includes the v410 bear filter, so totals
   differ from raw-book screens by construction.
3. Forced-flat history is on capped (held) weights with cross-year carry;
   counting BASE-sign streaks instead would re-trigger immediately after a
   forced flat and was pre-registered against.
4. In-sample walk-forward style screen (rule is a fixed constant, but all
   five years were available when scored); needs prospective validation.

## One-line verdict

NOT PROMISING: 42-bar same-sign hold-cap (one-bar flat, then resume) keeps >= 97% of book P&L in only 2/5 years with DD not worse in only 2/5 (extra turnover every year; 5y P&L -0.087, 5y DD worse) — close the direction.
