# oc_dvolshort REPORT: DVOL gate on BOOK SHORTS (idea #13)

Book = `forward_v205.research_books_d2` (rebuilt exactly, cell-checked vs
oc_bookic); opens = v154 4h opens. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins = 54775 rows. Rule (fixed in PLAN.md): per (T, sym), with `z` =
mapped `dvol_z90` exactly as oc_dvolbook (as-of = last hourly close with
bar END <= T; z vs trailing 2160 as-of samples, current excluded),
if `w[T,s] < 0` and `z > q67_k` then `w_g = 0.5*w`, else `w_g = w`
(longs/flats/NaN-z unchanged). `q67_k` = walk-forward 67th percentile of
pooled mapped `z` over `[2021-06-30, A_k)` only (matches oc_dvolbook's
cut-offs cell-for-cell). Screen = open-to-open 4h returns with gate
costs: net cell = `w*R1 - 0.0002*|w - w_prev|` per sym (first prev = 0;
gated path uses its own gated prev). Short-leg sums use ORIGINAL `w`
sign so gated vs ungated compare identical rows. Equity per year reset
to 1 and compounded as `eq *= 1 + sum_s pnl`; maxDD = peak-to-trough;
worst week = min 42-bar compounded return. Full tables in `results.json`;
`panel.parquet` holds per-(T,sym) rows. Coverage of `z` is 100% all years.

## Verdict

PROMISING (as assigned): book maxDD improves (gated < ungated) in 4/5
years and total book P&L is not lower (gated >= ungated) in 3/5 years.
The 2025 year fails on BOTH legs, matching the oc_dvolbook 2025 fade.

## Per-year screen (net, portfolio-return units; costs included)

| year | q67 | share shorts gated | short P&L ungated / gated | total book P&L ungated / gated | worst week ungated / gated | maxDD ungated / gated | DD improves | P&L not lower |
|---|---|---|---|---|---|---|---|---|
| 21-22 | -0.363210 | 0.463 | 0.138483 / 0.131585 | 0.309477 / 0.302617 | -0.103131 / -0.103100 | 0.131523 / 0.120962 | yes | no |
| 22-23 | -0.150886 | 0.210 | 0.023063 / 0.051849 | 0.306504 / 0.335309 | -0.046676 / -0.046676 | 0.069606 / 0.066478 | yes | yes |
| 23-24 | -0.293635 | 0.465 | -0.043047 / -0.016368 | 0.563893 / 0.590610 | -0.068789 / -0.065654 | 0.086094 / 0.080729 | yes | yes |
| 24-25 | 0.025842 | 0.332 | 0.044956 / 0.045182 | 0.557065 / 0.557326 | -0.045264 / -0.045611 | 0.062817 / 0.054240 | yes | yes |
| 25-26 | 0.052801 | 0.527 | 0.178036 / 0.131751 | 0.475135 / 0.428889 | -0.069087 / -0.064030 | 0.078414 / 0.083575 | no | no |

Counts: DD improves 4/5; P&L not lower 3/5. Full 5y path (context,
compounded from year-1 start): maxDD 0.131523 -> 0.120962 gated;
total P&L 2.212075 -> 2.214751 gated (essentially flat, +0.0027 over 5y).

Read: the gate cuts the short-loss years where oc_dvolbook said shorts
suffer (2022 short P&L more than doubles; 2023 short loss shrinks by
~60%), trims per-year DD by ~0.3-1.1pp in 2021-2024, and costs little
total P&L except in 2021 (-0.0069) and 2025 (-0.0462, where shorts were
strong and gating hurt). Worst-week changes are negligible except 2023
(-0.0688 -> -0.0657) and 2025 (-0.0691 -> -0.0640).

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, thresholds, or the
   decision rule. PLAN.md was written before `compute_dvolshort.py` ran.
2. Performance-only changes toward PLAN (verified, not outcome-driven):
   `z90` uses a rolling(2160, min_periods=1728).mean/std shifted by one,
   which is algebraically identical to oc_dvolbook's k=1..2160 loop on
   the gap-free hourly grid (checked on 5 dates vs oc_dvolbook's
   `features_for_times` to 1e-9 for BTC and ETH); per-bar sums use
   groupby (exact). Thresholds reproduce oc_dvolbook's q67 to 1e-6.
3. 2025 fails both criteria (DD worse, total P&L lower) and 2021 trades
   lower P&L for lower DD — the PASS rests on 2022-2024 plus a DD-only
   win in 2021. Same fade oc_dvolbook flagged (its 2025 short spread was
   -0.04, flat).
4. Vectorised open-to-open screen only (no vol target, governor, dip
   sleeve, funding, SL/TP, or engine limit path); maker cost only
   (0.0002/unit turnover, gated path's own turnover). Short-leg
   membership fixed by the original sign. Needs prospective validation;
   in-sample walk-forward style (thresholds strictly pre-anchor, but all
   five years were available when the idea was scored).

## One-line verdict

PROMISING (as assigned): DVOL short-gate (x0.5 shorts when mapped z90 >
walk-forward q67) cuts book maxDD in 4/5 years with total P&L not lower
in 3/5 (2025 fails both; 5y total flat) — DD-first context, not a return
edge.
