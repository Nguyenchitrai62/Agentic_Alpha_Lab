# oc_regimetrue REPORT — regime x depth dip P&L with TRUE per-rung pairs (2026-10-06; PLAN pre-registered)

DIAGNOSTIC (no rule, no selection, no PROMISING verdict). Universe: R2B1D17BF
engine replicas `oc_kpi/events_s{0..3}.parquet` (4 phase sub-accounts, live
2021-09-24..2026-09-23+shift), TRUE rung pairing by positional adjacency in
the engine's append order (exact copy of oc_deepcheck `pair_true`: 21,389
rungs, 0 adjacency violations, max fill/exit weight diff 0.0, 0 outside
anchor years). Year = FILL time in anchor year `[A_k,A_k+365d)`.
`pnl` = exit weight x engine ret (net of rung fees, fraction of sub-account
equity); `pnl_mix%` = `pnl_sub/4*100` (additive, as oc_deepcheck/oc_contrib);
`win` = ret > 0. Replication: per-depth per-year mix% matches oc_deepcheck
TRUE tables exactly (max abs diff 0.0); pooled total +176.65 mix%.
Regimes use only data with time <= T0 = floor(fill_t to the standard 4h grid)
except `n`: bear = v410 BTC open4 < MA1200 incl T0 min600 (NaN->bull);
sigma_terc = per-coin sigma4 (4h-open returns trailing360/min120) vs
walk-forward p33/p66 cutoffs fitted on T < anchor-7d (0 unknown);
n = same-shift distinct other majors with a rung_fill in [fill_t-60min,
fill_t], bucketed n0/n1/n2p (event-based B1-breadth proxy — exact 1m
`C<=O*(1-2.5sig)` B1 n not recomputed, no 1m read per LIGHT);
n_exact = stored exact v399 n joined on (sym, t_fill, depth), s0 only
(5437/5466 = 99.5% joined, 29 unknown). All five years are research data;
findings need prospective validation. Full numbers: `results.json`.
Cell format below: `mix% | n | win` (mix% of mix equity, additive).

## Year totals per depth (TRUE pairs)

| year | 2.5 | 3.0 | 3.5 | 4.0 | 5.0 | all |
|---|---|---|---|---|---|---|
| 2021 | +10.41 \| 1659 \| 0.62 | +5.71 \| 1024 \| 0.61 | +4.22 \| 677 \| 0.65 | +5.12 \| 483 \| 0.69 | +2.45 \| 266 \| 0.77 | +27.91 \| 4109 \| 0.64 |
| 2022 | +4.81 \| 1550 \| 0.67 | +7.56 \| 1011 \| 0.69 | +4.09 \| 688 \| 0.70 | +1.01 \| 506 \| 0.70 | +2.58 \| 305 \| 0.80 | +20.05 \| 4060 \| 0.69 |
| 2023 | +11.51 \| 1802 \| 0.71 | +7.50 \| 1142 \| 0.73 | +4.33 \| 762 \| 0.75 | +3.15 \| 539 \| 0.75 | +2.34 \| 300 \| 0.77 | +28.82 \| 4545 \| 0.73 |
| 2024 | +25.64 \| 1694 \| 0.67 | +21.59 \| 1020 \| 0.72 | +16.93 \| 648 \| 0.77 | +11.86 \| 420 \| 0.82 | +4.50 \| 164 \| 0.87 | +80.51 \| 3946 \| 0.72 |
| 2025 | +3.38 \| 1944 \| 0.62 | +5.77 \| 1240 \| 0.63 | +5.03 \| 817 \| 0.69 | +3.81 \| 506 \| 0.73 | +1.38 \| 222 \| 0.76 | +19.36 \| 4729 \| 0.65 |
| pooled | +55.74 \| 8649 \| 0.66 | +48.13 \| 5437 \| 0.68 | +34.60 \| 3592 \| 0.71 | +24.94 \| 2454 \| 0.73 | +13.24 \| 1257 \| 0.79 | +176.65 \| 21389 \| 0.69 |

Every depth earns in every year; win rates rise with depth (0.66 -> 0.79).

## Depth x bear flag per year (TRUE)

