# oc_kronoshidden — PLAN (pre-registered 2026-10-07, BEFORE any outcome)

Clean test of the Kronos dip tilt (research/tournament/kronos V1 rule) on
post-release data. Dev years are IN Kronos's training data (upper bound);
the most recent year 2025-09-24 .. 2026-09-23 is AFTER its release (verdict).

## Part A — features (no outcomes; GPU through heavy_slot)

- Code: copy of research/tournament/kronos/{model/,kronos_fast.py,
  build_bars.py,run_inference.py} into this folder, IDENTICAL settings:
  Kronos-small + Kronos-Tokenizer-base (HF cache, no re-download),
  context 400 x 4h bars, pred_len 6, S = 64 paths, T = 1.0, top_p = 0.9,
  top_k = 0, torch seed 1234, fp32, per-window z-normalisation + clip 5.
  8 features per (sym, shift, T): er1, er6, vol1, vol6, rng1, low1, pdrop2,
  pdrop3 + sigma, C0 (PLAN.md definitions of kronos/).
- Bars: 4h OHLCV for BTC/ETH/SOL/BNB/XRP from raw Binance USD-M 1m klines,
  FOUR clock grids shift s = 0,1,2,3 h (opens at s, s+4, ... UTC),
  2020-08-01 .. last complete 4h bar available locally. 1m sources:
  data/raw/majors_intraday_20260924 ({SYM}_1m_{YYYY}.parquet, alts),
  data/raw/btc_intraday_20260924 (klines_1m_{YYYY}.parquet, BTC),
  cross-checked against data/raw/btc_1m_hidden_20260924 (BTC duplicate
  2025-09-23 .. 2026-09-24) and data/raw/majors_1m_oos_20261006
  (all 5 majors, 2026-09-24 .. 2026-10-05, post-year extension only).
  Report which file covers which period + any gap/duplicate at junctions.
- Forecast for bar open T uses ONLY the 400 bars closing <= T on that
  shift's grid (same indexing as kronos/run_inference.py).
- Overlap check: recompute shift 0 on 2025-06-01 .. 2025-09-23, report
  Spearman + median abs diff of low1 vs
  research/tournament/kronos/kronos_4h_features.parquet (expect rho > 0.9).
- Output: kronos_features_4shift.parquet (sym, shift, T, 8 feats+sigma+C0).

## Part B — engine (4-phase, heavy_slot)

- Mechanism: copy of v414/v414_dvol_tilt.py, tilt swapped for Kronos:
  per-(coin, holding bar) dip-size multiplier on top of the corr-aware dip
  sizes (rule="inv", k=1.0, kd=1.7, bear=True, G=2.0 = v421 G2
  R2B1D17BFG2); budget unchanged. REF row loaded from v421/v421_runs.pkl
  cache (bit-exact); must reproduce 5.41 / 16.91 / 16.82 else STOP.
- Variants (ONLY these four, fixed):
  - REF = G2 unchanged.
  - K1 = kronos/PLAN.md V1: risk = -low1. Per anchor A fit on TRAINING
    rows = majors rows of harness.load() with t_exit < A - 7 d and
    shift-0 feature present (join on (sym, T)): direction = sign of
    Spearman(risk, y_dep); edges q20/q80 of risk. Mult 1.5 favourable
    outer quintile / 0.5 unfavourable / 1 else; missing -> 1. Fits of
    anchor A applied to all four shifts in year A. Most-recent-year fits
    use all harness rows with t_exit < 2025-09-17.
  - K2 = K1 with 1.25 / 0.75.
  - CTRL = exposure-matched control: constant multiplier = K1's mean
    realised multiplier per year on every rung. K1 needs to beat CTRL.
- Score dev4 (anchors 2021..2024): per-year 4-phase reset %/mo (reset
  metric year_reset), yearly DD, full-path DD (v388.mix continuous from
  2021-09-24), all-trade win rate, fills/year, mean multiplier.
  Choose K1 vs K2 on dev4 ONLY with the robust criterion
  (DD <= 20, no losing dev year; prefer dev4 mean >= 5 %/mo, then highest
  dev4 WORST-year monthly return, ties -> higher mean).
  Then score the most recent year ONCE for chosen + REF + CTRL.
  Post-2026-09-23 window: labelled extra row only if the 4-phase engine
  minutes + books cover it (only ~12 d of 1m exist -> expect "why not").

## Costs / leakage / caveats

- Gate costs: maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts 0.
  Limits fill only on 1m trade-through, nothing in first 5 min after a 4h
  close; stop-first in shared 1m bar (engine handles).
- Leakage checks in REPORT: feature timing (400 bars <= T), label windows
  (harness t_exit < A - 7 d), fit windows (shift-0 only, embargo),
  fill timing (engine win_start=5, trade-through).
- Contamination caveat next to EVERY dev number (dev = upper bound);
  the most recent year is the verdict. A negative result is valid.
