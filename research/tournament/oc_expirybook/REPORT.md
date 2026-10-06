# oc_expirybook REPORT: options-expiry 48h gate on the BOOK (idea #62)

Book = `forward_v205.research_books_d2` (rebuilt exactly, cell-formula as
oc_dvolshort) + v410 bear-long filter FIRST (BASE = control); opens = v154
4h opens. Grid = 10955 bars (2021-09-24..2026-09-23 16:00 UTC; last bar
dropped, no forward open) x 5 coins = 54775 rows. Rule (fixed in PLAN.md):
68 monthly Deribit expiries (last Friday 08:00 UTC, 2021-01..2026-08); for
holding bars with `T` in `[E-48h, E)`, `w_r = 0.5 * w_b` (both sides), else
`w_r = w_b`. Screen = open-to-open 4h returns with oc_dvolshort costs: net
cell = `w*R1 - 0.0002*|w - w_prev|` per sym (first prev = 0; each path its
own prev). Equity per year reset to 1 and compounded as
`eq *= 1 + sum_s pnl`; maxDD = peak-to-trough; worst week = min 42-bar
compounded return. Full tables in `results.json`; `panel.parquet` holds
per-(T,sym) rows. Expiry share ~6.6% of bars (12 x 12 bars/year; 2021 = 134
bars, partial first window).

## Verdict

PROMISING (as assigned): book maxDD not worse (rule <= base) in 4/5 years
and total book P&L >= 98% of base in 4/5 years. The 2021-22 year fails on
BOTH legs (only year the expiry window was profitable, so halving hurt).

## Per-year screen (net, portfolio-return units; costs included)

| year | n exp bars (share) | window P&L base / rule | total book P&L base / rule (retention) | worst week base / rule | maxDD base / rule | DD not worse | ret >= 98% |
|---|---|---|---|---|---|---|---|
| 21-22 | 134 (0.0612) | 0.038928 / 0.019305 | 0.291959 / 0.272183 (0.932) | -0.055143 / -0.055143 | 0.086514 / 0.090484 | no | no |
| 22-23 | 144 (0.0658) | -0.030674 / -0.015739 | 0.252013 / 0.266552 (1.058) | -0.046676 / -0.046676 | 0.071462 / 0.070298 | yes | yes |
| 23-24 | 144 (0.0656) | -0.006496 / -0.003681 | 0.564138 / 0.566512 (1.004) | -0.069232 / -0.069232 | 0.087278 / 0.087278 | yes | yes |
| 24-25 | 144 (0.0658) | -0.011023 / -0.005971 | 0.539535 / 0.544192 (1.009) | -0.045264 / -0.045264 | 0.062817 / 0.059411 | yes | yes |
| 25-26 | 144 (0.0658) | -0.029805 / -0.015288 | 0.413608 / 0.427729 (1.034) | -0.074825 / -0.074825 | 0.085657 / 0.085657 | yes | yes |

Counts: DD not worse 4/5; retention >= 98% 4/5. Full 5y path (context,
compounded from year-1 start): maxDD 0.100471 -> 0.090484 gated;
total P&L 2.061253 -> 2.077167 gated (+0.0159 over 5y).

Read: the 48h pre-expiry window lost money on the BASE book in 4/5 years
(2022-2025 window P&L -0.006 to -0.031), so halving it mechanically adds
+0.003 to +0.015 total P&L in those years; 2021 is the mirror (window made
+0.039, halving cost -0.020 total and +0.40pp DD). DD changes are small
except 2021 (+0.40pp worse) and 2024 (-0.34pp better); 2023/2025 DD ties to
6dp. Worst week is bit-identical every year (the gate never touches the
year's worst 7-day stretch). Rule-path turnover costs run slightly higher
each year (+0.00007 to +0.00047) because halving/unhalving adds two extra
round-trips per expiry.

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, calendar, window, factor (0.5),
   costs, or the decision rule. PLAN.md was written before
   `compute_expirybook.py` ran.
2. Window P&L levels are small vs yearly totals (window is ~6.6% of bars);
   the 2022-2025 gains come from skipping small losses, not from a large
   edge; 2021 shows the sign can flip.
3. Vectorised open-to-open screen only (no vol target, governor, dip
   sleeve, funding, SL/TP, or engine limit path); maker cost only
   (0.0002/unit turnover, each path's own turnover). Needs prospective
   validation; in-sample over research data with a parameter-free rule
   (pure calendar + fixed 0.5, so no LOYO fit to leave out).
4. BASE here includes the v410 bear filter, so totals differ from the raw
   book in oc_expiry's descriptives; the comparison that matters
   (base vs rule) shares the filter.

## One-line verdict

PROMISING (as assigned): halving the book in the 48h before monthly Deribit expiry keeps DD not worse in 4/5 years with total P&L >= 98% of base in 4/5 (2021 fails both; 2022-2025 window losses halve into small gains) — small, parameter-free effect, needs prospective validation.
