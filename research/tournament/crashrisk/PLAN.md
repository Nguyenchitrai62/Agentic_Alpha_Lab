# crashrisk - market-state crash-risk dial for the BOT R2-4P (pre-registered 2026-10-05, written before any score)

## Hypothesis
The market-wide state at a bar open T (index trend / drawdown, vol term structure, crash breadth, dispersion, correlation, BTC vs
alts) predicts the risk of a large drop of the 5-majors index over the NEXT 24 h. Scaling the whole BOT portfolio by a multiplier
m(T) in [0.5, 1] when predicted risk is high cuts the drawdown more than the return.

## Data and causality
- Input: research/tournament/data/hourly.parquet (hour-start t, OHLC), rows t < 2025-09-24 only. Nothing at/after 2025-09-24 is read.
- Panel: every whole hour T. A feature at T uses ONLY hourly bars with t <= T - 1h (bars that ENDED at or before T), sampled at
  t = T - 1h; all windows backward-looking. Assert test: truncate hourly to t < T for 20 random T (+ one global cut on 500 rows),
  recompute, require identical features (|diff| < 1e-9, same NaN pattern).
- Features (17): the 13 market-wide columns of research/tournament/context/build_market_features.py (35-coin equal-weight index;
  definitions ported verbatim): m_r4, m_r24, m_r72, m_dd7, m_tr7, m_vts, m_vlvl, x_disp4, x_disp24, x_br2, x_dn24, x_corr72,
  btc_rel24; plus 4 on the 5-majors index J (hourly log return = mean of available majors' hourly log returns, >= 4 coins):
  j_r24 = 24h J return / (J vol168 * sqrt 24), j_dd7 = (J - 168h max J) / (J vol168 * sqrt 24), j_vts = log(J vol24 / J vol168),
  j_vlvl = log(J vol168 / J vol720).

## Labels (at T; horizon (T, T + 24h] = hourly bars starting T .. T + 23h)
- Reference price: each major's close of the bar starting T - 1h (known at T). Majors used = those with that close and all 24
  forward bars (>= 4 required, else NaN).
- sigma_24h(T) = std of J's hourly log returns over bars t in [T - 168h, T - 1h] (>= 144 obs) * sqrt(24)  (data before T only).
- Path: C_k = mean_c log(close_{c,k} / ref_c), L_k = mean_c log(low_{c,k} / ref_c) for k = T .. T + 23h (equal-weight buy-and-hold
  in log terms, coin lows treated as simultaneous within the hour -> slightly conservative).
- crash24 = 1 if min_k L_k <= -2.5 * sigma_24h(T).
- mdd24 (regression) = max_k [ max(0, max_{j<k} C_j) - L_k ] / sigma_24h(T)  (forward 24h max drawdown in sigma units, peak from closes).
- Labels needing bars at/after 2025-09-24 are NaN (dropped). Base rates reported overall and per year.

## Walk-forward
Anchors A = 2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24; test = T in [A, A + 365 d). Training rows: T + 24h < A - 7 d (stricter
than the 2-day label embargo; satisfies the tournament rule t_exit < A - 7 d). Expanding window from the first valid hour.

## Models (fixed, no tuning)
- HGB classifier on crash24: HistGradientBoostingClassifier(max_depth=3, min_samples_leaf=200, learning_rate=0.05, max_iter=200,
  l2_regularization=1.0, early_stopping=False, random_state=0).
- HGB regressor on mdd24: HistGradientBoostingRegressor, same settings.
- Logistic baseline on crash24: training-median imputation, training standardisation, LogisticRegression(C=1.0, max_iter=2000).

## Score (a): AUC (crash24) and Spearman IC (vs mdd24) per test year for all three models (logistic and HGB-clf probabilities, HGB-reg
prediction). Also the 2.5-sigma label hit rate in the top predicted-risk decile vs base rate.

## Dial variants (max 3; thresholds from TRAINING data only)
Thresholds = percentiles of OUT-OF-FOLD predictions on the training rows (5 contiguous chronological blocks, the model of each block
trained on the other blocks minus a 7-day purge on each side of the block), so the cut-offs reflect out-of-sample score levels.
m = 1 below q_lo, 0.5 above q_hi, linear between.
- D1 `clf_80_95`: HGB classifier probability, q_lo = 80th, q_hi = 95th percentile.
- D2 `clf_90_99`: HGB classifier probability, q_lo = 90th, q_hi = 99th (only extreme states).
- D3 `reg_80_95`: HGB regressor predicted mdd24, q_lo = 80th, q_hi = 95th.
Reference rows (not candidates): undialled R2 / R2K; and `flat_same_mean` = constant multiplier equal to the variant's mean m over
the 4 dev years (separates timing skill from just holding less exposure; it uses the realised test-period mean, so it is a reference
only).

## Score (b): portfolio screen (approximation)
v391_runs.pkl, runs R2 and R2K, phases s = 0..3. Bar end t, bar start t - 4h; m from features at the bar start T = t - 4h (fold model of
T's anchor year). r'_t = m * r_t, eq'_t = eq'_{t-1} (1 + r'_t), eq_min'_t = eq'_{t-1} (1 + m (eq_min_t / eq_{t-1} - 1)). Phases
combined as the 1/4-capital mix of hourly forward-filled equity (v388 hourly()/mix()); per dev year geometric %/month, worst year,
conservative DD (per-year, max of eq_min vs running peak, max over years, as v388 year_stats) and also the full 4-year path DD.
Caveat: ignores path effects (sizing / governor / risk budget react to equity), fills, and cost of resizing.

## Step 4 rule (fixed)
A variant passes if the 4-year max DD (v388 definition) falls by >= 2.0 points AND either R2K dialled dev4 >= 5.0 %/month or R2 dialled
dev4 >= 90 % of undialled R2 dev4 (the DD drop must hold for the same run that meets the return condition). If any passes, write
tables/riskmult_s{s}.parquet (T = every 4h bar start of phase s from 2021-09-24 + s h to 2025-09-24 08:00 + s h, mult) for the passing
variant with the best DD drop; bars with T >= 2025-09-24 need data at/after the cut and get the neutral m = 1.0 (reported).
Resources: one process, < 2.5 GB RAM, < 60 min.
