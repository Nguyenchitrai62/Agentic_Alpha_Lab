# tp - take-profit choice as a full-information contextual bandit (pre-registered 2026-10-05, before any score)

## Hypothesis
The deployed TP agent (v321 R2: per-action HGB regressors trained on FILL-time state x0..x6 but applied to bar-open state, two
cross-fitted halves, deviate from 1.0 sigma only if both halves agree on a gain > 0.001) under-uses the information in the exact
counterfactual outcomes y0.5 / y1.0 / y1.5. A learner trained directly on the choice, with bar-open features that match the decision time,
beats the deployed TP at fixed deployed sizes (`harness.score_tp`, sizes = size_dep).

## Data / protocol (fixed)
- Rows: `harness.load()`; features joined from `research/tournament/data/bar_open.parquet` (same row order as fills_U after the
  `t_fill < 2025-09-24` filter; the join is asserted on j / sym / r).
- Folds: `harness.folds` (train = any of 35 coins, all rungs 2.0..5.0, `t_exit < anchor - 7 d`; test = majors R2 rows of the year).
- Features (bar-open, known at T + 1 min): bo_sp30, bo_volreg, bo_trend, bo_btc_sp30, bo_dd24, hour, r1h, r4h, r24h, r72h, rng24, dd7,
  du7, rv24, btc_r4h, btc_r24h, btc_dd24 + rung depth k (= x1). 18 features.
- Labels: y0.5 / y1.0 / y1.5 clipped to [-0.10, 0.08] (the deployed convention).
- Inner validation (V2 margin, V3 early stopping): inside the training rows of each fold, inner-val = the last 25 % of the training rows by
  T; inner-train = training rows with `t_exit < (first inner-val T) - 7 d`. Inner-val is scored on all coins, size 1. After a choice the
  final model is refit on all training rows of the fold (V2) / the inner-train models are used (V3, early stopping needs the val split).
- HGB settings for all HGB variants: max_depth 3, learning_rate 0.05, max_iter 300, min_samples_leaf 200, l2_regularization 1.0,
  random_state 0, no early stopping.

## Variants (each scored ONCE with harness.score_tp)
- **V1 `v1_cls`**: label = argmax_a y_a (ties -> 1.0; ~27 % of rows have all three equal = stop/backstop exits). HistGradientBoostingClassifier
  with sample weight = max_a y_a - min_a y_a (cost of a wrong action; zero-spread rows drop out). Per-class outcome table M[c, a] = mean
  clipped y_a over the fit rows with label c. Decision = argmax_a sum_c p(c|x) M[c, a].
- **V2 `v2_diff`**: two HGB regressors for D05 = y0.5 - y1.0 and D15 = y1.5 - y1.0 (clipped labels). Deviate to the action with the larger
  predicted difference only if it exceeds a margin m; m chosen from {0, 0.0005, 0.001, 0.002, 0.003, +inf} by the inner validation
  (maximise the sum of realised gains vs 1.0 on inner-val; ties -> larger m), then both regressors are refit on all training rows.
- **V3 `v3_mlp`**: torch MLP (CPU) 18 -> 64 -> 64 -> 3 (ReLU, dropout 0.1), softmax policy trained to maximise the exact expected reward
  sum_a pi(a|x) (y_a - y1.0) / 0.01 (full-information policy gradient). Features: median-imputed + standardised with inner-train
  statistics. Adam lr 1e-3, weight decay 1e-4, batch 512, max 60 epochs, early stopping on the inner-val expected reward (patience 8).
  5 seeds, probabilities averaged, decision = argmax.
- **Extra `v4_bot_only` (labelled bot_only)**: the V2 learner with the fill-time state x0, x2..x6 added (a bot could amend the TP at the
  fill). Not eligible for the manual product; reported separately.

## References (no selection, reported for context only)
deployed (gain 0 by construction), constant 1.0, constant 1.5, the per-row oracle (upper bound).

## Graduation
harness rule: gain > 0 in >= 3 of 4 years AND total gain > 0 AND worst-day not > 20 % worse than deployed. Nothing is tuned on test years.
