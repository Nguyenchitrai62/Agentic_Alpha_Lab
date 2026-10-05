# context - market-wide state at the bar open for dip-rung sizing (REPORT, 2026-10-05)

Pre-registration: `PLAN.md` (written before any score). Scripts: `build_market_features.py` (features + causality asserts),
`run_variants.py` (the 3 variants + reference R0, each scored once), `diag_robustness.py` (disclosed post-score seed diagnostic, no
selection). Logs: `build.log`, `run.log`. Outputs: `market_features.parquet`, `score_<variant>.json`, `diag_robustness.json`.

## Leakage / causality
- Market features use only hourly bars with start t <= T - 1h (the hour starting at T is never read); all windows backward-looking.
- Assert check: hourly data truncated to t < T for 20 random rows (own T each) + one global random cut (500 rows): features identical,
  max |diff| = 0.0 (bit-identical).
- bar_open.parquet joined on the fills_U index (rows < 2025-09-24), j / sym / r asserted equal; bar_open hour == T hour asserted.
- Training rows per fold = harness.folds (t_exit < anchor - 7 d); mu, imputation medians, standardisation from training rows only.
  No data >= 2025-09-24 touched. HGB early stopping ('auto', as in the deployed agent) uses a random 10 % holdout of training rows only.

## Results (gain = S_new - S_dep at equal exposure, harness.score; deployed S_dep per year 4.485 / 0.924 / 6.627 / 4.265, sum 16.30)

| variant | 2021-22 | 2022-23 | 2023-24 | 2024-25 | total | years > 0 | worst day (dep -1.915) | graduates |
|---|---|---|---|---|---|---|---|---|
| V1 hgb_mkt  | +0.288 | -0.046 | +0.085 | +0.257 | **+0.585** | 3/4 | -1.792 | True |
| V2 hgb_mono | +0.346 | +0.040 | +0.057 | +0.259 | **+0.702** | 4/4 | -1.812 | True |
| V3 ens      | +0.184 | -0.393 | +0.108 | +0.352 | +0.251 | 3/4 | -2.223 | True (tail ratio 1.16 < 1.2) |
| R0 base7 (reference, not a candidate) | +0.075 | -0.253 | +0.355 | +0.161 | +0.339 | 3/4 | -2.141 | (True) |

Size-vs-y Spearman IC on test rows (new size / deployed size): V1 0.179/0.019, 0.171/0.086, 0.136/0.073, 0.127/0.022;
V2 0.184, 0.165, 0.110, 0.132; V3 0.095, 0.140, 0.122, 0.189; R0 0.093, 0.088, 0.134, 0.094.
Continuous prediction IC vs y_dep: V1 0.20 / 0.22 / 0.20 / 0.16, V2 0.19 / 0.21 / 0.18 / 0.23 (part of this is magnitude: raw net
returns scale with sigma, so vol-state features rank |y|; it is not a pure direction skill).
Share sized up / down (V1): 34/1 %, 24/1 %, 39/0.5 %, 27/2 %; deployed 22/4 %, 4/14 %, 20/6 %, 11/13 %. The new rule almost never sizes
down - nearly all the gain comes from choosing which rungs to size up.

Per-year worst-day tails (dep -> new): V1 2021 -0.434 -> -0.575 (32 % worse), 2022 -1.915 -> -1.792, 2023 -0.577 -> -0.503, 2024 -0.703
-> -0.566. V2 2021 -0.434 -> -0.601 (38 % worse), others better. The graduation rule uses the worst day over all years (2022), so the 2021
tail deterioration does not block graduation, but it should be watched in the engine test.

Market features vs the same model on the 7 bar-open features only (V - R0): V1 +0.21 / +0.21 / -0.27 / +0.10; V2 +0.27 / +0.29 / -0.30 /
+0.10 (3 of 4 years positive; 2023-24 is the year R0 does best). So roughly half of V1/V2's gain over the deployed agent comes from the
market state, the rest from the bar-open refit itself (R0 also passes the rule, weakly).

