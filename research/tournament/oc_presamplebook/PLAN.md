# oc_presamplebook PLAN (pre-registered BEFORE any outcome is computed, 2026-10-07)

## Purpose (descriptive generality test; NOT the deployed book)

oc_presample / oc_presample2 showed the dip sleeve generalises to never-used
2017-2020 data, and that the dip sleeve alone earns only 0.6-3 %/month in
2021-2026: the BOOK carries G2 (5.4 %/month). The book's skill has never been
checked outside 2021-2026. Question: does a TV-indicator book member trained
and tested on 2017-2020 spot data show the same directional skill (same sign,
similar size IC) as in the dev years? Single fixed member, no tuning, no
selection. Any change after seeing an outcome is a disclosed extra row.

## Data (frozen)

- Pre-sample: Binance SPOT 1m `data/raw/spot_1m_presample_20261007/` (BTC/ETH
  from 2017-08-17 04:00, BNB from 2017-11-06, XRP from 2018-05-04, all to
  2020-09-30 23:59 UTC; read-only, copy nothing). 4h OHLCV built on the
  standard grid (opens 00/04/08/12/16/20 UTC): per window [T, T+4h),
  open = first finite 1m open, high = max finite high, low = min finite low,
  close = last finite close, volume = sum of finite volumes; a window with
  zero finite minutes is a NaN bar. Gaps stay NaN (never filled).
- Reference: the same features on 2020-08..2025-09 from the existing 4h data:
  BTC `data/raw/ma_ribbon_20260924/klines_4h.parquet` (perp, from 2019-09-08),
  ETH/BNB/XRP `data/raw/xs_universe_20260924/<SYM>_4h.parquet` (perp, from
  2019-11-27 / 2020-02-10 / 2020-01-06). Per coin the panel is stitched:
  spot-built 4h for t < that coin's perp start, perp 4h after; features and
  labels are computed separately per segment (no seam artefact; labels
  crossing the one seam bar are dropped). SOL is excluded everywhere (no
  pre-2020 data); reference uses the same 4 coins for comparability.
- Coins: BTCUSDT, ETHUSDT, BNBUSDT, XRPUSDT only.
- Source rule (pre-outcome clarification): pre-sample anchors train AND test
  on the full spot-built series only (oc_presample precedent: pre-sample legs
  run on the new spot store even where perp exists; the 2020-03-01 test year
  is truncated by the 2020-09-30 store end to ~2020-09-23 by label
  realisation); reference anchors train on everything before (spot history +
  earlier perp stitched) and test on perp bars only ("the same features on
  2020-08..2025-09 from the existing 4h data").

## Member (pooled HGBR, 17 TV features only)

- Features: the 17 TV features exactly as `v231/tv_indicators.py` defines
  them (`TV` list), reused UNCHANGED via import (no copy, no edit, no flow,
  no premium, no asset dummies, no BTC-cross features).
- Label (copied from v92 `v92_pooled_hgb_vt.py` lines 53-84): H = 42 bars
  (7 days). r1 = diff of log close; vol42 = rolling(42).std of r1;
  fwd[i] = log(o[i+1+H] / o[i+1]) with o = 4h opens (signal at close of bar
  i executes at next open, held H bars); y = clip(fwd / (vol42*sqrt(H)),
  -4, 4). Label end time = t + 43*4h.
- Model (copied from v92 line 115, = v231 A member settings):
  HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03,
  max_iter=400, min_samples_leaf=300, l2_regularization=1.0,
  random_state=0), pooled over the 4 coins, one fit per anchor. Rows with
  NaN label are dropped; NaN features are left for the native HGBR
  handling. No scaling, no calibration, no threshold tuning.

## Anchors (test year = [A, A+365d))

- Pre-sample: A = 2019-03-01 (train 2017-10..2019-02), 2019-09-24,
  2020-03-01 (overlaps COVID). Training rows: label end < A - 7d, i.e.
  t + 43*4h < A - 7d (7-day embargo per assignment).
- Reference (same member, same code; NOT the deployed book, numbers stated
  separately): A = 2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24, training
  on everything before (same embargo rule; includes spot history + earlier
  perp). The most-recent year is never touched.
- Test rows: A <= t < A+365d with realised label (label end <= data end).
  The 2020-03-01 year is truncated by the 2020-09-30 store end (~207 of 365
  days realisable); coverage is reported, no filling.

## Metrics (per test year)

- Pooled Spearman IC of pred vs realised label + per-coin IC, with 95 %
  block-bootstrap CI (block = 42 consecutive 4h bars in time order, 1000
  resamples, seed 0; per-coin CI within that coin's bars).
- Sign hit rate (pooled + per-coin): mean(sign(pred) == sign(label)); a zero
  matches only a zero.
- Diagnostic long/short book P&L (VECTORISED DIAGNOSTIC - not the engine):
  s = std of the model's predictions on its training rows (fallback:
  train-label std if non-finite/zero); per coin per test bar
  w(t) = clip(pred(t)/s, -1, 1); position set at the close of t earns the
  next-bar open-to-open return r = o[t+2]/o[t+1] - 1 (executable, no
  lookahead); cost 0.0002 per unit turnover (|w(t)-w_prev| per coin);
  portfolio per-bar net = mean over coins with valid w of (w*r - cost*|dw|)
  (equal-weight mean keeps gross <= 1: no leverage); equity from 1.0
  compounded; report monthly geometric (30.4375 d), total %, max DD %,
  turnover, n bars. NaN pred/return coins are skipped that bar (mean over
  valid coins only).

## Key question (bold in REPORT)

**Is the pre-sample IC of the same sign and similar size as in the reference
years?**

## Leakage / execution statement (to verify in REPORT)

Features at bar t use bars 0..t only (tv_indicators docstring; causality
covered by tests/test_tv_indicators.py + our truncation test). Labels use
only opens t+1..t+43. Fits use only rows with label end < anchor - 7d.
Diagnostic fills use next-bar opens only (executable). No statistic from a
test year feeds any choice.

## Protocol / resources

- Scripts ONLY in `research/tournament/oc_presamplebook/`:
  `presamplebook.py` (4h build + features + labels + walk-forward ->
  `tmp/panel.json` + predictions CSV), `metrics.py` (IC/CI/hit/P&L ->
  `results.json`), scratch under `tmp/` only. One coin's 1m slice in RAM
  at a time (float32); HGBR fits are small (no heavy slot needed; if a step
  exceeds 0.4 GB it goes through `scripts/heavy_slot.py`, tag
  oc_presamplebook, never --leader).
- Outputs: `results.json`, `REPORT.md` (per-year tables + 3-line Vietnamese
  verdict), per-year predictions CSV, `SUMMARY.md` (<= 15 lines).
- Tests: `tests/test_oc_presamplebook.py` (causality/truncation: train rows
  end before anchor-embargo, test labels realised, next-bar-only returns;
  hand-checked synthetic: label values, clip weight, turnover cost, block
  bootstrap shape). Run `.venv/Scripts/python.exe -m pytest
  tests/test_oc_presamplebook.py -q`.
- No commits; no edits outside `research/tournament/oc_presamplebook/` (+
  `tests/test_oc_presamplebook.py`). Git is read-only.
