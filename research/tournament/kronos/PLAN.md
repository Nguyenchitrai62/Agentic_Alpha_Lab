# Kronos zero-shot forecasts for 4h decisions - pre-registration (written 2026-10-05, before any forecast was run)

## Hypothesis
The public Kronos foundation model (zero-shot, no fine-tuning) produces forecasts of the next 4h bars of the majors that carry predictive
value for (a) the BOOK (direction over 1 bar / 7 days, next-bar volatility) and (b) the DIP sleeve (sizing of the R2 dip rungs).

## Data (hard stop 2025-09-24)
- 4h OHLCV bars (00/04/08/12/16/20 UTC) for BTC/ETH/SOL/BNB/XRP built by `build_bars.py` from the raw Binance USD-M 1m files with a parquet
  filter `open_time < 2025-09-24 00:00 UTC` (2026 files are never opened). amount = quote volume. No missing 4h bars in any coin.
- Forecast for bar open T uses ONLY the 400 bars whose close is <= T (the last context bar is [T-4h, T)). Forecast-bar time stamps are
  calendar values T, T+4h, ... (computed, not read).
- Inference range: every 4h bar open T from 2020-08-01 (or the first T with 400 context bars, SOL ~2020-11-20) to 2025-09-23 20:00.
  Disclosed deviation from the brief (2021-06-01 start): the earlier start only exists so that fold-1 DIP models have training rows with
  Kronos features (majors fills start 2020-08-21); the book IC evaluation uses only the four dev years. Benchmark: ~25 ms / series at
  S=32 (KV-cached sampler), so the full run (~55k series, S=64) is well under 3 h -> NO subsampling.

## Model and sampling (fixed)
- Kronos-small (NeoQuasar/Kronos-small, 24.7M) + NeoQuasar/Kronos-Tokenizer-base, weights from HuggingFace, code copied into `model/`
  (MIT licence, unmodified except the import line). Zero-shot only.
- Context 400 bars (README example lookback), pred_len 6 (= 24 h), sample paths S = 64, T = 1.0, top_p = 0.9, top_k = 0 (README defaults).
  Per-window z-normalisation and clip 5 exactly as `KronosPredictor`. torch seed 1234, fp32.
- `kronos_fast.py` = KV-cached multi-path version of the reference `auto_regressive_inference` (no window roll since 400 + 6 <= 512).
  Verified: greedy tokens identical to the reference calls, decoded outputs equal to 1.2e-6; sampled tokens lie inside the reference
  top-p nucleus. Returns every path (the reference returns only the mean).
- Optional (only if small runs fine and time permits): Kronos-base, same settings, every 2nd bar, IC evaluation (a) only, labelled.

## Features (per sym, T), sigma = std of the last 360 4h open-to-open log returns ending at open(T); C0 = close of the last context bar
For path k and forecast bar j (j = 0 is bar T): O,H,L,C decoded; Leff = min(L,O,C), Heff = max(H,O,C).
- `er1`  = mean_k log(C_k[0]/C0) / sigma                (expected 1-bar log return)
- `er6`  = mean_k log(C_k[5]/C0) / (sigma*sqrt 6)       (expected 24h log return)
- `vol1` = std_k  log(C_k[0]/C0) / sigma                (forecast 1-bar volatility, ratio to trailing sigma)
- `vol6` = std_k  log(C_k[5]/C0) / (sigma*sqrt 6)
- `rng1` = mean_k log(Heff_k[0]/Leff_k[0]) / sigma      (forecast next-bar range)
- `low1` = mean_k log(Leff_k[0]/C0) / sigma             (forecast depth of the next-bar low)
- `pdrop2`, `pdrop3` = share of paths with log(Leff_k[0]/C0) < -2 / -3 sigma (drop larger than 2 / 3 sigma within the next bar)
Also stored: `sigma`, `C0`. File: `kronos_4h_features.parquet` (sym, T, features).

## Evaluation (dev years only: anchors 2021-09-24 .. 2024-09-24, each [A, A+365 d))
(a) BOOK: Spearman IC per year (pooled over coins and per coin) of each feature vs
  - `f42` = log(O[T+42]/O[T]) / (sigma*sqrt 42)  (7-day forward; rows whose label would need data >= 2025-09-24 are dropped),
  - `r1`  = log(O[T+1]/O[T]) / sigma (next bar).
  Vol skill: IC of the raw forecast vol (vol1*sigma) vs |r1 raw| next to the baselines trailing sigma_4h(360) and trailing std over 42 bars;
  incremental skill = IC(vol1, |r1|/sigma) (the scaled baseline is a constant), compared with IC(sigma42/sigma, |r1|/sigma).
(b) DIP: join to `harness.load()` rows on (sym, T = bar open); score with `harness.score`, each variant ONCE:
  - V1 (rule): risk = -low1 (expected next-bar low depth, the continuous version of the drop probability). Per fold, on TRAINING majors rows
    (t_exit < A - 7 d, Kronos feature present): direction = sign of Spearman(risk, y_dep); quintile edges q20/q80 of risk. Size =
    size_dep * 1.5 in the favourable outer quintile, * 0.5 in the unfavourable outer quintile, * 1 otherwise (missing feature -> * 1).
  - V2 (model): HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, random_state=0) on the
    bar-open features of `research/tournament/data/bar_open.parquet` (all columns except j/sym/r) + rung depth k + the 8 Kronos features,
    trained per fold on MAJORS rows with t_exit < A - 7 d (all rungs 2.0..5.0), target y_dep. Size = 1.5 if pred > 2 * mean(y_dep train),
    0.5 if pred < 0, else 1 (replaces size_dep).
  - V3 (control, ablation of V2): identical HGB without the Kronos features. Kronos adds value for the DIP only if V2 graduates AND V2 beats
    V3 in >= 3 of 4 years.
Graduation = harness rule (gain > 0 in >= 3/4 years, total > 0, worst day not > 20 % worse than deployed).

## Caveats known in advance
- Kronos's pretraining corpus (45 exchanges, up to ~mid 2025) very likely contains these exact crypto series -> the zero-shot test years
  are probably IN-SAMPLE for Kronos itself. Positive results are an upper bound; only a prospective log could confirm them.
- 42-bar labels overlap -> per-year IC standard errors are much larger than 1/sqrt(n).
