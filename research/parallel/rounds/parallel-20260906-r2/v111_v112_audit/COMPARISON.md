# v111 + v112 blind audit — COMPARISON.md (Part B)

Blind replication was saved BEFORE opening `v111/` / `v112/` (see `replication.json`,
`predictions_v111_primary.csv`, `predictions_v111_secondary.csv`,
`predictions_v112_primary.csv`, `equity_v111_primary*.csv`,
`equity_v111_secondary*.csv`, `equity_v112_primary*.csv`, `equity_v112_blend*.csv`
in this folder).
Audit scope: `v111/v111_coinbase_premium.py`, `v111/v111_result.json`,
`v111/result_manifest.json`, `v112/v112_sign_classifier.py`, `v112/v112_result.json`,
`v112/result_manifest.json` (plus `v103/v103_flow_short_horizon.py`,
`v92/v92_pooled_hgb_vt.py`, `v94/v94_long_short_ensemble.py` as shared base).
No leader files were edited. All writes are under `v111_v112_audit/` + `tests/test_v111_v112_audit.py`.

## A. Number comparison (blind audit vs leader)

### v111 primary (A1: v103 + 5 CB feats, LS): exact match on ICs, train rows, all scenarios

Per-anchor IC (blind vs leader `ic_short`):

| anchor | IC y6 b/l | IC y18 b/l |
|---|---|---|
| 2021-09-24 | 0.0621/0.0621 | 0.0458/0.0458 |
| 2022-09-24 | 0.0282/0.0282 | 0.0498/0.0498 |
| 2023-09-24 | 0.072/0.072 | 0.1072/0.1072 |
| 2024-09-24 | 0.0123/0.0123 | 0.0054/0.0054 |
| 2025-09-24 | 0.1346/0.1346 | 0.1666/0.1666 |

Train rows h6/h18 blind: 33388/33328, 44338/44278, 55288/55228, 66268/66208,
77218/77158 (same embargo/label grid as v103; CB feats add no rows).

Yearly normal LS (blind vs leader `primary_v103_plus_cb_ls.normal.yearly`):

| anchor | net % b/l | DD % b/l | fills b/l |
|---|---|---|---|
| 2021-09-24 | 13.66/13.66 | 15.67/15.67 | 1697/1697 |
| 2022-09-24 | 1.11/1.11 | 31.09/31.09 | 2140/2140 |
| 2023-09-24 | 68.27/68.27 | 8.35/8.35 | 2145/2145 |
| 2024-09-24 | 7.30/7.30 | 18.00/18.00 | 2140/2140 |
| 2025-09-24 | 102.26/102.26 | 9.76/9.76 | 2048/2048 |

Fee-stress yearly: 10.15/10.15, -2.52/-2.52, 62.44/62.44, 3.16/3.16,
94.76/94.76 exact; execution-stress: 5.91/5.91, -6.88/-6.88, 55.44/55.44,
-1.79/-1.79, 85.78/85.78 exact; DDs and fills exact in both stresses.

No IC (>0.01) or return (>1pp) threshold exceeded for v111 primary.

### v111 secondary (A1: v92 + 5 CB feats, 7d long-only): exact match

IC vs y (blind vs leader `ic_v92_cb`): 0.1189/0.1189, 0.0201/0.0201,
0.1221/0.1221, 0.0214/0.0214, 0.2917/0.2917.
Train rows blind: 33088, 44038, 54988, 65968, 76918 (v92 102-bar embargo grid).

Yearly normal LO (blind vs leader `secondary_v92_plus_cb_lo.normal.yearly`):
-2.58/-2.58, 18.90/18.90, 85.86/85.86, 38.09/38.09, 29.48/29.48;
DDs 22.42/22.42, 16.39/16.39, 10.86/10.86, 11.68/11.68, 23.27/23.27;
fills 1290/1290, 1407/1407, 1430/1430, 1788/1788, 921/921.
Fee/execution yearly nets, DDs, fills exact as well.

No threshold exceeded.

### v112 primary (A2: v103 feats, per-horizon classifier, LS): exact match

Per-anchor IC of `pred=2*mean P(up)-1` vs y (blind vs leader `ic`):

| anchor | IC y6 b/l | IC y18 b/l |
|---|---|---|
| 2021-09-24 | 0.063/0.063 | 0.0309/0.0309 |
| 2022-09-24 | 0.031/0.031 | 0.0382/0.0382 |
| 2023-09-24 | 0.0447/0.0447 | 0.018/0.018 |
| 2024-09-24 | 0.0538/0.0538 | 0.0776/0.0776 |
| 2025-09-24 | 0.0411/0.0411 | 0.0672/0.0672 |

