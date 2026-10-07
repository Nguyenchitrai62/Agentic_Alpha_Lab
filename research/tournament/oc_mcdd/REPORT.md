# oc_mcdd — deployment-risk report (informational, no verdict rule)

Deployment pick **R2B1D17BF** vs reference **R2B1D16**: distribution of the
12-month return and max drawdown from a stationary block bootstrap over the
five walk-forward years 2021-09-24..2026-09-23. Method per PLAN.md.

## How the daily series was built
Daily mixed close equity = mean of the four phase sub-account equities after
resetting each phase to 1/4 of capital at each anchor (chained multiplicatively
year to year; causal ffill, 00:00 UTC marks). Daily marked low = same weighting
applied to each phase's intrabar low. Bootstrap: Politis-Romano stationary,
mean block 20 days, 10000 paths x 365 days, seed 0, circular wrapping.
Primary DD = marked (running peak of close vs min of close/low); close-only DD
as secondary row. Empirical year table uses the exact hourly `reset_metric`
replica, so it matches `v411_result.json` to the printed digit.

## Empirical per historic year (reset metric, %)
| year (anchor) | R2B1D17BF m%/mo | DD% | R2B1D16 m%/mo | DD% |
|---|---|---|---|---|
| 2021-09-24 | 2.831 | 12.42 | 2.012 | 15.16 |
| 2022-09-24 | 3.505 | 16.23 | 3.716 | 16.12 |
| 2023-09-24 | 4.669 | 18.33 | 4.522 | 17.33 |
| 2024-09-24 | 11.270 | 8.26 | 10.788 | 7.85 |
| 2025-09-24 | 5.060 | 12.81 | 4.853 | 12.68 |

## Bootstrap 12-month distribution (10000 paths, %)
| metric | R2B1D17BF | R2B1D16 |
|---|---|---|
| P(12m net < 0) | 0.7 | 1.3 |
| P(monthly geo < 5%) | 47.8 | 52.1 |
| monthly geo median / p5 / p95 | 5.12 / 1.47 / 10.32 | 4.87 / 1.12 / 10.15 |
| 12m net median / p5 / p95 | 82.0 / 19.1 / 224.9 | 77.0 / 14.3 / 219.0 |
| P(marked maxDD > 15 / 20 / 25%) | 42.2 / 11.0 / 2.1 | 55.1 / 14.3 / 3.2 |
| marked maxDD median / p95 | 14.47 / 22.57 | 15.01 / 23.77 |
| close-only maxDD median; P(> 20%) | 11.95; 5.7 | 13.76; 8.0 |

## Reading
- A random 12-month bootstrap year loses money only ~0.7% of the time (BF),
  but monthly geo clears 5% in only ~52% of resampled years: the 5%/mo gate
  pace sits almost exactly at the bootstrap median (5.12%), so year-to-year
  outcomes straddle the gate even though all five realised years were positive.
- Drawdown: median resampled marked maxDD 14.5% (BF); ~11% of paths breach
  20% and ~2% breach 25%. The realised worst year (18.3%) sits near the
  bootstrap p90. R2B1D16 is worse on every DD cut (median 15.0%, P(>20%) 14.3%).
- Caveats: bootstrap assumes roughly stationary daily returns and preserves
  only ~20-day dependence — it does not reproduce annual regime structure
  (the 2024-25 +11.3%/mo year vs the +2.8%/mo 2021-22 year); the empirical
  table above is the guardrail for that. Daily sampling understates true
  1m-marked DD; realised full-path DD (16.9 BF) remains the gate number.

Informational one-liner: the bootstrap says R2B1D17BF's edge clears 0 in ~99%
of resampled years but clears 5%/mo only about half the time, with ~1-in-9
resampled years breaching 20% marked DD — for the deployment doc, not a verdict.
