# oc_breadthbook REPORT: breadth brake on BOOK LONGS (idea #63)

Book = `forward_v205.research_books_d2` (rebuilt exactly, cell-checked vs
oc_dvolshort's formula); opens = v154 4h opens. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins = 54775 rows. BASE = v410 BTC-only bear filter FIRST (longs x0.5 when
BTC 4h open < rolling-1200 mean, min 600, open[T] inclusive; base total
2.061253 matches oc_bearshort/oc_bookcoinbrake's v410 base exactly).
RULE (fixed in PLAN.md): per 4h bar T, `e0` = T floored to midnight, daily
close `C0` = hourly_ext close of bar `[e0-1h, e0]` (end <= T, strictly
causal), 200-day mean `M` = mean of the 200 prior daily closes (current
excluded, all 200 required); `above` = C0 > M per coin; `breadth` = share
of the 5 majors above (NaN unless all 5 valid); `breadth_on` =
(breadth == 1.0); while ON, book LONG targets x0.75 (shorts/flats
bit-identical; bear+breadth longs = 0.375x raw). Screen = open-to-open 4h
returns with gate costs: net cell = `w*R1 - 0.0002*|w - w_prev|` per sym
(first prev = 0; each path its own prev). Equity per year reset to 1 and
compounded as `eq *= 1 + sum_s pnl`; maxDD = peak-to-trough; worst week =
min 42-bar compounded return. Full tables in `results.json`;
`panel.parquet` holds per-(T,sym) rows. Breadth coverage is 100% all years;
on-share overall 23.2% (vs 23.3% for oc_grindsignal's hourly breadth --
independent implementation, same frequency).

## Verdict

NOT PROMISING (as assigned): book maxDD not worse in 5/5 years BUT book
P&L >= 95% of base in only 2/5 years (2021 91.3%, 2024 86.4%, 2025 94.2%
fail; 2023 passes at 95.8%).

## Per-year screen (net, portfolio-return units; costs included)

| year | breadth on-share | book P&L base / rule | worst week base / rule | maxDD base / rule | DD not worse | P&L >=95% |
|---|---|---|---|---|---|---|
| 21-22 | 0.169863 | 0.291959 / 0.266482 | -0.055143 / -0.051956 | 0.086514 / 0.072141 | yes | no (91.3%) |
| 22-23 | 0.150685 | 0.252013 / 0.260521 | -0.046676 / -0.046676 | 0.071462 / 0.071462 | yes (equal) | yes (103.4%) |
| 23-24 | 0.270492 | 0.564138 / 0.540358 | -0.069232 / -0.069232 | 0.087278 / 0.087278 | yes (equal) | yes (95.8%) |
| 24-25 | 0.421918 | 0.539535 / 0.466142 | -0.045264 / -0.045264 | 0.062817 / 0.052935 | yes | no (86.4%) |
| 25-26 | 0.144815 | 0.413608 / 0.389614 | -0.074825 / -0.069696 | 0.085657 / 0.079999 | yes | no (94.2%) |

Counts: DD not worse 5/5; P&L >=95% 2/5. Full 5y path (context,
compounded from year-1 start): maxDD 0.100471 -> 0.100471 (equal); total
P&L 2.061253 -> 1.923118 (-0.1381, -6.7%). Breadth coverage 100% every
year; bear share 0.76 / 0.41 / 0.22 / 0.14 / 0.80.

Read: the brake trims DD where it bites (2021 -1.44pp, 2024 -0.99pp,
2025 -0.57pp; 2022/2023 DD equal to 6 decimals) but gives up P&L in 4/5
years -- only 2022 gains (+0.0085). The cost concentrates in the
highest on-share year (2024: on 42% of bars, P&L -13.6%): extended tops
kept rising, so fading longs bled. 2025 fails the 95% bar at 94.2%
despite a DD win. Worst-week changes are nil except 2021/2025.

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, thresholds, or the
   decision rule. PLAN.md was written before `compute_breadthbook.py` ran.
2. Daily vs hourly breadth: the assignment fixes daily closes + 200-day
   mean; oc_grindsignal used hourly closes + 4800-bar mean. Both give
   ~23% on-share and 100% coverage, so the screened regime matches the
   hypothesis regime in frequency, not tick-for-tick.
3. Vectorised open-to-open screen only (no vol target, governor, dip
   sleeve, funding, SL/TP, or engine limit path); maker cost only
   (0.0002/unit turnover, each path's own turnover). Needs prospective
   validation; in-sample walk-forward style (fixed 1.0 threshold, no
   fitted parameter, but all five years were available when scored).

## One-line verdict

NOT PROMISING: breadth brake (longs x0.75 when all 5 majors above their
200d mean) never worsens book maxDD (5/5) but keeps >=95% of base P&L in
only 2/5 years (2024 bleeds -13.6% while on 42% of bars) -- DD trim at a
return cost, not a gate.
