# crashrisk - market-state crash-risk dial for the BOT R2-4P (REPORT, 2026-10-05)

Pre-registration: `PLAN.md` (before any score). Scripts: `build_panel.py` (features, labels, causality asserts; `build.log`),
`run_crashrisk.py` (models, AUC / IC, 3 dial variants, portfolio screen, step-4 rule; `run.log`, `results.json`, `dial_hourly.parquet`),
`diag.py` (disclosed post-score diagnostic, no selection; `diag.log`, `diag.json`). Two code-crash reruns (array max / index bug) happened
before any portfolio number was printed; model outputs are deterministic (early_stopping off, random_state 0).

## Leakage
Features at T: hourly bars t <= T - 1h only; 20 random truncations at t < T + a global cut (500 T) identical (max |diff| 3e-15).
Labels at T: recomputed from bars [T-200h, T+23h] only for 20 random T (identical) and NaN when one bar short. Training rows
T + 24h < anchor - 7 d; thresholds = percentiles of out-of-fold (5 chronological blocks, 8-day purge) training predictions.
Nothing >= 2025-09-24 read (pyarrow filter + assert); bar starts >= 2025-09-24 get m = 1.

## Labels
crash24 (5-majors equal-weight index low within (T, T+24h] <= -2.5 sigma_24h, sigma from the 168 h before T): base rate 6.1 %
(2021 6.4, 2022 6.9, 2023 4.3, 2024 6.7, 2025 5.4 %). mdd24 mean ~1.2 sigma.

## (a) Predictability (test years 2021-22 / 2022-23 / 2023-24 / 2024-25; test base rate 6.7 / 5.8 / 5.7 / 5.6 %)
| model | AUC | Spearman IC vs mdd24 | crash rate in top predicted decile |
|---|---|---|---|
| HGB classifier | 0.661 / 0.682 / 0.697 / 0.698 | 0.23 / 0.17 / 0.16 / 0.25 | 11.4 / 9.4 / 13.2 / 14.8 % |
| HGB regressor (mdd24) | 0.625 / 0.645 / 0.662 / 0.666 | 0.21 / 0.17 / 0.24 / 0.31 | 10.4 / 12.7 / 12.9 / 9.9 % |
| logistic baseline | 0.668 / 0.697 / 0.713 / 0.706 | 0.27 / 0.19 / 0.21 / 0.29 | 12.4 / 13.8 / 19.0 / 13.0 % |
| raw x_br2 (no fit) | 0.578 / 0.687 / 0.699 / 0.693 | | |
Real but modest and mostly "vol clustering": risk is ~2x base rate in the top decile; the logistic beats HGB; crash breadth alone gets
most of the AUC.

## (b) Portfolio screen (approximation: r' = m(bar start) * r; ignores sizing / governor / risk-budget path effects)
dev4 = geometric %/month 2021-25, W = worst year %/month, DD = max per-year conservative DD (v388 definition); full-path DD identical
(always at 2024-01-03 12:00).
| row | R2 dev4 | R2 W | R2 DD | R2K dev4 | R2K W | R2K DD | mean m |
|---|---|---|---|---|---|---|---|
| undialled | 5.24 | 1.96 | 23.08 | 5.85 | 3.03 | 25.23 | 1 |
| D1 clf 80/95 | 4.88 | 1.37 | 22.93 | 5.42 | 2.64 | 24.84 | 0.965 |
| D2 clf 90/99 | 5.12 | 1.78 | 23.10 | 5.70 | 2.92 | 25.11 | 0.990 |
| D3 reg 80/95 | 4.86 | 1.64 | 23.19 | 5.37 | 2.79 | 25.02 | 0.966 |
| flat m = 0.965 (ref) | 5.05 | 1.89 | 22.36 | 5.63 | 2.93 | 24.32 | 0.965 |
| flat m = 0.990 (ref) | 5.18 | 1.94 | 22.87 | 5.79 | 3.00 | 24.96 | 0.990 |
Per-year (R2): undialled 1.96 / 3.85 / 4.94 / 10.40 %/mo, DD 14.0 / 15.8 / 23.1 / 8.7; D1 1.37 / 3.82 / 4.67 / 9.85, DD 13.4 / 16.0 / 22.9 / 8.2.
Per-year (R2K): undialled 3.03 / 4.30 / 5.48 / 10.76, DD 13.4 / 21.5 / 25.2 / 12.5; D1 2.64 / 4.05 / 5.00 / 10.15, DD 13.4 / 21.4 / 24.8 / 11.8.
DD drop at most 0.4 points; every dial is WORSE than holding the same average exposure flat (lower return and higher DD).

## Step 4: FAIL (no variant lowers DD by >= 2 points) -> no riskmult tables written.

## Why (diag.py, disclosed post-score)
- BOT bar returns are HIGHER when predicted risk is high: R2 mean bar return 7.1 bp at m = 0.5 vs 2.3 bp at m = 1 (R2K 3.9 / 6.3 / 4.1 vs
  2.8 bp). The dip ladder earns its money in exactly the volatile states the model flags, so the dial cuts profits.
- The binding loss, 2024-01-03 (R2 phase bar -33 % intrabar), came from a calm state: D1 m = 1.0 on all three worst bars (the dial
  dipped to 0.67 only briefly in the window). FTX (2022-11-07..10) was flagged (mean m 0.89, min 0.5) but was not the DD driver.
- The crash label is dominated by vol clustering (follow-through after a first drop), while the BOT's worst episodes are surprise
  crashes out of quiet markets.

## Caveats
Approximation only (linear scaling of bar returns; the real engine's risk budget, governor and dip sizing react to equity and would
change paths); m applied to the whole portfolio including open positions; labels on an equal-weight log index with simultaneous
intra-hour lows (slightly conservative); 4 test years with few independent crash clusters. Verdict: negative - market-state crash
prediction at the 24 h horizon does not address R2-4P's drawdown.