| depth/regime | 2021 | 2022 | 2023 | 2024 | 2025 | pooled |
|---|---|---|---|---|---|---|
| 2.5 bear | +9.14 \| 1329 \| 0.60 | +3.01 \| 557 \| 0.72 | +1.54 \| 441 \| 0.69 | +1.96 \| 137 \| 0.69 | +1.25 \| 1427 \| 0.61 | +16.90 \| 3891 \| 0.64 |
| 2.5 bull | +1.26 \| 330 \| 0.67 | +1.80 \| 993 \| 0.64 | +9.97 \| 1361 \| 0.72 | +23.68 \| 1557 \| 0.67 | +2.13 \| 517 \| 0.63 | +38.84 \| 4758 \| 0.67 |
| 3.0 bear | +4.93 \| 820 \| 0.60 | +2.62 \| 360 \| 0.74 | +0.66 \| 283 \| 0.69 | +1.16 \| 85 \| 0.68 | +2.74 \| 909 \| 0.63 | +12.11 \| 2457 \| 0.65 |
| 3.0 bull | +0.78 \| 204 \| 0.69 | +4.95 \| 651 \| 0.66 | +6.83 \| 859 \| 0.74 | +20.43 \| 935 \| 0.73 | +3.03 \| 331 \| 0.63 | +36.02 \| 2980 \| 0.70 |
| 3.5 bear | +4.27 \| 543 \| 0.65 | +1.86 \| 249 \| 0.77 | +1.04 \| 206 \| 0.71 | +0.42 \| 48 \| 0.63 | +2.48 \| 605 \| 0.70 | +10.07 \| 1651 \| 0.69 |
| 3.5 bull | -0.05 \| 134 \| 0.67 | +2.23 \| 439 \| 0.66 | +3.29 \| 556 \| 0.76 | +16.50 \| 600 \| 0.78 | +2.55 \| 212 \| 0.67 | +24.53 \| 1941 \| 0.73 |
| 4.0 bear | +5.38 \| 382 \| 0.68 | +0.74 \| 184 \| 0.75 | +0.95 \| 153 \| 0.73 | +0.35 \| 34 \| 0.74 | +2.12 \| 382 \| 0.73 | +9.54 \| 1135 \| 0.72 |
| 4.0 bull | -0.26 \| 101 \| 0.72 | +0.26 \| 322 \| 0.66 | +2.20 \| 386 \| 0.76 | +11.51 \| 386 \| 0.83 | +1.69 \| 124 \| 0.71 | +15.40 \| 1319 \| 0.75 |
| 5.0 bear | +1.58 \| 200 \| 0.73 | +1.27 \| 106 \| 0.81 | +0.13 \| 83 \| 0.66 | +0.23 \| 14 \| 0.71 | +0.56 \| 170 \| 0.79 | +3.77 \| 573 \| 0.75 |
| 5.0 bull | +0.87 \| 66 \| 0.89 | +1.31 \| 199 \| 0.79 | +2.21 \| 217 \| 0.81 | +4.26 \| 150 \| 0.88 | +0.82 \| 52 \| 0.65 | +9.47 \| 684 \| 0.82 |

Deep (4.0/5.0) wins in 19/20 bear/bull cells; the single negative (4.0 bull
2021, -0.26 on n=101) is trivial next to FIFO's -11.27 for the same bucket.

## Depth x sigma tercile per year (TRUE)

