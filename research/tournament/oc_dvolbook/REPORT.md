# oc_dvolbook REPORT: DVOL context for the deployed BOT book

Book = `forward_v205.research_books_d2` (rebuilt exactly, cell-checked vs
oc_bookic); opens = v154 4h opens. Grid = 10955 bars (2021-09-24..2026-09-23
16:00 UTC; last bar dropped, no forward open) x 5 coins = 54775 rows. Metric =
`w[T,s] x (open[T+1]/open[T]-1)`, gross, NO costs, before vol target/governor/
sleeve/SL-TP. DVOL as-of = last hourly close with bar END <= T (causal).
Features mapped BTC->BTCDVOL, ETH->ETHDVOL, SOL/BNB/XRP->BTCDVOL. Coverage 100%
in all 5 anchor years (warm-up ends 2021-06-30, before year 1). Full tables in
`results.json`; `panel.parquet` holds the per-(T,sym) rows.

## Verdict

PROMISING (as assigned) for the SHORT leg only: high-DVOL tercile earns worse
short-leg P&L than the low tercile in 5/5 years with 4/5 LOYO sign consistency
(the 5th LOYO spread is -0.00, flat — not a flip). Total and long legs FAIL
(3/5 both). Effect sizes are small (sub-bps per unit weight) and fade in 2025 —
a sizing/gate context, not a standalone edge.

## Q1. Spearman IC(feature, forward open-to-open return) per anchor year

R42 (7-day), pooled / BTC-only / ETH-only:

| feat | 21-22 | 22-23 | 23-24 | 24-25 | 25-26 |
|---|---|---|---|---|---|
| z90 pooled | +0.23 | +0.11 | +0.11 | +0.11 | +0.01 |
| z90 BTC | +0.27 | +0.13 | +0.05 | +0.16 | -0.00 |
| z90 ETH | +0.13 | +0.06 | +0.11 | +0.03 | +0.08 |
| chg24 pooled | +0.05 | +0.02 | +0.14 | +0.02 | -0.01 |
| vrp pooled | +0.03 | -0.05 | +0.14 | -0.07 | -0.00 |

R6 (1-day) is weaker and mixed (z90 pooled +0.10/+0.02/+0.09/+0.06/-0.00;
chg24 and vrp flip signs across years — see results.json). ICs are descriptive
context only (NOT part of the decision rule). Read: elevated DVOL level leans
with HIGHER 7-day forward returns (contrarian bounce, consistent with oc_dvol's
dip-fill finding), but the 2025 fade warns against over-reading.

## Q2. Book P&L by z90 tercile (cut-offs from PREVIOUS data only), bps/unit

Mean pnl per (bar, coin) [n]; spread = Hi - Lo:

| year | total lo / hi (spread) | long lo / hi (spread) | short lo / hi (spread) |
|---|---|---|---|
| 21-22 | +0.25 / +0.52 (+0.27) | -0.05 / +1.33 (+1.37) | +0.70 / +0.07 (**-0.63**) |
| 22-23 | +0.53 / -0.31 (-0.84) | +0.85 / -0.12 (-0.97) | +0.29 / -0.54 (**-0.83**) |
| 23-24 | +0.31 / +0.75 (+0.44) | -0.02 / +1.19 (+1.21) | +0.62 / -0.27 (**-0.89**) |
| 24-25 | +0.43 / +0.74 (+0.31) | +0.51 / +1.15 (+0.63) | +0.33 / -0.01 (**-0.34**) |
| 25-26 | +0.51 / +0.30 (-0.20) | +0.71 / +0.39 (-0.32) | +0.32 / +0.28 (**-0.04**) |
| sign | 3/5 (+) FAIL | 3/5 (+) FAIL | **5/5 (-) PASS** |

LOYO spreads (training = other 4 years): total +0.29/-1.08/+0.46/+0.23/-0.13
(3/5 FAIL); long +2.10/-1.11/+1.06/+0.59/-0.80 (3/5 FAIL); short
-0.76/-1.05/-0.92/-0.38/-0.00 (**4/5 (-) PASS**, 5th is flat zero).

## Q3. Does high DVOL predict larger book losses or better book returns?

Neither, on the total book: Hi-tercile mean pnl >= Lo in 3/5 years and loss
frequency P(pnl<0) is flat across terciles (~0.40-0.49 every year x tercile).
Average loss size is somewhat larger in Hi in 2022 (-8.0 vs -4.7 bps) and 2023
(-7.4 vs -5.2 bps), but not in 2021/2024/2025. The consistent DVOL pattern is
leg-specific, not crash-shaped: **shorts** earn less (or lose) when z90 is high
(Hi short-leg mean <= Lo in 5/5; worst Hi short years 2022-23, the bear market),
while longs are unaffected-to-better. So high DVOL marks adverse tape for the
book's shorts (relief-squeeze risk), not a general book drawdown state.

## Proposed (NOT tested) follow-up — one rule, with economic reason

**Short-scale in elevated IV**: scale short-leg book weights down (e.g. x0.5,
cut-off q67 fitted on pre-anchor data only, walk-forward) when mapped dvol_z90
is in its top tercile. Reason: high implied vol prices in fear and forced
positioning; a slow momentum book's shorts sit directly in the path of the
fastest moves in the sample — bear-market relief rallies — where short losses
are unbounded while the long edge survives. Must be judged walk-forward by the
leader (this study is in-sample walk-forward style; 2025 already fades).

## Caveats / post-hoc log

1. PLAN amendment BEFORE any computation: year-1 cut-off pool uses the
   pre-anchor 4h grid (2021-06-30..2021-09-24, ~2.5k feature values; cut-offs
   need no weights) since the book grid starts exactly at A_0. Still strictly
   previous-data-only; no outcome had been seen.
2. Bug fix AFTER first run (toward PLAN, which already required dropping the
   last grid bar): the trailing bar's NaN pnl leaked into one 2025 mid-bucket
   mean. Dropped; spreads/counts unchanged (5 rows of 54780). No definition,
   universe, or rule change.
3. 2025 fade: short year-spread -0.04 and LOYO -0.00 — the PASS rests on
   2021-2024 plus a flat (not flipped) 2025. Weak, context-only.
4. Multiple comparisons: 3 legs x (5 year + 5 LOYO) spreads; nominal look — the
   pre-registered 5/5 + 4/5 bar is the test, and only the short leg clears it.
5. Gross vectorised P&L only (no fees/funding/vol-target/governor/SL-TP/
   compounding); timing is next-bar open-to-open, not the engine limit path.
   In-sample walk-forward style; needs prospective validation.

## One-line verdict

PROMISING (as assigned): elevated DVOL predicts worse short-leg book P&L with
5/5-year and 4/5-LOYO sign consistency (total/long fail at 3/5) — small,
fading-in-2025 effect, suitable at most as a short-scale context, not a gate.
