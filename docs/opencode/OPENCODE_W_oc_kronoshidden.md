# OpenCode task oc_kronoshidden - Kronos dip tilt on G2, clean test on post-release data
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_kronoshidden/` and `tests/test_oc_kronoshidden.py`.

## Why
research/tournament/kronos (read PLAN.md and REPORT.md fully) found that the zero-shot Kronos-small forecast `low1` (expected depth of the
next 4h bar's low, in sigma units) tilts dip-rung outcomes: rule V1 (size x1.5 / x0.5 on the outer quintiles) graduated with +2.52 over
the four dev years. Caveat: Kronos was released 2025-08 and pretrained on exchange candles up to ~mid 2025, so the dev years are probably
IN its training data. The most recent year 2025-09-24 .. 2026-09-23 and anything later are AFTER its release -> the first clean test.
Nobody has used Kronos on that year yet, so it can be scored once.

## Part A - features (no outcomes; GPU through heavy_slot)
1. Reuse research/tournament/kronos (model/, kronos_fast.py, build_bars.py, run_inference.py) with IDENTICAL settings: Kronos-small +
   Kronos-Tokenizer-base (weights already in that folder or the HF cache - do not re-download if present), context 400 x 4h bars, pred_len 6,
   S = 64 paths, T = 1.0, top_p = 0.9, top_k = 0, torch seed 1234, fp32, per-window z-normalisation + clip 5. Copy code into your folder;
   do not edit research/tournament/kronos.
2. Build 4h OHLCV bars for BTC/ETH/SOL/BNB/XRP from raw Binance USD-M 1m klines for FOUR clock grids: shift s = 0, 1, 2, 3 hours (bar opens
   at s, s+4, s+8, ... UTC), from 2020-08-01 to the last complete 4h bar available locally. Find the 1m sources (data/raw/majors_intraday_20260924,
   data/raw/btc_intraday_20260924, data/raw/btc_1m_hidden_20260924, data/raw/majors_1m_oos_20261006, data/raw/binance_usdm ...) and list
   which file covers which period; check there is no gap/duplicate at the junctions (report any).
3. Compute the 8 Kronos features of kronos/PLAN.md (er1, er6, vol1, vol6, rng1, low1, pdrop2, pdrop3 + sigma, C0) for every bar open T of
   every shift. Shift 0 dev features already exist (`research/tournament/kronos/kronos_4h_features.parquet`): recompute shift 0 on the overlap
   2025-06-01 .. 2025-09-23 and report Spearman / median abs difference of low1 vs the stored file (sampling noise expected; Spearman should
   be > 0.9). Save `kronos_features_4shift.parquet` (sym, shift, T, features). Expected cost: ~4 x 55k forecasts, ~2-3 h on the GTX1650.

## Part B - engine (4-phase, heavy_slot)
1. Copy the mechanism of research/parallel/rounds/parallel-20260906-r2/v414/v414_dvol_tilt.py (a per-(coin, holding bar) dip-size multiplier
   applied on top of the corr-aware dip sizes; budget unchanged) and run it on top of the G2 reference RUNS entry of v421
   (`rule="inv", k=1.0, kd=1.7, bear=True, G=2.0`). The reference row must reproduce v421 G2 exactly (5.41 / 16.91 / 16.82); else stop.
2. Variants (fixed):
   - REF = G2 unchanged.
   - K1 = V1 rule of kronos/PLAN.md: risk = -low1. For each anchor A, fit on TRAINING rows = majors rows of `research/tournament/harness.py`
     `load()` with t_exit < A - 7 d and the Kronos feature present (shift-0 features joined on (sym, T)): direction = sign of
     Spearman(risk, y_dep); edges q20 / q80 of risk. Multiplier 1.5 in the favourable outer quintile, 0.5 in the unfavourable outer quintile,
     1 otherwise; missing feature -> 1. The fitted (direction, edges) of anchor A are applied to all four clock shifts in year A (features are
     in sigma units, comparable across shifts). For the most recent year the training rows are all harness rows with t_exit < 2025-09-17.
   - K2 = K1 with 1.25 / 0.75.
   - CTRL (exposure-matched control, methodology lesson 3): a constant multiplier equal to K1's mean realised multiplier per year, applied to
     every rung. K1 must beat CTRL to claim timing skill.
3. Score dev4 per year (4-phase reset metric, yearly DD, full-path DD, all-trade win rate, fills per year, mean multiplier) for REF, K1, K2,
   CTRL. Choose between K1 / K2 on dev4 with the robust criterion. Then score the most recent year ONCE for the chosen variant, REF and CTRL.
   If the engine can run on the clean window after 2026-09-23 (data permitting), add it as a labelled extra row; otherwise say why not.
4. In REPORT.md put the contamination caveat next to every dev number (dev = upper bound) and treat the most recent year as the verdict.