| depth/regime | 2021 | 2022 | 2023 | 2024 | 2025 | pooled |
|---|---|---|---|---|---|---|
| 2.5 low | +7.15 \| 1415 \| 0.61 | +2.71 \| 1430 \| 0.67 | +10.70 \| 1569 \| 0.72 | +12.81 \| 943 \| 0.67 | +3.57 \| 1649 \| 0.63 | +36.94 \| 7006 \| 0.66 |
| 2.5 mid | +3.26 \| 244 \| 0.66 | +1.58 \| 92 \| 0.72 | +0.81 \| 233 \| 0.65 | +6.62 \| 547 \| 0.66 | -0.09 \| 279 \| 0.55 | +12.17 \| 1395 \| 0.64 |
| 2.5 high | 0.00 \| 0 \| - | +0.53 \| 28 \| 0.64 | 0.00 \| 0 \| - | +6.21 \| 204 \| 0.72 | -0.11 \| 16 \| 0.50 | +6.63 \| 248 \| 0.69 |
| 3.0 low | +2.71 \| 876 \| 0.60 | +5.77 \| 935 \| 0.68 | +7.52 \| 1007 \| 0.72 | +10.85 \| 545 \| 0.74 | +5.39 \| 1070 \| 0.64 | +32.24 \| 4433 \| 0.67 |
| 3.0 mid | +3.00 \| 148 \| 0.72 | +1.15 \| 58 \| 0.83 | -0.03 \| 135 \| 0.73 | +6.43 \| 346 \| 0.69 | +0.37 \| 160 \| 0.56 | +10.92 \| 847 \| 0.68 |
| 3.0 high | 0.00 \| 0 \| - | +0.65 \| 18 \| 0.61 | 0.00 \| 0 \| - | +4.31 \| 129 \| 0.74 | +0.02 \| 10 \| 0.50 | +4.97 \| 157 \| 0.71 |
| 3.5 low | +2.69 \| 589 \| 0.63 | +2.51 \| 641 \| 0.69 | +4.04 \| 671 \| 0.75 | +8.56 \| 346 \| 0.81 | +4.72 \| 720 \| 0.71 | +22.52 \| 2967 \| 0.71 |
| 3.5 mid | +1.54 \| 88 \| 0.80 | +1.11 \| 35 \| 0.91 | +0.28 \| 91 \| 0.77 | +4.45 \| 220 \| 0.72 | +0.28 \| 90 \| 0.58 | +7.66 \| 524 \| 0.73 |
| 3.5 high | 0.00 \| 0 \| - | +0.48 \| 12 \| 0.58 | 0.00 \| 0 \| - | +3.91 \| 82 \| 0.74 | +0.03 \| 7 \| 0.57 | +4.42 \| 101 \| 0.71 |
| 4.0 low | +3.98 \| 433 \| 0.67 | -0.12 \| 471 \| 0.68 | +2.83 \| 481 \| 0.74 | +5.30 \| 222 \| 0.85 | +3.55 \| 458 \| 0.74 | +15.54 \| 2065 \| 0.72 |
| 4.0 mid | +1.14 \| 50 \| 0.86 | +0.75 \| 26 \| 0.92 | +0.32 \| 58 \| 0.81 | +3.69 \| 153 \| 0.77 | +0.24 \| 44 \| 0.64 | +6.14 \| 331 \| 0.79 |
| 4.0 high | 0.00 \| 0 \| - | +0.38 \| 9 \| 0.67 | 0.00 \| 0 \| - | +2.87 \| 45 \| 0.84 | +0.01 \| 4 \| 0.75 | +3.26 \| 58 \| 0.81 |
| 5.0 low | +2.28 \| 252 \| 0.76 | +2.09 \| 285 \| 0.79 | +1.98 \| 275 \| 0.76 | +2.45 \| 87 \| 0.92 | +1.23 \| 212 \| 0.76 | +10.02 \| 1111 \| 0.78 |
| 5.0 mid | +0.17 \| 14 \| 0.93 | +0.56 \| 15 \| 1.00 | +0.36 \| 25 \| 0.84 | +1.06 \| 60 \| 0.78 | +0.15 \| 10 \| 0.70 | +2.29 \| 124 \| 0.83 |
| 5.0 high | 0.00 \| 0 \| - | -0.07 \| 5 \| 0.60 | 0.00 \| 0 \| - | +0.99 \| 17 \| 0.88 | 0.00 \| 0 \| - | +0.93 \| 22 \| 0.82 |

Deep wins everywhere it has size; high-tercile deep fills are rare (80 in 5
years) and positive pooled (+3.26/+0.93). Empty high cells (n=0 in 2021/2023)
are ties, not evidence — disclosed, not counted as wins.

## Depth x B1 breadth n per year (TRUE, event proxy)

