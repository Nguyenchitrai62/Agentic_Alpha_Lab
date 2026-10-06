# oc_fomcbook REPORT: scheduled FOMC statements and the BOOK (idea #66)

Book = `forward_v205.research_books_d2` (rebuilt exactly, same code as
oc_dvolshort); opens = v154 4h opens. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins = 54775 rows. BASE = audited v410 bear filter FIRST (longs x0.5
where BTC 4h open < its 1200-bar mean, rolling 1200/min 600 on full
history from 2017). RULE = BASE with ALL targets (both sides) x0.5 on
RULEBARs: holding bars starting in [R-24h, R+4h] around each of the 56
hard-coded scheduled FOMC statement instants 2020-2026 (federalreserve.gov
fomccalendars.htm; 14:00 ET = 18:00 UTC EDT / 19:00 UTC EST; unscheduled
excluded; pre-published schedule so causal at T). 40 statements fall in
the scored span x 7 grid bars each = 280/10955 bars (2.56%).
Screen = open-to-open 4h returns with 0.05%/unit turnover (each path with
its OWN prev, first prev = 0; no vol scale). Equity per year reset to 1
and compounded as `eq *= 1 + sum_s pnl`; maxDD = peak-to-trough; worst
week = min 42-bar compounded return. Full tables in `results.json`;
`panel.parquet` holds per-(T,sym) rows. No 1m data; one process, RAM < 1 GB.

## Verdict

NOT PROMISING (as assigned): book maxDD not worse in 4/5 years but total
book P&L >= 98% of base in only 2/5 years (needs 4/5 on both legs).
Event-window bars earned positive P&L in 3/5 years, so halving them gives
up profit more often than it avoids loss; retention is 0.95-0.96 in the
three failing years.

## Per-year screen (net, portfolio-return units; costs included)

| year | n_bars | rule share | bear share | window P&L base / rule | total book P&L base / rule | retention | worst week base / rule | maxDD base / rule | DD ok | P&L ok |
|---|---|---|---|---|---|---|---|---|---|---|
| 21-22 | 2190 | 0.0256 | 0.7635 | 0.026009 / 0.012688 | 0.278895 / 0.265356 | 0.9515 | -0.055289 / -0.055289 | 0.092278 / 0.095238 | no | no |
| 22-23 | 2190 | 0.0256 | 0.4073 | -0.022429 / -0.011832 | 0.235444 / 0.245506 | 1.0427 | -0.047268 / -0.047268 | 0.073721 / 0.072843 | yes | yes |
| 23-24 | 2196 | 0.0255 | 0.2172 | 0.042504 / 0.020457 | 0.544150 / 0.521472 | 0.9583 | -0.069471 / -0.069471 | 0.087902 / 0.087902 | yes | no |
| 24-25 | 2190 | 0.0256 | 0.1384 | -0.005752 / -0.003819 | 0.517693 / 0.518709 | 1.0020 | -0.045930 / -0.045930 | 0.065296 / 0.058526 | yes | yes |
| 25-26 | 2189 | 0.0256 | 0.8036 | 0.032633 / 0.015724 | 0.394724 / 0.377244 | 0.9557 | -0.075345 / -0.075345 | 0.087166 / 0.087166 | yes | no |

Counts: DD not worse 4/5; retention >= 98% 2/5. Full 5y path (context,
compounded from year-1 start): total P&L 1.970907 -> 1.928287 gated
(-0.0426 over 5y); maxDD 0.104644 -> 0.103597 gated.

Read: the DD leg passes (strictly better in 2022/2024, equal in
2023/2025, worse only in 2021), but the P&L leg fails decisively — only
2022 (window lost money, halving helped both legs) and 2024 (window near
flat, small DD win) retain >= 98%. In 2021/2023/2025 the window earned
positive P&L (+0.026/+0.043/+0.033), so halving it costs 4-5% of yearly
book P&L each time. Worst week is identical in all 5 years (the 7-day
troughs sit outside FOMC windows), so no crash-protection story either.
LOYO majority-agreement (descriptive, no fitted parameter): DD 4/5,
retention 0/5 — the retention failure is stable, not a one-year fluke.

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, calendar, multipliers,
   or the decision rule. PLAN.md was written before
   `compute_fomcbook.py` ran.
2. One pre-run bug fix (before any outcome was computed, script had never
   run to completion): removed an over-strict assert requiring all 56
   hard-coded instants to precede CUTOFF+24h (the 2026-10-28/12-09
   instants are inert — their windows hold no grid bar — and are kept so
   the calendar stays complete).
3. Vectorised open-to-open screen only (no vol target, governor, funding,
   SL/TP, sleeve sizing, or engine limit path); cost 0.0005/unit turnover
   per the assignment (each path's own turnover). All five years were
   available when the rule was frozen (assignment); no hidden year remains
   — prospective validation still required before any adoption (none
   proposed: the verdict is negative).
4. BASE maxDD/P&L levels differ from oc_bookevent's because that study
   used 0.0002 turnover while this assignment specifies 0.0005; the
   comparison BASE-vs-RULE inside this study is like-for-like.

## One-line verdict

NOT PROMISING: halving book targets (both sides) on FOMC windows
([R-24h, R+4h], 2.6% of bars) leaves maxDD not worse in 4/5 years but
retains >= 98% of book P&L in only 2/5 (window P&L positive in 3/5 years)
— no drawdown relief worth its P&L cost, close the direction.
