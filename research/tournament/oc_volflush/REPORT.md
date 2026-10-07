# oc_volflush REPORT: capitulation volume at the fill as dip-rung context

## Setup
Majors (BTC/ETH/SOL/BNB/XRP) R2 rungs (`x1` in {2.5,3,3.5,4,5}) from
`research/tournament/ext/fills_U_ext.parquet`: 6876 fills, T = t_fill - f
(all T on 4h boundaries, all t_fill minute-exact). Years = 5 anchors
2021-09-24..2025-09-24, `[anchor, anchor+365d)` keyed by `T`
(990/1045/1330/989/1144 fills). Outcome `y1.0` = exact net at TP 1.0 sigma
(fees/funding in). Features from own-coin 1m klines (volume +
taker_buy_volume verified present; bars >= 2026-09-24 00:00 UTC dropped):
at minute f-1, `vol_ratio` = (15-min summed volume / 15) / trailing-24h
per-minute mean, `sell_share` = 15-min taker-sell fraction. Coverage 100%
both features in all 5 years (6876/6876 valid). All 5 years are research
data per assignment (disclosed vs RULES.md hidden-year rule); a PROMISING
feature would still need prospective validation. Methods fixed in PLAN.md
before any outcome was computed. Scripts: `compute_volflush.py` ->
`features_volflush.parquet`, `analyze_volflush.py` -> `results.json`
(this file renders it). Label: fill-time context -> `bot_only`.

Feature scale (pooled 6876): vol_ratio p1/p10/p50/p90/p99 =
0.53/1.17/3.08/7.46/16.21 (fills fire into elevated volume, as expected);
sell_share range 0.368/0.777 (unclipped by design; no degenerate 0/1).

## 1. Per-year Spearman IC(feature, y1.0) + tercile mean y1.0 in bps
Cut-offs q33/q67 from strictly previous data (training n grows
1378/2368/3413/4743/5732; includes pre-window rows). Pearson r secondary.

vol_ratio:

| year | n | Spearman | Pearson | Lo | Mid | Hi |
|---|---|---|---|---|---|---|
| 2021-09-24 | 990 | +0.034 | +0.016 | +46.0 (316) | +25.3 (205) | +38.5 (469) |
| 2022-09-24 | 1045 | -0.005 | +0.047 | -3.8 (279) | +3.4 (253) | +8.1 (513) |
| 2023-09-24 | 1330 | +0.041 | -0.073 | +44.4 (386) | +58.2 (420) | +21.4 (524) |
| 2024-09-24 | 989 | +0.233 | +0.185 | +4.7 (290) | +33.7 (379) | +82.9 (320) |
| 2025-09-24 | 1144 | -0.014 | -0.074 | +25.2 (293) | +26.6 (405) | -6.3 (446) |

sell_share:

| year | n | Spearman | Pearson | Lo | Mid | Hi |
|---|---|---|---|---|---|---|
| 2021-09-24 | 990 | +0.023 | +0.005 | +33.5 (459) | +29.5 (250) | +53.5 (281) |
| 2022-09-24 | 1045 | -0.024 | -0.003 | -3.3 (382) | +17.2 (365) | -3.6 (298) |
| 2023-09-24 | 1330 | -0.098 | -0.035 | +47.4 (478) | +48.2 (484) | +18.4 (368) |
| 2024-09-24 | 989 | +0.113 | +0.104 | +18.9 (286) | +45.3 (310) | +53.9 (393) |
| 2025-09-24 | 1144 | +0.048 | +0.056 | +18.1 (365) | -17.5 (337) | +33.2 (442) |

## 2. LOYO Hi-Lo spread (cut-offs from the other 4 years; bps in parens)

vol_ratio spreads (y1.0 units): -0.000404 (-4.0) / -0.000210 (-2.1) /
-0.003112 (-31.1) / +0.008183 (+81.8) / -0.003437 (-34.4) for held-out
2021..2025 (Hi/Lo n all >= 273, min 273/333).
sell_share spreads: +0.002217 (+22.2) / +0.000614 (+6.1) /
-0.003127 (-31.3) / +0.003541 (+35.4) / +0.001420 (+14.2) (min 305/366).

## 3. Decision (PROMISING = IC sign same >= 4/5 AND LOYO-spread sign same >= 4/5)

| feature | IC signs | IC count | LOYO signs | LOYO count | spread agrees w/ IC? | verdict |
|---|---|---|---|---|---|---|
| vol_ratio | + - + + - | 3/5 | - - - + - | 4/5 | NO (spread majority negative) | NOT PROMISING (IC) |
| sell_share | + - - + + | 3/5 | + + - + + | 4/5 | mixed (IC majority + but 2023 both negative) | NOT PROMISING (IC) |

Pooled-5y per-coin IC (descriptive, not part of the rule) — vol_ratio:
BNB +0.131 / XRP +0.101 / SOL +0.029 / ETH -0.004 / BTC -0.035; sell_share:
XRP +0.031 / BNB +0.023 / SOL +0.000 / ETH -0.010 / BTC -0.017. No coin
carries a stable effect either (BTC, the deepest rung book, is ~0/negative).

## Caveats / post-hoc log
1. One bug fix after the first run, before writing this report: yearly
   tercile training pools wrongly excluded pre-window rows (T < 2021-09-24),
   leaving year-2021 terciles empty. Fixed to use all rows with T < A_k per
   PLAN.md; IC/LOYO code untouched. No threshold or definition was tuned.
2. 2024 is the outlier that motivates this note: vol_ratio IC +0.23 with a
   monotone Lo->Hi tercile (+4.7/+33.7/+82.9 bps) and sell_share IC +0.11 —
   but 2025 shows nothing (vol_ratio -0.01, Hi tercile -6.3 bps), so the
   pre-registered consistency rule fails. Do not size on 2024 alone.
3. Tercile Hi-Lo magnitudes are mostly a few bps, i.e. at or below the
   ~4-8 bps round-trip cost — even a consistent sign would be a weak edge.
4. MU24 includes the 15-min spike window (standard relative-volume
   convention, frozen in PLAN.md); excluding it would only shrink ratios
   toward 1 and cannot create consistency that is absent here.
5. Fill-time features: `bot_only` — unusable for bar-open decisions.

## Verdict
NOT PROMISING for either feature as assigned: vol_ratio IC sign matches in
only 3/5 years (LOYO 4/5 negative, disagreeing with the IC majority) and
sell_share IC in only 3/5 years (LOYO 4/5 positive); keep the deployed
sizing — capitulation volume at the fill does not separate good from bad
dip fills consistently.
