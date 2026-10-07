# oc_idiocap REPORT — idiosyncratic caps on n = 0 dip rungs (2026-10-05; PLAN pre-registered before any outcome)

## Setup
Majors R2 rungs (`x1` in {2.5,3.0,3.5,4.0,5.0}) from `ext/fills_U_ext.parquet`
joined 1-1 to `oc_b1shape/fills_n.parquet` on (sym, t_fill, x1 = k), 5498 fills
in 5y. `T = t_fill - f`; years Y0..Y4 = [anchor, anchor + 365d) for anchors
2021-09-24..2025-09-24 keyed by `T`; outcome `y1.0` (net, fees/funding in).
B0 `plain` w = 1/(1+n); C1 `idio05` x0.5 and C3 `idio07` x0.7 ONLY when n = 0
AND x4 > -1 AND x0 < -4 (fill-minute f - 1 state, causal); C2 skipped (needs 1m
closes; LIGHT no-1m job, per assignment). Equal exposure per year (mean w'=1);
daily sums by T.floor('D'). Repro: `{PLAN.md,score_idiocap.py,results.json}`.

## Trigger rarity (the cap almost never fires)
| year | fills | n=0 | capped (C1/C3) | share of n=0 |
|---|---|---|---|---|
| 2021-09-24 | 990 | ~422 | 3 | 0.7% |
| 2022-09-24 | 1045 | ~515 | 12 | 2.3% |
| 2023-09-24 | 1330 | ~659 | 12 | 1.8% |
| 2024-09-24 | 989 | ~460 | 2 | 0.4% |
| 2025-09-24 | 1144 | ~443 | 0 | 0.0% |
| 5y | 5498 | ~2499 | 29 | 1.2% of n=0, 0.53% of all |

## Yearly sum S = sum(w' * y1.0)
| variant | 2021 | 2022 | 2023 | 2024 | 2025 | keep >=95% |
|---|---|---|---|---|---|---|
| B0 plain | 3.955 | 0.291 | 5.737 | 3.952 | 1.237 | — |
| C1 x0.5 | 3.976 | 0.220 | 5.712 | 3.970 | 1.237 | 4/5 (2022: 76%) |
| C3 x0.7 | 3.967 | 0.248 | 5.722 | 3.963 | 1.237 | 4/5 (2022: 86%) |

## Worst-day per year (higher = shallower)
| variant | 2021 | 2022 | 2023 | 2024 | 2025 | improved |
|---|---|---|---|---|---|---|
| B0 plain | -0.713 | -1.081 | -0.398 | -0.331 | -0.903 | — |
| C1 x0.5 | -0.715 | -1.090 | -0.401 | -0.332 | -0.903 | 0/5 |
| C3 x0.7 | -0.714 | -1.087 | -0.400 | -0.332 | -0.903 | 0/5 |

## Per-year maxDD of daily sums (higher = shallower)
| variant | 2021 | 2022 | 2023 | 2024 | 2025 | improved |
|---|---|---|---|---|---|---|
| B0 plain | -0.713 | -1.698 | -0.403 | -0.331 | -1.130 | — |
| C1 x0.5 | -0.715 | -1.743 | -0.401 | -0.332 | -1.130 | 1/5 (2023 only) |
| C3 x0.7 | -0.714 | -1.725 | -0.400 | -0.332 | -1.130 | 1/5 (2023 only) |

## Overall tails (reference)
| variant | worst-day | full-path maxDD |
|---|---|---|
| B0 plain | -1.081 | -1.698 |
| C1 x0.5 | -1.090 | -1.743 |
| C3 x0.7 | -1.087 | -1.725 |

## Decision
C1: wd 0/5, dd 1/5, keep95 4/5 -> NOT PROMISING. C3: wd 0/5, dd 1/5, keep95
4/5 -> NOT PROMISING. LOYO passes 0/5 both. The x4 > -1 & x0 < -4 iso-crash
fires on 29/5498 rungs (0 in the most recent year); under equal exposure the
rescale-up of everything else slightly deepens tails, and 2022's sum drops
below 95%. Close direction.

## Verdict
VERDICT: NOT PROMISING — neither idiosyncratic cap improves worst-day in any year or per-year maxDD beyond 1/5 years, so the n = 0 iso-crash cap is rejected.