## Seed diagnostic (disclosed, post-score, not used for selection)
HGB early stopping makes the 2022+ folds seed-dependent (2021 fold < 10k rows per half -> no early stopping -> identical). 5 extra seeds:
- V1 totals 0.69 / 0.66 / 0.68 / 0.66 / 0.76, all graduate; 2022 gain ranges -0.04..+0.21, 2023 -0.04..+0.13.
- V2 totals 0.85 / 0.74 / 0.57 / 0.82 / 0.84, all graduate; 2022 +0.01..+0.12, 2023 -0.11..+0.18.
The total is robust (~+0.6..+0.85 = +4..5 % of deployed S); the middle two years are near zero and sign-unstable - the gain is carried by
2021-22 and 2024-25.

## Permutation importance (2024 fold models, 15k sampled TRAINING rows per half, in-sample, MSE increase)
- V1: m_r4, x_br2, m_r24, k, bo_volreg, m_r72, bo_btc_sp30, x_disp24.
- V2: m_r4, x_br2, k, m_r24, x_corr72, m_r72, bo_btc_sp30, bo_volreg.
- V3: m_r4, m_r24, m_tr7, x_br2, m_r72, x_corr72, k, m_dd7.
- R0: bo_btc_sp30 dominates (~4x the next), then bo_volreg, k.
The market's own recent move (4h / 24h / 72h index return in vol units) and crash breadth (share of coins > 2 sigma below their 24h high)
replace BTC's minute-0 speed as the main driver - consistent with the hypothesis that market-wide state, not the coin's own state, decides
whether a dip reverts. Coin-vs-market features (beta, idiosyncratic move) rank low.

## Verdict
V2 hgb_mono (+0.70, 4/4 years, tail better than deployed) and V1 hgb_mkt (+0.59, 3/4) graduate under the harness rule; V3 graduates only
narrowly (one bad year -0.39, worse tail). Recommended for a registered engine test: V2 (pre-registered, best and most uniform, monotone
constraints make it simpler). Caveats: (1) effect size is modest (~4 % of deployed S) and 2022-23 / 2023-24 gains are within seed noise;
(2) 2021 worst day is ~35 % worse than deployed; (3) the rule rarely sizes down, so it adds risk on more rungs before the equal-exposure
rescale - the engine test (sleeve risk budget, DD) must confirm; (4) it replaces a fill-time agent with a bar-open one - a combination
(fill-time x0..x6 + market state, `bot_only`) is the natural follow-up but was not part of this registration.

## Engine tables for V2 hgb_mono (leader request, 2026-10-05)
`build_engine_tables.py` -> `tables/ctx_v2_s{0..3}.parquet` (T, sym, rung 0..4, size), audit features `tables/ctx_v2_feat_s*.parquet`,
`tables/check.json`, log `tables_build.log`. Models = the scored V2 (same rows / seeds / mu), verified by re-scoring the reproduced
test sizes: identical to score_hgb_mono.json. 1m data read with a pyarrow filter open_time < 2025-09-24 (nothing at/after the cut loaded).
- Check 1 (s = 0 vs scored): 4354 / 4354 scored majors test rows matched, size max |diff| 0.0, match share 1.000; all 23 features
  bit-identical to the scored inputs (0 NaN mismatches).
- Check 2: each phase 219,225 rows (43,845 bars x 5 rungs), keys identical to research/diagnostics/phase_agents/tables/r2_table_s{s}.
  Size counts 0.5 / 1.0 / 1.5: s0 1422 / 123455 / 94348; s1 1495 / 123682 / 94048; s2 1540 / 122500 / 95185; s3 1554 / 122618 / 95053.
  75 rows per phase (T = 2025-09-24 00:00..08:00 + s h, 3 bars x 5 coins x 5 rungs) need minute-0 data at/after the cut -> neutral 1.0.
  Note: over ALL bars ~43 % of rungs are sized up (on filled rungs 22-39 %) - the rule sizes up often; the engine's risk budget matters.
- Check 3 (causality): 20 random (phase, T, sym) recomputed from 1m data truncated at T + 1 min (minute 0 kept) on the shifted grid and
  hourly data truncated to t < T: all 23 features identical (max |diff| 0.0).
