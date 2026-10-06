# oc_g2k20robust: friction robustness of v422 G2K20 + carry f=0.25 (diagnostic, no selection)

Row G2K20 = R2B1D17BF with dip multiplier kd 2.0, budget 0.26 x 2.0,
sleeve_gross_cap 2.0 (research/parallel/rounds/parallel-20260906-r2/v422/v422_cap_frontier.py).
Friction set exactly as v421_audit/ROBUST.md / robust_v421.py (S1 cost stress
MAKER 0.0004/TAKER 0.0012, S2 latency 15/16, S3 latency 30/31, S4 stop slip 0.5,
S5 Bybit prices from 2021-11-15). Harness = 4 phases (shifts 0..3), per-year reset
metric (reset_metric.year_reset), full-path conservative DD of the equal 1/4 mix
from 2021-09-24 (v388.mix). Base row from the v422_runs.pkl cache (reproduced here).
Carry f=0.25 overlay: method reused UNCHANGED from
research/tournament/oc_carryfric/combine_carryfric.py (which imports
oc_carryd13/combine_carryd13.py); G2+carry values are oc_carryfric/results.json,
recomputed here to the digit (max gap 0.0). S1 carry-cost stress is the same labelled
assumption (spot 0.0015/side + fut taker 0.0012 entry, delivery 0.0002 unchanged).
DIAGNOSTIC ONLY: no selection is made.

## G2K20 baseline (v422 cache reproduced, reset metric)

| year | %/month | DD |
|---|---|---|
| 2021-09-24 | 2.832 | 12.01 |
| 2022-09-24 | 3.272 | 17.79 |
| 2023-09-24 | 7.149 | 15.79 |
| 2024-09-24 | 11.644 | 9.34 |
| 2025-09-24 | 4.716 | 13.65 |

5y geometric mean 5.874 %/month, max year DD 17.79, full-path DD 17.69.
v422_result.json cross-check: R 5.874 / DD 17.79 / full-path 17.69.

Most-recent-year fold (v422/result_manifest.json): fold 4 (test year 2025-09-24) chose G2K20 with test R 4.716 / DD 13.65 vs R2B1D17BF ref R 5.060 / DD 12.81, good=False; transfer=False, final=G2K20. So G2K20 earlier FAILED the most-recent-year fold (4.716 vs 5.06: weaker in 2025-26, like every cap row).

## Frictions: G2K20 vs G2 (per-year %%/month / DD, 5y mean, max DD, full DD)

| scenario | 2021 | 2022 | 2023 | 2024 | 2025 | mean5y | maxDD | fullDD |
|---|---|---|---|---|---|---|---|---|
| base G2K20 | 2.832 / 12.01 | 3.272 / 17.79 | 7.149 / 15.79 | 11.644 / 9.34 | 4.716 / 13.65 | 5.874 | 17.79 | 17.69 |
| base G2 (v421_audit) | 2.588 / 10.86 | 3.282 / 16.91 | 6.045 / 15.81 | 10.677 / 8.27 | 4.648 / 12.90 | 5.410 | 16.91 | 16.82 |
| S1 G2K20 (cost stress MAKER 0.0004/TAKER 0.0012) | 2.194 / 12.38 | 2.556 / 18.01 | 5.580 / 15.98 | 10.568 / 9.35 | 3.833 / 15.17 | 4.903 | 18.01 | 17.92 |
| S1 G2 | 1.975 / 11.18 | 2.592 / 17.45 | 4.853 / 16.01 | 9.712 / 8.31 | 3.900 / 13.61 | 4.571 | 17.45 | 17.37 |
| S2 G2K20 (latency 15/16) | 2.773 / 11.95 | 3.123 / 17.80 | 6.783 / 15.84 | 11.448 / 9.35 | 4.559 / 13.76 | 5.690 | 17.80 | 17.72 |
| S2 G2 | 2.513 / 11.09 | 3.132 / 16.91 | 5.624 / 15.82 | 10.479 / 8.29 | 4.501 / 12.98 | 5.212 | 16.91 | 16.86 |
| S3 G2K20 (latency 30/31) | 2.205 / 12.86 | 2.616 / 17.90 | 4.953 / 15.91 | 10.664 / 9.45 | 4.394 / 13.53 | 4.924 | 17.90 | 17.82 |
| S3 G2 | 2.070 / 11.85 | 2.476 / 17.32 | 4.346 / 16.03 | 9.798 / 8.36 | 4.380 / 12.75 | 4.578 | 17.32 | 17.24 |
| S4 G2K20 (stop slip 50%) | 2.665 / 12.76 | 3.049 / 17.95 | 5.118 / 17.08 | 11.447 / 9.34 | 4.555 / 14.40 | 5.320 | 17.95 | 17.86 |
| S4 G2 | 2.363 / 11.06 | 2.915 / 17.31 | 4.422 / 17.08 | 10.460 / 8.27 | 4.522 / 13.54 | 4.898 | 17.31 | 17.24 |
| S5 G2K20 (Bybit prices from 2021-11-15) | 2.338 / 12.83 | 2.678 / 18.76 | 6.002 / 16.70 | 11.450 / 10.47 | 4.494 / 13.27 | 5.342 | 18.76 | 19.61 |
| S5 G2 | 2.129 / 12.36 | 2.735 / 18.11 | 4.932 / 16.89 | 10.377 / 9.22 | 4.443 / 12.37 | 4.883 | 18.11 | 18.09 |