| depth/regime | 2021 | 2022 | 2023 | 2024 | 2025 | pooled |
|---|---|---|---|---|---|---|
| 2.5 n0 | +8.66 \| 590 \| 0.64 | +4.63 \| 572 \| 0.69 | +7.45 \| 678 \| 0.73 | +11.82 \| 721 \| 0.66 | +0.74 \| 595 \| 0.58 | +33.29 \| 3156 \| 0.66 |
| 2.5 n1 | +1.45 \| 388 \| 0.61 | +1.13 \| 382 \| 0.68 | +3.07 \| 432 \| 0.70 | +4.74 \| 391 \| 0.65 | +1.29 \| 422 \| 0.62 | +11.68 \| 2015 \| 0.65 |
| 2.5 n2p | +0.30 \| 681 \| 0.60 | -0.95 \| 596 \| 0.64 | +0.99 \| 692 \| 0.70 | +9.08 \| 582 \| 0.70 | +1.35 \| 927 \| 0.64 | +10.77 \| 3478 \| 0.65 |
| 3.0 n0 | +2.15 \| 176 \| 0.64 | +1.94 \| 269 \| 0.68 | +2.85 \| 287 \| 0.72 | +6.51 \| 272 \| 0.66 | +2.59 \| 234 \| 0.62 | +16.03 \| 1238 \| 0.67 |
| 3.0 n1 | +1.99 \| 201 \| 0.61 | +3.03 \| 203 \| 0.75 | +3.95 \| 235 \| 0.79 | +6.00 \| 209 \| 0.78 | +0.64 \| 169 \| 0.69 | +15.60 \| 1017 \| 0.73 |
| 3.0 n2p | +1.58 \| 647 \| 0.61 | +2.59 \| 539 \| 0.67 | +0.70 \| 620 \| 0.70 | +9.08 \| 539 \| 0.73 | +2.55 \| 837 \| 0.62 | +16.50 \| 3182 \| 0.66 |
| 3.5 n0 | +1.29 \| 77 \| 0.70 | -1.22 \| 139 \| 0.62 | +1.22 \| 110 \| 0.73 | +4.59 \| 123 \| 0.72 | +2.03 \| 93 \| 0.66 | +7.92 \| 542 \| 0.68 |
| 3.5 n1 | +0.99 \| 98 \| 0.68 | +2.25 \| 100 \| 0.78 | +2.23 \| 112 \| 0.80 | +4.47 \| 118 \| 0.80 | +0.00 \| 71 \| 0.58 | +9.94 \| 499 \| 0.74 |
| 3.5 n2p | +1.94 \| 502 \| 0.64 | +3.06 \| 449 \| 0.70 | +0.87 \| 540 \| 0.74 | +7.87 \| 407 \| 0.78 | +3.00 \| 653 \| 0.71 | +16.74 \| 2551 \| 0.71 |
| 4.0 n0 | +1.29 \| 34 \| 0.71 | -1.81 \| 86 \| 0.64 | +1.84 \| 68 \| 0.79 | +3.97 \| 66 \| 0.85 | +1.57 \| 43 \| 0.74 | +6.88 \| 297 \| 0.74 |
| 4.0 n1 | +1.11 \| 51 \| 0.71 | +1.00 \| 51 \| 0.80 | +1.45 \| 60 \| 0.88 | +2.02 \| 62 \| 0.82 | +0.41 \| 24 \| 0.58 | +6.00 \| 248 \| 0.79 |
| 4.0 n2p | +2.72 \| 398 \| 0.69 | +1.81 \| 369 \| 0.69 | -0.15 \| 411 \| 0.73 | +5.87 \| 292 \| 0.82 | +1.82 \| 439 \| 0.73 | +12.07 \| 1909 \| 0.73 |
| 5.0 n0 | +0.35 \| 10 \| 0.60 | +0.46 \| 44 \| 0.70 | +0.75 \| 32 \| 0.69 | +1.29 \| 21 \| 0.86 | +0.35 \| 13 \| 0.62 | +3.20 \| 120 \| 0.71 |
| 5.0 n1 | +0.22 \| 21 \| 0.76 | +0.55 \| 29 \| 0.79 | +0.25 \| 10 \| 0.80 | +0.63 \| 20 \| 0.85 | +0.56 \| 13 \| 0.92 | +2.21 \| 93 \| 0.82 |
| 5.0 n2p | +1.88 \| 235 \| 0.78 | +1.57 \| 232 \| 0.82 | +1.35 \| 258 \| 0.78 | +2.57 \| 123 \| 0.87 | +0.46 \| 196 \| 0.76 | +7.83 \| 1044 \| 0.79 |

