# oc_fundregime REPORT: Binance settled funding as a crowding regime

Feature: F(T) = cross-major mean 7-day settled funding, settlements in
[T-7d, T) only (21 per coin required, else NaN; strict end<T verified by
test). Universe: BOT book grid 10955 4h bars (2021-09-24..2026-09-23;
2190 bars per literal +365d year, 2189 in the last after dropping the bar
with no forward return; 6 bars of 2024-09-23 in no year) and 6876
majors-R2 dip fills (per-year 990/1045/1330/989/1144). Cut-offs from
strictly previous data only. Funding files end 2026-08-31 16:00 UTC, so
T >= 2026-09-01 04:00 is NaN by construction (year-5 coverage ~94-95%).

## Verdict

NOT PROMISING for both primaries, hence overall NOT PROMISING. The funding
level is too non-stationary for backward-looking terciles to transfer: the
Hi bucket is EMPTY in 3 of 5 dip years (and the 2022 book year), because
bull-market training cut-offs (dip q67 5.51 bps for year 1) are never
revisited in bear years. Where computable, signs are inconsistent (dip 2024
spread +32.9 bps, book 2024 +0.87 bps — both the WRONG sign and, for dips,
large). Book long-leg spreads are sub-1-bps per-bar means — negligible
against ~4-8 bps costs even where the sign matches.

## Tables

Book long-leg per-row mean gross pnl by funding tercile, bps [n rows]
(Hi-Lo spread = primary E_book, expect negative):
2021-22: lo +0.55 [3116] / mid +0.02 [1862] / hi +0.21 [120]  -> spread -0.35
2022-23: lo +1.34 [2290] / mid -0.08 [2937] / hi -- [0]       -> FAIL (Hi empty)
2023-24: lo +1.27 [423]  / mid +0.96 [1969] / hi +0.90 [4119] -> spread -0.37
2024-25: lo +0.73 [965]  / mid +0.41 [3732] / hi +1.60 [1852] -> spread +0.87
2025-26: lo +0.39 [1078] / mid +0.96 [2259] / hi +0.12 [180]  -> spread -0.26
year neg: 3/5. Book LOYO long-leg spreads: -1.54 / -1.62 / -0.81 / -0.35 / +0.09
-> neg 4/5. PASS requires 4/5 on BOTH -> book FAILS on (a).

Book short-leg (descriptive, no rule): 2021 lo +0.24/mid +0.97/hi --;
2022 lo -0.27/mid +0.53/hi --; 2023 lo -0.10/mid -0.34/hi +0.87;
2024 lo +0.40/mid -0.09/hi +0.16; 2025 lo +0.12/mid +0.49/hi -- (bps [n] in
results.json). No consistent mirror image of the long leg.

Dip mean y1.0 by funding tercile, bps [n] (Hi-Lo = primary E_dip, expect negative):
2021-22: lo +35.8 [959] / mid +110.1 [31] / hi -- [0]    -> FAIL (Hi empty)
2022-23: lo +18.7 [571] / mid -24.5 [420]  / hi -- [0]    -> FAIL (Hi empty)
2023-24: lo +62.1 [91]  / mid +21.9 [732]  / hi +61.3 [507] -> spread -0.8
2024-25: lo +26.2 [204] / mid +39.4 [560]  / hi +59.0 [225] -> spread +32.9
2025-26: lo +7.9 [709]  / mid +18.4 [382]  / hi -- [0]    -> FAIL (Hi empty)
year neg: 1/5. Dip LOYO spreads: +22.6 / +18.7 / -55.8 / +15.2 / None
-> neg 1/5. Dip FAILS on both (a) and (b).

Training q67 (bps) shows the regime shift: dip-row cut-offs
5.51 / 2.96 / 1.21 / 1.23 / 1.14; book-clock cut-offs
3.19 / 1.37 / 0.71 / 0.76 / 0.71. Spot check 2021-03-15: cross-major 7d mean
+8.6 bps (bull); bear years sit near 0-1 bps.

## Caveats / post-hoc log

1. No post-hoc change to definitions, universe, cut-off rules, or the
   decision rule. The script was run once; results.json is that single run.
2. Coverage diagnostics (found after the run, rule untouched): SOL funding
   switched 8h -> 4h -> 2h over 2022-11-09..18 (FTX collapse; all other coins
   always 8h), so 7d windows overlapping it hold != 21 SOL settlements -> NaN
   (~92 book bars, ~54 dip rows, all inside 2022-23). Pre-2020-09-21 T is NaN
   (SOL series starts 2020-09-13). Both are the pre-registered "else NaN".
3. The 2023 dip LOYO spread (-55.8 bps) rests on a 49-row Lo bucket (deeply
   negative post-FTX funding); the 2021 dip mid bucket (+110 bps, n=31) is
   likewise noise. Fragile cells, not signals.
4. First-four-year read (repo selection uses 2021-2024): book yearly neg 2/4
   with one FAIL year; dip neg 1/4 — fails there too, so the verdict does not
   hinge on the most recent year.
5. Book pnl is gross weight x next-bar return (before vol target, fees,
   funding); dip y1.0 is exact net. All five years are research data;
   this negative finding needs no prospective follow-up, but any future use
   of funding levels must solve the non-stationarity (e.g. z-scored or
   coin-relative funding, pre-registered separately).

## One-line verdict

NOT PROMISING: high-vs-low 7d funding spreads have the expected negative sign
in only 3/5 book years (4/5 LOYO) and 1/5 dip years (1/5 LOYO), Hi buckets are
repeatedly empty because the funding level does not revisit bull-era cut-offs,
and the computable 2024 spreads go the wrong way — funding level, as defined,
does not separate book or dip outcomes consistently.
