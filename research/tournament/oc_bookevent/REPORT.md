# oc_bookevent REPORT: book exposure around scheduled US macro events (idea #51)

Book = `forward_v205.research_books_d2` (rebuilt exactly, same code as
oc_dvolshort); opens = v154 4h opens. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins = 54775 rows. BASE = audited v410 bear filter FIRST (longs x0.5
where BTC 4h open < its 1200-bar mean, rolling 1200/min 600 on full
history from 2017). RULE = BASE with ALL targets x0.5 on RULEBARs (the 4h
bar containing a scheduled FOMC/CPI release instant from the oc_eventblk
calendar — read-only, 54 FOMC + 82 CPI before cutoff — AND the bar before
it; instant-in-bar predicate, schedule pre-published so causal at T).
Screen = open-to-open 4h returns with 0.02%/unit turnover (each path with
its OWN prev, first prev = 0; no vol scale). Equity per year reset to 1
and compounded as `eq *= 1 + sum_s pnl`; maxDD = peak-to-trough; worst
week = min 42-bar compounded return. Full tables in `results.json`;
`panel.parquet` holds per-(T,sym) rows. No 1m data; one process, RAM < 1 GB.

## Verdict

NOT PROMISING (as assigned): book maxDD not worse in 3/5 years and total
book P&L >= 97% of base in 3/5 years (needs 4/5 on both legs). Event bars
are only ~1.8% of bars; halving them trims P&L in 4/5 years (retention
0.91-0.99, above base only in 2022 where event bars lost money) and the
DD effect is mixed (better in 2022/2024/2025, worse in 2021/2023).

## Per-year screen (net, portfolio-return units; costs included)

| year | n_bars | event / rule share | bear share | event-bar P&L base / rule | total book P&L base / rule | retention | worst week base / rule | maxDD base / rule | DD ok | P&L ok |
|---|---|---|---|---|---|---|---|---|---|---|
| 21-22 | 2190 | 0.0091 / 0.0183 | 0.7635 | 0.050633 / 0.024957 | 0.291959 / 0.265977 | 0.9110 | -0.055143 / -0.055143 | 0.086514 / 0.089171 | no | no |
| 22-23 | 2190 | 0.0091 / 0.0183 | 0.4073 | -0.029230 / -0.015233 | 0.252013 / 0.265428 | 1.0532 | -0.046676 / -0.046676 | 0.071462 / 0.068400 | yes | yes |
| 23-24 | 2196 | 0.0091 / 0.0178 | 0.2172 | 0.028072 / 0.013327 | 0.564138 / 0.548743 | 0.9727 | -0.069232 / -0.071191 | 0.087278 / 0.089199 | no | yes |
| 24-25 | 2190 | 0.0091 / 0.0183 | 0.1384 | 0.049737 / 0.023964 | 0.539535 / 0.512960 | 0.9507 | -0.045264 / -0.045264 | 0.062817 / 0.061341 | yes | no |
| 25-26 | 2189 | 0.0096 / 0.0187 | 0.8036 | 0.007036 / 0.002921 | 0.413608 / 0.408964 | 0.9888 | -0.074825 / -0.074825 | 0.085657 / 0.085023 | yes | yes |

Counts: DD not worse 3/5; retention >= 97% 3/5. Full 5y path (context,
compounded from year-1 start): total P&L 2.061253 -> 2.002072 gated
(-0.059 over 5y); maxDD 0.100471 -> 0.096970 gated.

Read: event-bar P&L is positive in 4/5 years (only 2022 negative), so
halving event exposure gives up profit more often than it avoids loss —
the opposite of the hypothesised event-risk premium. The one winning
year on both legs (2022) is the year event bars lost money; elsewhere
the rule trades lower P&L for flat-or-worse DD (2021/2023 DD worse,
2024 DD better but retention 0.95 fails). Worst week is unchanged in 4/5
years (the 7-day troughs sit outside event bars) and slightly worse in
2023. LOYO majority-agreement (descriptive, no fitted parameter): DD 3/5,
retention 3/5 — no stability either.

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, calendar, multipliers,
   or the decision rule. PLAN.md was written before
   `compute_bookevent.py` ran; the script ran once, unmodified after.
2. Calendar reused in place from oc_eventblk (never copied/edited); all
   136 instants (54 FOMC + 82 CPI) are before CUTOFF by assertion.
3. Vectorised open-to-open screen only (no vol target, governor, funding,
   SL/TP, sleeve sizing, or engine limit path); maker cost only
   (0.0002/unit turnover, each path's own turnover). All five years were
   available when the rule was frozen (assignment); no hidden year remains
   — prospective validation still required before any adoption (none
   proposed: the verdict is negative).

## One-line verdict

NOT PROMISING: halving book targets on macro-event bars (and the bar
before) leaves maxDD not worse in only 3/5 years with >= 97% P&L
retention in only 3/5 (event bars earned positive P&L in 4/5 years) —
no drawdown relief, close the direction.
