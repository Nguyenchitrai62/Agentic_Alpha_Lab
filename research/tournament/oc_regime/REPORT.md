# oc_regime REPORT: do slow regimes separate good from bad dip periods?

Universes: MAIN = 5 majors x R2 depths (2.5/3/3.5/4/5), outcome y1.0 fill mean;
POOLED = all 35 coins x same depths. Anchor years start each 2021-09-24 .. 2025-09-24.
Baseline (no-gate) mean y1.0 per fill: MAIN 38/4/40/41/13 bps; POOLED 35/-8/16/27/24 bps
(years 21-22 .. 25-26). Round-trip cost context ~4-8 bps.

## Verdict

MAIN (the BOT question): NO variable is CONSISTENT. Best candidates fail the sign rule:
trend30 (sign 3/5, gate 4/5), volratio (3/5, 4/5), corr30 (3/5, 4/5) — each flips sign in
>= 2 of 5 years. stress30 has the most one-sided sign (4/5 positive) but its
pre-registered gate is degenerate (training median 0, good side below = no months kept,
0/5). Nothing supports a slow-regime gate on majors dip bids.
POOLED: corr30 (sign 4/5 all >= 0 except 25-26 at -0.01, gate 5/5, good side above = take
dips when 30d cross-coin correlation is high) and dd90 (sign 4/5 negative, gate 4/5, good
side below = take dips when BTC is further off its 90d high) meet the pre-registered
CONSISTENT rule. breadth50 (sign 5/5 negative, gate 3/5) does not.

## Tables

MAIN Spearman rho month-start regime vs monthly edge (n=12 each):
var       21-22 22-23 23-24 24-25 25-26 | gate helps 21..25
trend30   +0.08 -0.14 +0.15 -0.15 +0.35 | 1 1 1 1 0
trend90   -0.03 -0.32 +0.20 +0.07 +0.34 | 1 0 0 0 1
volratio  +0.65 +0.27 -0.04 -0.49 -0.12 | 1 1 1 0 1
corr30    +0.31 +0.45 -0.27 +0.01 -0.34 | 1 1 1 0 1
stress30  +0.50 +0.33 -0.09 +0.03 +0.13 | 0 0 0 0 0 (gate keeps 0 months)
breadth50 +0.22 -0.37 +0.31 -0.15 +0.52 | 0 0 1 0 0
dd90      -0.16 -0.38 +0.12 -0.12 +0.43 | 0 0 1 0 1
vollevel  +0.62 +0.31 -0.06 -0.31 -0.50 | 0 1 0 0 1

POOLED Spearman rho / gate helps:
trend30   -0.08 +0.07 -0.53 -0.44 -0.02 | 0 0 0 1 1
trend90   -0.03 -0.27 -0.10 -0.15 +0.12 | 0 1 1 1 0
volratio  +0.48 +0.17 +0.15 -0.49 -0.08 | 0 0 0 0 1
corr30    +0.29 +0.26 +0.25 +0.20 -0.01 | 1 1 1 1 1 CONSISTENT
stress30  +0.44 -0.01 +0.35 +0.39 +0.19 | 0 0 0 0 0 (gate keeps 0 months)
breadth50 -0.02 -0.35 -0.37 -0.47 -0.05 | 0 1 1 1 0
dd90      -0.27 -0.20 -0.47 -0.42 +0.28 | 0 1 1 1 1 CONSISTENT
vollevel  +0.59 +0.12 +0.28 -0.22 +0.10 | 0 1 1 0 1

Full numbers (thresholds, kept months/fills, with/without means): results.json.
Monthly series: monthly_main.csv, monthly_pooled.csv. Regimes: regimes_daily.parquet.

## Caveats / post-hoc log

1. PLAN fixed hourly.parquet as the only source, but it ends 2025-09-23 while year 5 needs
   regimes to 2026-09-01. Post-hoc extension (same causal day rule): daily closes from 1m
   raw after 2025-09-23. Overlap 2024-09-01..2025-09-23 agrees EXACTLY (median|logdiff|=0).
2. Bug fix after first run: volratio window was 365d for a 30d-rolling quantity (always
   NaN); fixed to 394d window, median of last 365 (matches PLAN intent). Logged here.
3. Power is low (12 months/year); Spearman signs flip easily — the MAIN null result may
   reflect noise, not proof of no regime effect. Pooled CONSISTENT flags are
   hypothesis-generating, not a trading rule (gates keep as few as 2 months/year).
4. Causality: 20-day truncate-and-recompute passes; future-spike test passes;
   dev/ext T-split has no overlap (tests/test_oc_regime.py, 5 passed).
