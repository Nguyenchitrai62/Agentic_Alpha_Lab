# oc_presampleflow PLAN (pre-registered BEFORE any outcome is computed, 2026-10-07)

## Purpose (descriptive generality test; NOT a deployment change)

oc_bookattrib: G2's book return is TIMING (placebo >= 96.8 every year
2021-2025). oc_presamplebook: a TV-only member has ~0 OOS IC, so the timing
comes from the other members: whale flow (A/Aq, v236/v240 order-level flow)
and the Coinbase premium (D/Dq, v285). oc_memberdrop: either family alone
keeps G2. Their skill was only ever measured on 2021-2026. Question: do the
deployed member FAMILIES show positive OOS IC in never-used pre-sample years
like (or unlike) the research years? Single fixed pipeline per family, no
tuning, no selection. Any change after seeing an outcome is a disclosed extra
row. No most-recent year is touched.

## Deployed weights (confirmed from code BEFORE any outcome)

- `scripts/forward_v205.py::research_books_d2`: `o1 = 0.5*(A+B)/2 +
  0.5*(Aq+Bq)/2`, `d2 = 0.8*o1 + 0.2*(D+Dq)/2` (union index, missing -> 0.0),
  where A = `member_A_O1_orders` (annual order-level whale flow, v240 O1),
  Aq = `member_Aq_O1_orders` (quarterly), B/Bq = `member_B_tv`/`member_Bq_tv`
  (TradingView), D = `members_v154[D]` (annual Coinbase-premium, v154/v285),
  Dq = `members_quarterly_D` (quarterly). Implicit FULL weights: A/Aq/B/Bq
  0.2 each, D/Dq 0.1 each (sum 1.0). Same blend in v285 (`D2_d20`) and
  oc_memberdrop FULL. The diagnostic BLEND below mirrors the 0.8/0.2 family
  weighting at the prediction level (disclosed proxy, not the engine).

## Variants (ONLY these three; fixed here)

