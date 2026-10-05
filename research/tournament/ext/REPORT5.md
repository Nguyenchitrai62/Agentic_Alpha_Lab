# Tournament5: 5-fold re-score of the existing ideas on the extended year

Inputs (all under `research/tournament/ext/`, market data <= 2026-09-24 00:00 UTC, nothing later):
- `fills_U_ext.parquet` (72130 rows, t_fill max 2026-09-23 18:40; rows < 2025-09-17 identical to `fills_U.parquet`, `fills_check.json` max_abs 0.0).
- `prep_features_ext.py` run to completion: 35/35 coins, `bar_open_ext.parquet` (72130x20) + `hourly_ext.parquet` (1820834 rows, t_max 2026-09-23 23:00, early enders EOS/SXP/YFII).
  Overlap (`features_check.json`): bar_open max_abs 0.0 every column (0 rows missing), hourly OHLC maxdiff 0.0 (0 rows missing).
  Causality: 20 random rows recomputed from 1m arrays truncated at the bar's minute-0 close (kk = 240j) identical, max_abs 0.0.
- `build_market_features_ext.py` (copy of context logic, only input/output paths changed; diff verified): `market_features_ext.parquet`
  (72130x19), overlap with `market_features.parquet` max_abs 0.0, causality 20 per-row truncations + global cut passed (max 4.6e-15).
- `harness5.py`: 5 folds anchors 2021-09-24..2025-09-24, TABLE v376 `r2_table_s0.parquet`, graduation gain > 0 in >= 4/5 years AND total > 0
  AND worst day not > 20% worse; `score_tp` same formula as `harness.score_tp`. Sanity: deployed scores 0.0, flat size loses every year.

Method: one thin wrapper per idea in ext/ reusing the original functions with NO parameter changes, models refit per fold exactly as the
original scripts do (`score_kelly5.py`, `score_context5.py`, `score_tp5.py`). Overlap assert on the first 4 folds vs the original scored
sizes/decisions for rows with t_fill < 2025-09-24: kelly 4354/4354 (worst diff 0.0), context 4354/4354 exact (old gains reproduced first),
tp 4354/4354 exact; first-4-year gains reproduce the original score JSONs to 4dp in all three cases.

| idea (variant) | 2021-22 | 2022-23 | 2023-24 | 2024-25 | 2025-26 (new) | total | graduates (4/5 rule) |
|---|---|---|---|---|---|---|---|
| kelly V2 meanvar | +1.0937 | +1.8837 | +0.6903 | +1.0525 | -1.4546 | +3.2656 | true (4/5, worst -1.719 vs dep -1.9145) |
| context V2 hgb_mono | +0.3457 | +0.0404 | +0.0568 | +0.2593 | -0.6799 | +0.0223 | true (4/5, worst -1.2291 vs dep -1.9145) |
| tp V2 diff | -0.2366 | +0.0926 | +0.8230 | +0.0698 | +0.0905 | +0.8392 | true (4/5, worst -0.9493 vs dep -1.9145) |

Caveats: kelly and context both lose the new 2025-26 fold yet still graduate under the 4-of-5 rule (context's total is +0.02, i.e. no margin);
only tp is positive in 2025-26. `bar_open_identical_first_rows=false` in the check is benign (new rows interleave chronologically; the
keyed sym/j/r merge shows 0.0 diff on all old rows). Tests: `tests/test_tournament5.py` (7 passed: causality + alignment).

Kelly V2 meanvar graduates on 4/5 years but loses the new 2025-26 fold (-1.45).
Context V2 hgb_mono graduates on 4/5 years but its edge nearly vanishes (total +0.02) after losing 2025-26 (-0.68).
TP V2 diff is the only idea positive in the new 2025-26 fold (+0.09) and graduates with the most balanced 5-year profile.