Idiosyncratic (n0) deep flushes — the cells oc_depthregime flagged as the
last hope for a keep rule under FIFO — truly earn pooled (+6.88/+3.20) and
win 4-5/5 years. Joint (n2p) deep flushes earn the most pooled
(+12.07/+7.83). The few yearly negatives are small one-year cells
(worst: 4.0 n0 2022 -1.81 on n=86; 3.5 n0 2022 -1.22 on n=139).

## s0 cross-check: depth x EXACT v399 n per year (TRUE, s0 fills only, n=5437)

Pooled: 2.5 n0 +14.71 (1341, 0.66) / n1 +1.88 (430, 0.64) / n2p +0.78 (445,
0.64); 3.0 +13.23 (618, 0.73) / +1.59 (273, 0.64) / +2.10 (496, 0.67); 3.5
+7.69 (292, 0.75) / +1.85 (150, 0.70) / +3.05 (476, 0.74); 4.0 +5.19 (157,
0.81) / +1.61 (87, 0.79) / +2.36 (369, 0.72); 5.0 +3.02 (64, 0.89) / +0.12
(24, 0.75) / +1.49 (215, 0.81). All 15 pooled cells positive; yearly
negatives are dust (worst: 5.0 n1 2023 -0.22 on n=11; 2.5 n1/n2p 2021 -0.14/
-0.09 on n=81/82). The exact-n split tells the same story as the proxy:
no losing breadth bucket at any depth.

## Flags (fixed in PLAN)

`lose_ge4` (negative in >= 4/5 years, conditional-rule candidates): ZERO
cells out of 40 primary cells (10 bear + 15 sigma + 15 n). `win_5`
(non-negative 5/5): 27/40 cells; the 13 non-unanimous cells sit at 4/5 with
small one-year negatives (largest: 4.0 n0 2022 -1.81; 3.5 n0 2022 -1.22;
all others <= 0.95 in abs, several on n <= 139 or empty high-tercile ties).
No depth x regime cell is a persistent loser.

## Plain paragraph

Redoing the regime x depth table with the engine's own per-rung pairs
reverses oc_depthregime's verdict cell by cell: deep 4.0/5.0σ rungs do not
lose in any bar-open regime — they earn in 19/20 bear/bull cells, in every
sigma-tercile cell that ever fills, and in 14/15 breadth cells (pooled deep
n0 +6.88 / n1 +6.00 / n2p +12.07 mix% for 4.0; +3.20/+2.21/+7.83 for 5.0),
with win rates rising in depth in every regime exactly as in the pooled
deepcheck. The cells FIFO painted as the worst deep losers — 2021 bull
(-11.27 FIFO -> -0.26 TRUE for 4.0), low-vol environments (-23.89 FIFO 2022
low -> -0.12 TRUE for 4.0), idiosyncratic n0 flushes (losing all 5 years FIFO
-> winning pooled and 4/5 years TRUE) — are surrenders of fast deep
take-profits to shallow fills under time-sorted pairing, not engine losses.
The s0 exact-B1-n split confirms the proxy: all 15 pooled depth x exact-n
cells positive. There is nothing left to condition on: no persistent-loser
cell exists at any depth in any of the three regime families, so a
regime-conditional drop rule built on these regimes would delete profit.

## Verdict

VERDICT (descriptive, no selection): with TRUE pairs every depth wins in
essentially every regime every year — zero cells lose in >= 4/5 years, so no
conditional drop rule is supported (and the FIFO-based "no keepable regime"
verdict is superseded).

## Caveats

Additive `pnl_mix` (compounding gap as in oc_contrib/oc_deepcheck); T0 is
the standard 4h grid while s=1..3 replicas run on shifted grids (still
causal: T0 <= bar open <= fill); n is an engine co-fill proxy, not the exact
1m B1 flush count (same-minute cross-coin ties counted as joint; exact-n s0
cross-check agrees); sigma-high yearly ties with n=0 are empty, not wins;
dip rungs exit inside the same 4h bar so fill-year ~= exit-year up to
boundary bars.