- FLOW: 6 order-level whale-flow features ONLY (family isolation).
- PREMIUM: 5 Coinbase-premium features ONLY (family isolation).
- BLEND: `pred_blend = 0.8*pred_FLOW + 0.2*pred_PREMIUM` per (t, sym) row
  (mirrors deployed `d2 = 0.8*o1 + 0.2*D`; o's TV part B/Bq is ~0-skill per
  oc_presamplebook, so FLOW proxies o's skill contribution; diagnostic only).

## Data (frozen, read-only)

- Spot prices: pre-sample 4h built from `data/raw/spot_1m_presample_20261007/`
  (BTC/ETH from 2017-08-17 04:00, BNB from 2017-11-06, XRP from 2018-05-04,
  all to 2020-09-30 23:59 UTC) on the standard grid (opens
  00/04/08/12/16/20 UTC): per window [T, T+4h), open = first finite 1m open,
  high = max finite high, low = min finite low, close = last finite close,
  volume = sum of finite volumes; windows with zero finite minutes are NaN
  bars; gaps stay NaN (never filled; oc_presamplebook precedent, same code
  shape). Reference prices: `data/raw/spot_majors_20260925/<SYM>_spot_4h.parquet`
  (Binance SPOT, 2019-09-01..2026) for t >= 2020-10-01. Stitch per coin:
  presample-built for t < 2020-10-01, spot_majors after (no overlap, no seam
  choice; both Binance SPOT, same venue). Labels and `r_next` are computed on
  the stitched series (single venue throughout; no spot/perp seam at all).
- Spot order flow (FLOW venue): `data/raw/aggflow_spot_20260929_orders/`
  (`<SYM>_flow_4h.parquet`, built by `scripts/fetch_aggtrades_flow.py
  --market spot --orders`; BTC/ETH/BNB from 2017-08/11, XRP from 2018-05-04,
  through 2026-09-28). VENUE DIFFERENCE DISCLOSED: the research years used
  PERP flow (`aggflow_20260928_orders`); here BOTH pre-sample and reference
  use SPOT flow so the comparison is like-for-like on the same construction.
- Coinbase premium (PREMIUM venue): `data/raw/coinbase_20260925/`
  (BTC-USD/ETH-USD 1h from 2017-08-01) vs Binance SPOT 4h closes (v111
  `premium()` reads `spot_majors_20260925` 2017-prefix + spot_4h internally;
  same SPOT venue as our stitched prices for t >= 2019-09-01, 2017-prefix
  files before; disclosed).
- Coins: BTCUSDT, ETHUSDT, BNBUSDT, XRPUSDT only (SOL excluded: no
  pre-2020 spot flow; same 4 coins as oc_presamplebook for comparability).

## Features (copied UNCHANGED via import; originals never edited)

- FLOW: `research/parallel/rounds/parallel-20260906-r2/v236/flow_features.py`
  (`FL` = fl_big_imb6, fl_big_imb42, fl_ret_imb6, fl_div6, fl_big_share_z,
  fl_whale_n_z; same six formulas as v240's order-level variant, which only
  repoints `D` at the orders table), imported UNCHANGED with `D` repointed
  at `data/raw/aggflow_spot_20260929_orders` (the v240 pattern:
  `flo.D = ORDERS`; no edit to the original file). Row of bar t uses only
  trades inside bars <= t (causal rolling <= t); NaN before archive/warm-up.
- PREMIUM: `research/parallel/rounds/parallel-20260906-r2/v111/`
  `v111_coinbase_premium.py` (`premium()` + `add_cb()`; `CB` = cb_btc_dev,
  cb_btc_z, cb_btc_chg, cb_eth_z, cb_eth_chg; Coinbase 1h close at T+3h vs
  Binance SPOT 4h close, asof-backward within 2h; rolling-6/42/540, causal),
  imported UNCHANGED. Market-wide: the same 5 values are joined to every
  coin by t (SOL/BNB/XRP use BTC's premium exactly as the deployed code
  does -- `add_cb` merges on `t` only, no per-asset premium).
- No TV, no v92-base, no xs, no asset dummies in either family (isolation;
  TV-only is already ~0 IC per oc_presamplebook, so its omission does not
  flatter either family).

## Model and label (copied from v92, = oc_presamplebook; pooled HGB as deployed)

- Label (v92 `v92_pooled_hgb_vt.py` lines 53-84 copy): H = 42 bars (7 days).
  r1 = diff of log close; vol42 = rolling(42).std of r1 (causal, closes <= t);
  fwd[i] = log(o[i+1+H]/o[i+1]) with o = 4h opens (signal at close of bar i
  executes at next open, held H bars); y = clip(fwd/(vol42*sqrt(H)), -4, 4).
  Label end time = t + 43*4h. NaN-label rows are dropped.
- Model (v92 line 115, = v231 A settings = oc_presamplebook):
  HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03,
  max_iter=400, min_samples_leaf=300, l2_regularization=1.0, random_state=0),
  pooled over the 4 coins, one fit per anchor. NaN features left for native
  HGBR handling. No scaling, no calibration, no threshold tuning.
- NOTE (disclosed proxy): deployed A/D members are full v144 ensembles
  (v92 7d LO + v94 3d/7d/14d LS + v103 1d/3d LS + vol-target + xs); this study
  tests each FAMILY's features through the common v92 7d yardstick (same as
  oc_presamplebook's TV test), so pre-sample vs research-year ICs are
  comparable across all three family studies. Not a deployment change.

## Anchors (test year = [A, A+365d))

- Pre-sample (spot only): A = 2019-03-01 (train 2017-10..2019-02),
  2019-09-24, 2020-03-01 (overlaps COVID; truncated at 2020-09-23 by label
  realisation against the 2020-09-30 store end).
- Reference (same spot-built features/labels; NOT perp): A = 2021-09-24,
  2022-09-24, 2023-09-24, 2024-09-24 (same code, spot venue both sides).
- Training rows: label end < A - 7d, i.e. t + 43*4h < A - 7d (7-day embargo).
  Reference anchors train on everything before (spot history, same rule).
- Test rows: A <= t < A+365d with realised label (label end <= data end).
  Coverage reported, no filling. The most-recent year is never touched.