Train rows h6/h18 blind: same as v103 grid (33388/33328 ... 77218/77158).

Yearly normal LS (blind vs leader `primary_long_short.normal.yearly`):
6.05/6.05, -9.44/-9.44, 23.17/23.17, 13.61/13.61, 22.16/22.16;
DDs 22.76/22.76, 29.82/29.82, 18.64/18.64, 19.15/19.15, 20.16/20.16;
fills 1637/1637, 2143/2143, 2154/2154, 2149/2149, 1914/1914.
Fee/execution yearly exact.

No threshold exceeded.

### v112 secondary (A2: 0.5*v96 + 0.5*LS-scaled, scale 1): exact match

Yearly normal blend (blind vs leader `secondary_blend_v96.normal.yearly`):
5.82/5.82, 8.48/8.48, 45.09/45.09, 31.14/31.14, 27.67/27.67;
DDs 21.62/21.62, 15.84/15.84, 8.77/8.77, 10.90/10.90, 15.71/15.71;
fills 1691/1691, 2176/2176, 2176/2176, 2185/2185, 2082/2082.
Fee/execution yearly exact.

No threshold exceeded anywhere in v111/v112.

## B. Why blind matched

- Base panel: blind reimplements the audited v103 path inline (USD-M + spot-prefix
  concat, v92 features, 10 flow features, y6/y18/y42 labels, 78-bar embargo with
  per-horizon `t+(h+1)*4h<cutoff`, HGB `max_depth 4/lr 0.03/max_iter 400/
  min_samples_leaf 300/l2 1.0/random_state 0`, `pred=mean`). Train rows agree with
  the v103 grid, so the join, embargo, and NaN-native handling coincide.
- CB features: blind implements the spec formulas inline; leader
  `premium(asset)` (`v111_coinbase_premium.py:46-59`) is the same: spot concat of
  the two 4h files, `drop_duplicates("open_time")` sorted, `key=T+3h`,
  `merge_asof` backward with 2h tolerance, `cbp=1e4*log(cb/close)`,
  `p6=roll6/min4`, `p42=roll42/min30`, `m540/s540=roll540/min270` (pandas
  `std` ddof=1 on both sides), `dev=p6-m540`, `z=(p6-m540)/s540`, `chg=p6-p42`.
  Leader `add_cb` keeps BTC times and left-joins ETH (`:62-66`); blind builds the
  union grid and left-joins both — identical because BTC/ETH spot 4h grids are
  the same (both 2017-08-17..2026-09-25). Coverage field matches the spec join:
  leader `coverage` BTC/ETH 0.986 (early NaN from 270-bar warmup), others 1.0.
- Weights/vol/execution: blind reimplements audited `v94.weights_ls`
  (shorts True/False), `v94.vol_target_scale` (20% cap 2, `W.shift(2)` realised,
  trailing 360/min-120, NaN->1), `v92.simulate` (2-bar delay, fee+slip on scaled
  turnover, 0.00005/bar long funding) and `v103.evaluate` yearly cuts. Leader
  calls the audited functions directly (`v103.evaluate`, `v94.weights_ls`,
  `v92.weights_from`/`vol_target_scale`). For the v111 secondary the long-only
  leg `v94.weights_ls(shorts=False)` (blind) is algebraically identical to
  `v92.weights_from(..., "model")` (leader `:91`): `clip(pred,0)/0.5`,
  `rib!=-1`, `/vol42/sqrt(2190)`, gross-normalise, `count/5`, every-6th-bar
  ffill. Nets/DDs/fills agree bit-exact on all books and scenarios.
- v112 classifier: blind `HistGradientBoostingClassifier(**HGB_PARAMS)` per
  horizon on `(y_h>0).astype(int)`, `pred=2*mean P(up)-1` (`replicate:train_predict_clf`)
  matches leader `train_predict` (`v112_sign_classifier.py:38-50`) line for line,
  including `predict_proba(...)[:,1]` column, same embargo/feats. ICs use OOS
  spearman of that `pred` vs `y_h`.
- v96 leg provenance (no PnL effect): leader retrains v92/v94 paths inside
  `v112_sign_classifier.py:67-74` (deterministic HGB) and combines with its own
  v112 LS leg scaled by its trailing vol before `0.5*v96+0.5*W112` with
  `scale=1.0` (`:76`); blind reuses the audited OOS CSVs
  (`v92_audit/predictions_5asset.csv`, `v93_v94_audit/predictions_v94.csv`) with
  the leader vol scales for the v96 leg and its own v112 OOS for the v112 leg.
  Because retraining is deterministic, both give the same books: blend nets
  agree exactly.

