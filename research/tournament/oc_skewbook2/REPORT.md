# oc_skewbook2 REPORT: options skew as a BOOK long filter (idea #59)

Base = `forward_v205.research_books_d2` (rebuilt exactly, cell-checked vs
oc_dvolshort) with the v410 bear filter FIRST (longs x0.5 when BTC 4h open <
1200-bar mean, min_periods 600; bear share of bars 46.6%). Gated = base with
the fixed skew rule: `z = skew_z90` (BTC put-minus-call OTM IV z vs trailing
540 4h bars, min 432, current excluded — exactly as oc_optctx; as-of = last
options bar with END strictly before T, i.e. `[T-8h,T-4h)` for 4h T); when
`z >` walk-forward 80th percentile (pool = per-T `z` on the 4h opens grid in
`[2019-06-01, A_k)`, strictly previous data), all base LONG targets x0.75;
shorts/flats/NaN-`z` unchanged. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins = 54775 rows. Screen = open-to-open 4h returns with gate costs, exactly
as oc_dvolshort: net cell = `w*R1 - 0.0002*|w - w_prev|` per sym (first
prev = 0; gated path uses its own prev). Equity per year reset to 1 and
compounded as `eq *= 1 + sum_s pnl`; maxDD = peak-to-trough; worst week =
min 42-bar compounded return. Full tables in `results.json`; `panel.parquet`
holds per-(T,sym) rows. Coverage of `z` is 100% in all 5 anchor years
(options span 2019-01-01..2026-09-23 20:00 START; `q80` stable 0.61-0.67).

## Verdict

NOT PROMISING (as assigned): book P&L gated >= 97% of base in only 1/5 years
and maxDD not worse in 4/5 years (needs 4/5 on BOTH legs).

## Per-year screen (net, portfolio-return units; costs included)

| year | q80 | share longs gated (rows) | total book P&L base / gated (ratio) | P&L kept | worst week base / gated | maxDD base / gated | DD not worse |
|---|---|---|---|---|---|---|---|
| 21-22 | 0.671800 | 0.0993 (0.0462) | 0.291959 / 0.260119 (0.891) | no | -0.055143 / -0.053707 | 0.086514 / 0.086447 | yes |
| 22-23 | 0.640908 | 0.1126 (0.0547) | 0.252013 / 0.240225 (0.953) | no | -0.046676 / -0.046676 | 0.071462 / 0.072192 | no |
| 23-24 | 0.613963 | 0.1983 (0.1179) | 0.564138 / 0.543193 (0.963) | no | -0.069232 / -0.069263 | 0.087278 / 0.085775 | yes |
| 24-25 | 0.639215 | 0.1927 (0.1153) | 0.539535 / 0.513214 (0.951) | no | -0.045264 / -0.042694 | 0.062817 / 0.061976 | yes |
| 25-26 | 0.634573 | 0.0974 (0.0371) | 0.413608 / 0.403770 (0.976) | yes | -0.074825 / -0.067735 | 0.085657 / 0.077915 | yes |

Counts: P&L kept 1/5; DD not worse 4/5. Full 5y path (context, compounded
from year-1 start): total P&L 2.061253 -> 1.960521 gated (-0.101); maxDD
0.087278 -> 0.086447 gated (essentially flat).

Read: the filter fires on 10-20% of long rows but gives up 2-11% of book P&L
in every year (ratios 0.89-0.98, worst in 2021) while DD barely moves
(-0.0 to -0.15pp, except 2022 +0.07pp worse). High-skew bars are not adverse
for book longs here — scaling them down just scales down a profitable leg.
The only year clearing 97% (2025, 0.976) is also the only year with a visible
DD cut (-0.77pp), but one year cannot carry the 4/5 bar.

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, thresholds, or the decision
   rule. PLAN.md was written before `compute_skewbook2.py` ran; the script ran
   once with no outcome-driven edit.
2. Vectorised open-to-open screen only (no vol target, governor, dip sleeve,
   funding, SL/TP, or engine limit path); maker cost only
   (0.0002/unit turnover, gated path's own turnover). Base already includes
   the v410 bear filter, so the comparison isolates the skew filter.
3. Thresholds are strictly walk-forward (pool ends at each anchor); all five
   years were available when the idea was scored, so this is in-sample
   walk-forward style and needs prospective validation before any use.
4. `pnl_kept` uses the assigned 0.97x bar (all base year totals are positive,
   so no sign edge case is hit).

## One-line verdict

NOT PROMISING (as assigned): skew long-gate (x0.75 longs when BTC skew_z90 >
walk-forward q80) keeps >= 97% of bear-filtered book P&L in only 1/5 years
(DD not worse in 4/5) — it taxes a profitable long leg for no drawdown gain.