## Metrics (per test year x variant)

- Pooled Spearman IC of pred vs realised label + per-coin IC, with 95%
  block-bootstrap CI (block = 42 consecutive 4h bars in time order, 1000
  resamples, seed 0; per-coin CI within that coin's bars).
- Sign hit rate (pooled + per-coin): mean(sign(pred) == sign(label)); a zero
  matches only a zero.
- In-sample (train) pooled IC as positive control.
- Diagnostic long/short book P&L (VECTORISED DIAGNOSTIC - not the engine,
  oc_presamplebook definition): s = std of the model's predictions on its
  training rows (fallback: train-label std if non-finite/zero); per coin per
  test bar w(t) = clip(pred(t)/s, -1, 1); position set at the close of t earns
  the next-bar open-to-open return r = o[t+2]/o[t+1] - 1 (executable, within
  the single stitched spot series); cost 0.0002 per unit turnover
  (|w(t)-w_prev| per coin, establishing turnover on first bar); portfolio
  per-bar net = mean over coins with valid w of (w*r - cost*|dw|)
  (equal-weight mean keeps gross <= 1: no leverage); equity from 1.0
  compounded; report monthly geometric (30.4375 d), total %, max DD %,
  turnover, n bars. NaN pred/return coins are skipped that bar. BLEND uses
  pred_blend with s = 0.8*s_flow + 0.2*s_prem (fixed here; no fitting).

## Key question (bold in REPORT)

**Do the deployed member families show positive OOS IC in the pre-sample
years like (or unlike) the research years?**

## Leakage / execution statement (to verify in REPORT)

Features at bar t use bars/trades/candles <= t only (flow: trades inside
bars <= t + causal rolling; premium: Coinbase 1h opening at T+3h known at
4h close + causal rolling; label uses opens t+1..t+43). Fits use only rows
with label end < anchor - 7d. Diagnostic fills use next-bar opens only
(executable). No statistic from a test year feeds any choice. Tests:
`tests/test_oc_presampleflow.py` (causality/truncation: train rows end
before anchor-embargo, test labels realised, next-bar-only returns;
hand-checked synthetic: label math incl. clip, flow ratio/z formulas on a
toy ledger, premium asof/rolling on toy candles, clip weight, turnover cost,
block bootstrap shape, blend 0.8/0.2 arithmetic).

## Protocol / resources

- Scripts ONLY in `research/tournament/oc_presampleflow/`:
  `presampleflow.py` (spot 4h build + flow/premium features + labels +
  walk-forward pooled HGBR -> `preds_<variant>_<anchor>.csv` + `tmp/fits.json`),
  `metrics.py` (IC/CI/hit/P&L -> `results.json`), scratch under `tmp/` only.
  One coin's 1m slice in RAM at a time (float32); flow 4h tables are small
  (~20k rows); HGBR fits are small. If any step exceeds 0.4 GB it goes
  through `scripts/heavy_slot.py` (tag oc_presampleflow, never --leader).
  Progress printed per coin/anchor (at least every 10 minutes).
- Outputs: `results.json`, `REPORT.md` (per-year x variant tables + 3-line
  Vietnamese verdict), per-variant-per-year predictions CSV,
  `SUMMARY.md` (<= 15 lines).
- Tests: `tests/test_oc_presampleflow.py` (see above). Run
  `.venv/Scripts/python.exe -m pytest tests/test_oc_presampleflow.py -q`.
- No commits; no edits outside `research/tournament/oc_presampleflow/` (+
  `tests/test_oc_presampleflow.py`). Git is read-only.

## Post-hoc log

- 2026-10-07 (disclosed in REPORT, no definition changed): the 2020-03-01 test
  year runs the full 8760 rows, not truncated at 2020-09-23 -- the
  pre-registered stitch rule (spot_majors SPOT 4h for t >= 2020-10-01, same
  venue) keeps its labels realisable, so the truncation clause was
  inoperative. `train_ic_blend` = IC of the fixed 0.8/0.2 combination of the
  two fitted models' train predictions (no refit, no choice).
