# oc_coinbear REPORT: per-coin bear-book filter (idea #44)

Book = `forward_v205.research_books_d2` (rebuilt exactly, cell-checked vs
oc_bookic); opens = v154 4h opens. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins = 54775 rows. BASE = audited v410 BTC-only filter (longs x0.5 when
BTC 4h open < its 1200-bar mean, rolling(1200, min 600) on full history,
open[T] inclusive, NaN -> False). RULE = per-coin extension (coin long
x0.5 when BTC bear OR the coin's own open < its own 1200-bar mean;
shorts/flat unchanged; BTC rows identical in both). Screen = open-to-open
4h returns with gate costs exactly as oc_dvolshort: net cell =
`w*R1 - 0.0002*|w - w_prev|` per sym (first prev = 0; each path its own
prev). Long-leg sums use ORIGINAL raw `w > 0` so BASE vs RULE compare
identical rows. Equity per year reset to 1 and compounded as
`eq *= 1 + sum_s pnl`; maxDD = peak-to-trough; worst week = min 42-bar
compounded return. Full tables in `results.json`; `panel.parquet` holds
per-(T,sym) rows. PLAN.md was written before `compute_coinbear.py` ran.

## Verdict

NOT PROMISING (as assigned): book maxDD not worse in 3/5 years (needs
>= 4/5) and book P&L >= 95% of base in 3/5 years (needs >= 4/5).

## Per-year screen (net, portfolio-return units; costs included)

| year | btc bear share | newly halved (all / of longs) | book P&L base / rule | long P&L base / rule | worst week base / rule | maxDD base / rule | DD not worse | P&L >= 95% |
|---|---|---|---|---|---|---|---|---|
| 21-22 | 0.763470 | 0.008037 / 0.017262 | 0.291959 / 0.289877 | 0.153468 / 0.151382 | -0.055143 / -0.055143 | 0.086514 / 0.083855 | yes | yes |
| 22-23 | 0.407306 | 0.035525 / 0.073134 | 0.252013 / 0.242178 | 0.228949 / 0.219105 | -0.046676 / -0.042164 | 0.071462 / 0.065865 | yes | yes |
| 23-24 | 0.217213 | 0.026412 / 0.044397 | 0.564138 / 0.530448 | 0.607182 / 0.573480 | -0.069232 / -0.069232 | 0.087278 / 0.087278 | yes | no |
| 24-25 | 0.138356 | 0.071507 / 0.119560 | 0.539535 / 0.504542 | 0.494588 / 0.459567 | -0.045264 / -0.040408 | 0.062817 / 0.063452 | no | no |
| 25-26 | 0.803563 | 0.003655 / 0.009592 | 0.413608 / 0.411631 | 0.235489 / 0.233513 | -0.074825 / -0.072560 | 0.085657 / 0.085666 | no | yes |

Counts: DD not worse 3/5; P&L >= 95% 3/5. Full 5y path (context,
compounded from year-1 start): maxDD 0.100471 -> 0.096342 rule; total P&L
2.061253 -> 1.978676 rule (-0.0826 over 5y, rule lower every year).
LOYO descriptive (fixed rule, no fit): pnl sign-hold 5/5 (rule lower in
all 5 years); DD-hold 2/5.

## Gate window 2023-04-17..2023-06-15 (354 bars; linear net sums)

| | book BASE | book RULE | delta (rule - base) |
|---|---|---|---|
| all legs | -0.050424 | -0.050610 | -0.000186 |
| long leg | -0.075081 | -0.075268 | -0.000187 |

Read: the per-coin extension does not bind in the gate window — the
window loss is unchanged to < 0.02pp. It trims DD only in 2021-2022
(-0.27pp, -0.56pp) where the extra haircut is small (0.8-3.6% of rows),
is exactly flat on DD in 2023 while costing 6% of book P&L, and is
slightly worse on DD in 2024-2025. The extra haircut bites hardest in
2024 (7.2% of rows, 12.0% of longs; book P&L -6.5%) — a bull year where
own-bear flags catch coin pullbacks inside a BTC bull tape.

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, or the decision rule.
   PLAN.md predates `compute_coinbear.py`; thresholds are fixed constants
   (no walk-forward fit), so LOYO coincides with the fixed rule.
2. Vectorised open-to-open screen only (no vol target, governor, dip
   sleeve, funding, SL/TP, or engine limit path); maker cost only
   (0.0002/unit turnover, each path's own turnover). Needs prospective
   validation; all five years were available when the idea was scored.
3. "Not worse" uses tolerance 1e-12 (equality = PASS); the 2023 DD tie
   (0.087278 = 0.087278) counts as PASS. The 95% P&L leg uses
   RULE >= 0.95*BASE for BASE >= 0 (all five years positive), else
   RULE >= 1.05*BASE.

## One-line verdict

NOT PROMISING: per-coin bear extension (own-open < own 1200-bar mean OR
BTC bear) leaves the 2023-04-17..06-15 gate-window book loss unchanged
(-0.0504 -> -0.0506), cuts maxDD in only 3/5 years and keeps >= 95% of
book P&L in only 3/5 years — do not register an engine version.
