# kelly - distributional / risk-adjusted rung sizing (pre-registered 2026-10-05, before any score)

## Hypothesis
Dip-rung net returns are fat-tailed (many small take-profit wins, rare large stop losses). The deployed size agent (size_dep) thresholds a
predicted MEAN. A distributional model (quantiles, stop probability, outcome buckets) plus a continuous risk-adjusted size
(Kelly / mean-variance: size proportional to predicted mean / predicted (downside) variance, clipped) should beat it at equal exposure
(harness.score rescales every year to the deployed mean size).

## Data, label, folds
- Rows: `harness.load()` (35 coins pooled for training; test = majors R2 rungs with a deployed size, via `harness.folds`).
- Label: `y_dep` (net return at the deployed TP; alt / pre-2021 rows fall back to TP 1.0 as in the harness).
- Train rows of the year with anchor A: `t_exit < A - 7 d` (harness mask). Nothing from a test year feeds any fit, scale or threshold.
- Join of `data/bar_open.parquet`: on the unique key (j, sym, r) (harness.load resets the index after a merge, so a key join is used and
  checked: every row must match, no duplicates).

## Features (bar-open only; no fill-time x0, x2..x6)
- The 17 bar-open features of `bar_open.parquet`: bo_sp30, bo_volreg, bo_trend, bo_btc_sp30, bo_dd24, hour, r1h, r4h, r24h, r72h, rng24,
  dd7, du7, rv24, btc_r4h, btc_r24h, btc_dd24.
- `k` (rung depth, known at placement) and `tp` (= tp_dep, the deployed TP fixed at placement; 1.0 where missing).
- `lsig` = log of a volatility proxy `sig` = 2 x std of hourly log returns over the 168 hourly closes ending at T (hours starting <= T - 1 h,
  i.e. closed by T; from `data/hourly.parquet`). Needed because the label is in return units while every other feature is sigma-scaled.
  `sig` also defines the stop event below. NaN where < 48 hourly returns exist (HGB handles NaN; a NaN sig falls back to the training median
  in the formulas).

## Model settings (fixed, all variants)
sklearn HistGradientBoosting{Regressor,Classifier}: max_depth 3, learning_rate 0.05, max_iter 300, min_samples_leaf 200, no early stopping,
random_state 0. Cross-fitting on (j % 2) halves of the training rows: model A on even j, model B on odd j; training rows get the
out-of-fold prediction of the other half (used only for the residual model of V2 and for the size scale); test rows get the mean of A and B.
Size scale: `size = clip(c * raw, 0, 2)` with `raw = max(mu, 0) / V`; c is solved (bisection) so the mean size over the TRAINING rows'
out-of-fold predictions equals 1. Zero size = the rung is skipped.
Stop event: `y_dep < -2 * sig` (a loss larger than two sigma_4h-equivalents; the engine's stop sits 4 sigma below the fill).

## Variants (max 3, each scored once)
- **V1 quantile_kelly**: three quantile HGBs (q = 0.1, 0.5, 0.9) + a stop-probability HGB classifier (stop event above).
  mu = 0.3 q10 + 0.4 q50 + 0.3 q90 (Swanson 3-point mean). V = (max(q50 - q10, 0))^2 + p_stop * L^2 with
  L = sig * m_stop, m_stop = training mean of y_dep / sig over stop rows. raw = max(mu, 0) / V.
- **V2 meanvar**: mean HGB (squared error); out-of-fold residuals e on the training rows; second HGB fits |e| on the same features;
  sd = sqrt(pi / 2) * max(|e|_hat, 1e-4); V = sd^2; raw = max(mu, 0) / V.
- **V3 bucket_ev**: 3-class HGB classifier: win (y_dep > 0), small loss (-2 sig <= y_dep <= 0), stop (y_dep < -2 sig).
  Bucket moments in sigma units m1[c, tp], m2[c, tp] = training mean of y/sig and (y/sig)^2 per bucket and tp level (fallback to the
  bucket's all-tp moment if a (c, tp) cell has < 50 rows). mu = sig * sum p_c m1; E2 = sig^2 * sum p_c m2; V = max(E2 - mu^2, 1e-8);
  raw = max(mu, 0) / V.

## Reporting
harness.score per variant (equal exposure) -> `score_<variant>.json`; REPORT.md with per-year gain vs the deployed agent, IC (size vs y),
worst-day tails, graduation flags, plus non-scored diagnostics (Spearman IC of mu on test, share of skipped rungs). Single run, one process.
