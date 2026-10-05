# context - market-wide state at the bar open for dip-rung sizing (pre-registered 2026-10-05, before any score)

## Hypothesis
Single per-coin state variables (funding, flow, positioning) were unstable year to year. The MARKET-WIDE state at the 4h bar open T,
computed across the 35 pooled coins, says whether dips revert (systemic sell-off vs idiosyncratic dip, vol expansion, breadth of the
damage, correlation regime) and improves the size multiplier of each majors R2 rung beyond the deployed size agent (`size_dep`).

## Causality
`build_market_features.py` builds the features from `research/tournament/data/hourly.parquet` using ONLY hourly bars whose hour ENDS at or
before T (bar start t <= T - 1h); the hour starting at T is never used. Every feature for (T, sym) is computed from the hourly panel sliced
to rows t <= T - 1h (loop over unique T; no centred / forward windows). An assert-based check truncates the hourly data to t < T for 20
random rows (each with its own T) and also at one random global cut, recomputes, and requires identical features. Data end < 2025-09-24.

## Features (all at T, from completed hours only)
Deployed-style bar-open state (7, from bar_open.parquet, same order as the deployed agent's x0..x6):
  bo_sp30, k (rung depth), bo_volreg, bo_trend, bo_btc_sp30, bo_dd24, hour.
Market-wide (equal-weight index of the coins with data; hourly log returns; vol = std of the index hourly returns):
  m_r4, m_r24, m_r72        index log return over 4 / 24 / 72 h divided by (vol_168h * sqrt(h))
  m_dd7                     index log distance to its 168h max divided by (vol_168h * sqrt(24))
  m_tr7                     index 168h log return divided by (vol_168h * sqrt(168))   (market trend)
  m_vts                     log(vol_24h / vol_168h)                                     (vol term structure)
  m_vlvl                    log(vol_168h / vol_720h)                                    (vol level vs 30 d)
  x_disp4, x_disp24         cross-sectional std of coin 4h / 24h log returns / median coin sigma over that horizon (coin hourly std 168h * sqrt(h))
  x_br2                     share of coins whose close is > 2 sigma_4h (hourly std 168h * 2) below their 24h high
  x_dn24                    share of coins with a negative 24h return
  x_corr72                  average pairwise correlation of hourly returns over the last 72 h (coins with a full window)
  btc_rel24                 BTC 24h log return minus the ex-BTC alt index 24h return, divided by (index vol_168h * sqrt(24))
Coin vs market (per row's coin):
  c_beta7                   OLS beta of coin hourly returns on the index over 168 h
  c_idio24, c_idio4         (coin return - beta * index return) over 24 / 4 h divided by (residual hourly std 168h * sqrt(h))
  c_corr72                  correlation of coin vs index hourly returns over 72 h
Minimum coin count for cross-sectional stats: 8 (else NaN; HGB handles NaN, V3 imputes training medians).

## Common protocol (fixed)
- Rows: harness.load(); bar-open features joined on the fills_U index (verified j / sym / r equal).
- Folds: harness.folds - train = any coin, any rung, t_exit < anchor - 7 d; test = majors R2 rungs of the year.
- Target: clip(y1.0, -0.10, 0.08) (the deployed agent's label); mu = mean target of the training rows of the fold.
- Cross-fit: two models per fold, trained on j % 2 == 0 and j % 2 == 1 training rows; both predict every test row.
- Rule (deployed): size 1.5 if both halves predict > 2 mu; 0.5 if both < 0; else 1.0. Scored with harness.score (equal exposure rescale).
- No hyper-parameter / threshold tuning; settings below are final.

## Variants (max 3)
- V1 `hgb_mkt`: HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, l2_regularization=1.0,
  random_state fixed) on the 7 deployed-style + all market / coin-vs-market features.
- V2 `hgb_mono`: V1 with monotonic constraints only where the sign is economically clear (chosen before looking at any relationship):
  m_tr7 +1 (dips revert in a rising market), bo_trend +1 (same, own coin), m_vts -1 (short-term vol expansion vs the sigma used to place
  rungs and stops makes rungs effectively shallower and stops easier to hit). All other features unconstrained.
- V3 `ens`: per half, average of (a) the V1 HGB, (b) ExtraTreesRegressor(n_estimators=200, min_samples_leaf=200, max_features=0.5,
  random_state fixed) on training-median-imputed features, (c) Ridge(alpha=10) on training-standardised, median-imputed features.
  Same rule on the averaged predictions.
- Reference R0 (NOT a candidate, cannot graduate, reported only to attribute the effect of the market features): V1's model on the 7
  deployed-style bar-open features only.

## Reporting
score_<variant>.json per variant (harness.score), per-year gain vs deployed, size-y IC and prediction-y IC on test rows, worst-day tails,
graduation flag; permutation importance (MSE increase, 3 repeats, 15k sampled TRAINING rows of the 2024 fold, in-sample per half) for the
2024-fold models. Resources: one process, < 2.5 GB RAM, < 60 min.