## C. Look-ahead audit

### `v111_coinbase_premium.py` — no look-ahead found (Coinbase alignment correct)

- Spot/coinbase read: `premium()` concats the two Binance spot 4h files,
  dedups on `open_time`, sorts (`:49-52`); coinbase 1h read with UTC times.
  No future files; no USD-M data in the premium itself. Pass.
- Time alignment: `key = open_time + 3h`, `merge_asof(..., left_on="key",
  right_on="open_time", direction="backward", tolerance=2h)` (`:53-55`). For a
  4h bar opening at T, this picks the 1h candle opening at or before T+3h —
  normally exactly T+3h — covering `[T+3h, T+4h)`. Its close is known at T+4h,
  i.e. at the 4h bar close, so `cbp=1e4*log(cb_close/spot_close)` uses only
  information available after candle T closes. The 2h tolerance only fills gaps
  backward (older hours), never forward; missing maps to NaN (HGB-native).
  Correct 1-bar delay, no future beyond the execution bar. Pass.
- Rolling: `p6/p42/m540/s540` are trailing rolling means/std on `cbp` in spot
  time order (`:57-58`), then `dev/z/chg` (`:59`). All causal; early NaN
  (min-periods 4/30/270) matches the 0.986 BTC/ETH coverage. Pass.
- Join: `add_cb` merges the 5 features onto the panel by exact `t=open_time`
  (`:62-66`); panel decisions at `t` use features known at `close_time[t]`.
  Training rows satisfy the v103/v92 embargo (`v103.train_predict`,
  `v92.train_predict` with 78/102-bar cutoffs); labels `y6/y18`/`y` realised
  before cutoff. Pass.
- Books: primary reuses `v103.train_predict` + `v94.weights_ls(True)` +
  `v103.evaluate` (own 20% vol) (`:77-82`); secondary reuses `v92.train_predict`
  + `v92.weights_from("model")` + `v92.vol_target_scale` (`:83-93`). All scale
  inputs lagged (`W.shift(2)` realised). Pass.

### `v112_sign_classifier.py` — no look-ahead found

- Panel/feats/embargo: `v103.build()` and the v103 feature list (v92+flow, no
  `y*` labels) (`:54-55`); per-horizon filter `t<cutoff and t+(h+1)*4h<cutoff`,
  `cutoff=A-78*4h` (`:40,44-45`). Same timing as audited v103. Pass.
- Labels: classifier target `(y_h>0).astype(int)` (`:47`) is the sign of the
  already-embargoed vol-normalised forward return; no new data. `pred` is
  `2*mean P(up)-1` (`:49`), range [-1,1], fed to `v94.weights_ls(shorts=True)`
  with its own 20% vol (`:64-65`). Pass.
- Blend: v96 retrained legs use audited v92/v94 code with own trailing vols
  (`:67-74`), combined `0.5*v96+0.5*(W112*s112)` with `scale=1.0` after
  (`:75-76`); all scale inputs lagged. The v96-vs-v112 retrain-vs-CSV
  difference is provenance only (deterministic HGB gives identical books, per
  section A). Pass.

## D. Manifest notes

- `v111/result_manifest.json`: track B, `rejected`, `live_approved:false`,
  pending-audit flags. Normal monthly 2.419%, worst DD 31.09%, fills 10170/60mo;
  secondary LO monthly 2.272%, worst DD 23.27%.
- `v112/result_manifest.json`: track C, `rejected`, `live_approved:false`.
  Normal monthly 0.83%, worst DD 29.82%, fills 9997/60mo; blend monthly 1.724%,
  worst DD 21.62%.

## E. Verdict

- v111 (primary LS + secondary 7d LO, all three scenarios) and v112 (primary
  classifier LS + secondary v96 blend, all three scenarios) blind reproductions
  are bit-exact on train rows, ICs (y6/y18/y), yearly normal/fee/execution nets,
  DDs, and fills. No IC (>0.01) or return (>1pp) threshold exceeded.
- No look-ahead found in Coinbase premium time alignment, trailing
  premium windows, panel join, short-horizon/7d labels/embargo, classifier
  targets, LS/LO weights, vol targets, or v96-blend timing. Audit complete;
  leader files untouched.