## Both + frozen carry f=0.25 (oc_carryfric method; chained-reset full DD, labelled)

| scenario | 2021 | 2022 | 2023 | 2024 | 2025 | mean5y | maxDD | fullDD(ch) |
|---|---|---|---|---|---|---|---|---|
| base G2K20+carry0.25 | 2.976 / 11.78 | 3.325 / 17.66 | 7.403 / 15.75 | 11.737 / 9.24 | 4.747 / 13.40 | 5.989 | 17.66 | 17.66 |
| base G2+carry0.25 (oc_carryfric) | 2.736 / 10.68 | 3.334 / 16.78 | 6.329 / 15.77 | 10.779 / 8.17 | 4.680 / 12.65 | 5.533 | 16.78 | 16.78 |
| S1 G2K20+carry0.25 | 2.334 / 12.13 | 2.605 / 17.88 | 5.864 / 15.95 | 10.662 / 9.25 | 3.862 / 14.70 | 5.022 | 17.88 | 17.88 |
| S1 G2+carry0.25 (oc_carryfric) | 2.118 / 11.01 | 2.640 / 17.31 | 5.159 / 15.98 | 9.814 / 8.21 | 3.929 / 13.37 | 4.696 | 17.31 | 17.31 |
| S2 G2K20+carry0.25 | 2.917 / 11.72 | 3.176 / 17.67 | 7.046 / 15.80 | 11.543 / 9.25 | 4.590 / 13.52 | 5.807 | 17.67 | 17.67 |
| S2 G2+carry0.25 (oc_carryfric) | 2.662 / 10.91 | 3.185 / 16.77 | 5.921 / 15.78 | 10.583 / 8.18 | 4.533 / 12.73 | 5.339 | 16.77 | 16.77 |
| S3 G2K20+carry0.25 | 2.359 / 12.60 | 2.673 / 17.77 | 5.271 / 15.86 | 10.766 / 9.35 | 4.426 / 13.29 | 5.056 | 17.77 | 17.77 |
| S3 G2+carry0.25 (oc_carryfric) | 2.226 / 11.65 | 2.533 / 17.18 | 4.684 / 15.98 | 9.910 / 8.25 | 4.412 / 12.51 | 4.717 | 17.18 | 17.18 |
| S4 G2K20+carry0.25 | 2.812 / 12.49 | 3.103 / 17.82 | 5.430 / 17.05 | 11.542 / 9.24 | 4.587 / 14.15 | 5.448 | 17.82 | 17.82 |
| S4 G2+carry0.25 (oc_carryfric) | 2.514 / 10.82 | 2.969 / 17.18 | 4.758 / 17.04 | 10.565 / 8.17 | 4.553 / 13.29 | 5.033 | 17.18 | 17.18 |
| S5 G2K20+carry0.25 | 2.489 / 12.63 | 2.734 / 18.63 | 6.288 / 16.57 | 11.544 / 10.37 | 4.526 / 13.03 | 5.465 | 18.63 | 19.72 |
| S5 G2+carry0.25 (oc_carryfric) | 2.284 / 12.16 | 2.790 / 17.98 | 5.250 / 16.75 | 10.482 / 9.12 | 4.475 / 12.12 | 5.016 | 17.98 | 17.98 |

## Verdict: is G2K20 more or less fragile than R2B1D17BF/G2 under frictions?

Mean-5y drops G2K20 {'S1': -0.971, 'S2': -0.184, 'S3': -0.95, 'S4': -0.554, 'S5': -0.532}; G2 {'S1': -0.839, 'S2': -0.198, 'S3': -0.832, 'S4': -0.512, 'S5': -0.527}. G2K20 is MORE fragile on return-drop size than G2 (its S1/S3 drops are larger), but it starts from a higher base (5.874 vs 5.410) so its absolute friction levels stay above G2's in every scenario (S1 4.903 vs 4.571, S3 4.924 vs 4.578, S4 5.320 vs 4.898, S5 5.342 vs 4.883).

## Plain answer: does G2K20 (+ carry f=0.25) keep 5y >= 5.0 and DD < 20
## under EVERY friction where G2 fails?

G2 fails the 5y>=5.0 bar at S1 (4.571), S3 (4.578), S4 (4.898), S5 (4.883) without carry (S2 passes at 5.212); with carry f=0.25 it still fails at S1 (4.696) and S3 (4.717). DD is < 20 for G2 everywhere (max 18.11), so the DD bar is not the binding constraint. G2K20+carry f=0.25 keeps 5y >= 5.0 AND DD < 20 under EVERY one of those G2-failing frictions (worst: S1 at 5.022). Plain YES for the return+DD bar taken together; without carry G2K20 alone fails at S1, S3. Per-friction detail: S1: G2 4.571 (DD 17.45/17.37, pass=False) | G2+carry0.25 4.696 (DD 17.31/17.31, pass=False) | G2K20 4.903 (DD 18.01/17.92, pass=False) | G2K20+carry0.25 5.022 (DD 17.88/17.88, pass=True) // S2: G2 5.212 (DD 16.91/16.86, pass=True) | G2+carry0.25 5.339 (DD 16.77/16.77, pass=True) | G2K20 5.690 (DD 17.80/17.72, pass=True) | G2K20+carry0.25 5.807 (DD 17.67/17.67, pass=True) // S3: G2 4.578 (DD 17.32/17.24, pass=False) | G2+carry0.25 4.717 (DD 17.18/17.18, pass=False) | G2K20 4.924 (DD 17.90/17.82, pass=False) | G2K20+carry0.25 5.056 (DD 17.77/17.77, pass=True) // S4: G2 4.898 (DD 17.31/17.24, pass=False) | G2+carry0.25 5.033 (DD 17.18/17.18, pass=True) | G2K20 5.320 (DD 17.95/17.86, pass=True) | G2K20+carry0.25 5.448 (DD 17.82/17.82, pass=True) // S5: G2 4.883 (DD 18.11/18.09, pass=False) | G2+carry0.25 5.016 (DD 17.98/17.98, pass=True) | G2K20 5.342 (DD 18.76/19.61, pass=True) | G2K20+carry0.25 5.465 (DD 18.63/19.72, pass=True)

S5 window from 2021-11-15 (G2K20): S5 monthly 5.611, DD 19.61, finalX 24.103; baseline same window: monthly 6.241, DD 17.69, finalX 34.089. S5 year 2021 is a short window (starts 2021-11-15).

