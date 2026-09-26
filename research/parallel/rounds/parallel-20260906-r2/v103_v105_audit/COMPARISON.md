# v103 + v104 + v105 blind audit — COMPARISON.md (Part B)

Blind replication was saved BEFORE opening `v103/` / `v104/` / `v105/` (see `replication.json`,
`predictions_v103.csv`, `predictions_v105a_noflow.csv`, `predictions_v105b_7dflow.csv`,
`equity_v103_LS.csv`, `equity_v103_LO.csv`, `equity_v103_blend.csv`,
`equity_v104_normal.csv`, `equity_v104_fee_stress.csv`, `equity_v104_execution_stress.csv`,
`equity_v104_hidden_exec.csv`, `equity_v105a_noflow.csv`, `equity_v105b_7dflow.csv` in this folder).
Audit scope: `v103/v103_flow_short_horizon.py`, `v103/v103_result.json`, `v103/result_manifest.json`,
`v104/v104_candidate.py`, `v104/v104_result.json`, `v104/result_manifest.json`,
`v105/v105_flow_ablation.py`, `v105/v105_result.json`, `v105/result_manifest.json`
(plus `v92/v92_pooled_hgb_vt.py`, `v94/v94_long_short_ensemble.py`, `v99/v99_candidate.py` as shared base).
No leader files were edited. All writes are under `v103_v105_audit/` + `tests/test_v103_v105_audit.py`.

## A. Number comparison (blind audit vs leader)

### v103 (A1): exact match on ICs, train rows, LS / LO / blend nets, DDs, fills

Per-anchor IC + train rows (blind vs leader `ic`):

| anchor | train h6 b/l | train h18 b/l | IC y6 b/l | IC y18 b/l | IC y42 b/l |
|---|---|---|---|---|---|
| 2021-09-24 | 33388/33388 | 33328/33328 | 0.0602/0.0602 | 0.0651/0.0651 | 0.1216/0.1216 |
| 2022-09-24 | 44338/44338 | 44278/44278 | 0.0258/0.0258 | 0.0551/0.0551 | 0.0117/0.0117 |
| 2023-09-24 | 55288/55288 | 55228/55228 | 0.054/0.054 | 0.0788/0.0788 | 0.083/0.083 |
| 2024-09-24 | 66268/66268 | 66208/66208 | 0.0298/0.0298 | 0.0579/0.0579 | 0.1154/0.1154 |
| 2025-09-24 | 77218/77218 | 77158/77158 | 0.0611/0.0611 | 0.112/0.112 | 0.1541/0.1541 |

Yearly normal LS (blind vs leader `primary_long_short.normal.yearly`):

| anchor | net % b/l | DD % b/l | fills b/l |
|---|---|---|---|
| 2021-09-24 | 24.17/24.17 | 18.87/18.87 | 1781/1781 |
| 2022-09-24 | 2.03/2.03 | 24.59/24.59 | 2158/2158 |
| 2023-09-24 | 66.52/66.52 | 10.14/10.14 | 2162/2162 |
| 2024-09-24 | 50.52/50.52 | 14.53/14.53 | 2138/2138 |
| 2025-09-24 | 52.77/52.77 | 12.60/12.60 | 2061/2061 |

Yearly normal long-only (blind vs leader `secondary_long_only.normal.yearly`): -0.92/-0.92,
26.30/26.30, 74.38/74.38, 65.65/65.65, 21.17/21.17; DDs 23.15/23.15, 14.51/14.51,
10.98/10.98, 11.34/11.34, 26.78/26.78; fills 1257/1257, 1520/1520, 1581/1581, 1643/1643, 1211/1211.

Yearly normal 0.5*v96 + 0.5*v103 blend (blind vs leader `secondary_blend_v96.normal.yearly`):
14.28/14.28, 14.77/14.77, 67.80/67.80, 50.64/50.64, 42.31/42.31; DDs exact; fills
1776/1776, 2176/2176, 2179/2179, 2163/2163, 2112/2112.

No IC (>0.01) or return (>1pp) threshold exceeded for v103.

### v104 (A2): exact match on all three scenarios + hidden execution net/DD

Yearly normal (blind vs leader `normal.yearly`):

| anchor | net % b/l | DD % b/l | fills b/l |
|---|---|---|---|
| 2021-09-24 | 14.07/14.07 | 15.79/15.79 | 1778/1778 |
| 2022-09-24 | 15.80/15.80 | 12.56/12.56 | 2186/2186 |
| 2023-09-24 | 64.90/64.90 | 6.74/6.74 | 2180/2180 |
| 2024-09-24 | 46.93/46.93 | 10.46/10.46 | 2165/2165 |
| 2025-09-24 | 32.70/32.70 | 10.06/10.06 | 2122/2122 |

Fee-stress yearly: 11.96/11.96, 12.93/12.93, 60.61/60.61, 42.59/42.59, 29.09/29.09 exact;
execution-stress yearly: 9.37/9.37, 9.43/9.43, 55.40/55.40, 37.35/37.35, 24.73/24.73 exact;
DDs exact in both stresses. No threshold exceeded.

Hidden-year strict 1m execution:

| metric | blind audit | leader `hidden_year_1m_execution_strict` | diff |
|---|---|---|---|
| net % | 28.27 | 28.27 | 0 |
| monthly geo % | 2.098 | 2.098 | 0 |
| max DD % | 11.46 | 11.46 | 0 |
| fills (trend-leg bars) | 2122 | 2122 | 0 |
| maker fills | 7053 | ~7053 (implied) | 0 |
| total orders | 8244 | 8249 | 5 (0.06%) |
| maker rate | 0.8555 (4dp) | 0.855 (3dp) | 0.0005 (rounding) |
| missing 1m | 0 | — (no field) | — |

Net/DD/fills exact; the 5-order / 0.0005 rate gap is counting + rounding only (B.2).

### v105 (A3): exact match on both legs

Primary no-flow LS ICs y6/y18 blind vs leader: 0.0462/0.0462, 0.0576/0.0576;
0.024/0.024, 0.0482/0.0482; 0.0512/0.0512, 0.0747/0.0747; 0.0226/0.0226, 0.0467/0.0467;
0.0714/0.0714, 0.1182/0.1182. Yearly normal: 20.69/20.69, -0.69/-0.69, 51.56/51.56,
34.19/34.19, 48.37/48.37; fills 1715/1715, 2146/2146, 2161/2161, 2143/2143, 2056/2056; DDs exact.

Secondary v92-7d + flow long-only IC (vs y) blind vs leader: 0.1161/0.1161, 0.022/0.022,
0.0735/0.0735, 0.109/0.109, 0.1485/0.1485. Yearly normal: 2.63/2.63, 36.97/36.97,
60.56/60.56, 59.08/59.08, 22.69/22.69; fills 1275/1275, 1500/1500, 1501/1501, 1755/1755,
1117/1117; DDs exact.

No threshold exceeded anywhere in v103/v104/v105.

## B. Why blind matched + the one counting note

### B.1 Method notes (no PnL-relevant difference)

- Flow features: blind implements the spec formulas inline on the prefixed 4h klines;
  leader `flow_features(b, vol42)` (`v103_flow_short_horizon.py:49-65`) is the same:
  `qv.clip(1)`, `tbr1.clip(0,1)`, `tbr_k=rolling(k).mean-0.5`, `flow_k=signed.sum/qv.sum`,
  `tbr_z=(m6-m180)/std180`, `tsize/ntr` 180-bar z-scores of `log(qv/ntr)`, `log(ntr)`,
  `rng6=mean6(log(h/l))/vol42`, `clv6=mean6((c-l)/(h-l) with 0->NaN)-0.5`. All causal rolling.
  Train rows agree for every anchor/horizon, so the join (spot prefix, BTC context), embargo
  (`max(HS)+10*PD=78`, per-horizon `t+(h+1)*4h<cutoff`), HGB params, and NaN-native handling coincide.
- Weights/vol/execution: blind reimplements audited `v94.weights_ls` (shorts True/False),
  `v94.vol_target_scale` (20% cap 2, `W.shift(2)` realised, trailing 360/min-120, NaN->1),
  `v92.simulate` (2-bar delay, fee+slip on scaled turnover, 0.00005/bar long funding).
  Leader calls the audited functions directly (`evaluate`, `v94.weights_ls`, `v92.simulate`).
  Nets/DDs/fills agree bit-exact on all books.
- v96 books provenance (no PnL effect): leader retrains v92/v94/v103 inside
  `v103_flow_short_horizon.py:139-146` and `v104_candidate.py:41-56` (deterministic HGB);
  blind reuses the audited OOS CSVs (`v92_audit/predictions_5asset.csv`,
  `v93_v94_audit/predictions_v94.csv`) with the leader `vol_target_scale` (no fillna, NaN->1)
  for the v96 leg and its own v103 OOS for the v103 leg. Because retraining is deterministic,
  both give the same books: blend nets agree exactly. Blend uses scale 1.0 (no further vol
  target) on both sides (`evaluate(..., scale=1.0)` vs blind `simulate(..., 1.0)`).
- v104 wrapper: blind uses the v99 constants (0.8 books + 0.2*3 carry, 15% target cap 2)
  with leader carry convention `carry_exp[t]*carry[t]` and first carry diff 0
  (`v104_candidate.py:88-106`); realised/vol/scale/costs identical, so normal/fee/execution
  yearly agree exactly.
- v105: primary is `v103.train_predict(panel, a, noflow)` + `weights_ls(...,True)`
  (`v105_flow_ablation.py:41-45`); secondary sets `v92.FEATS=allf` (v92+flow) then
  `v92.train_predict` (102-bar embargo, y42) + `v92.weights_from(..., "model")` with
  `v92.vol_target_scale` (`:46-54`). Blind does the same steps (with `weights_ls(False)`
  for the long-only leg, which is algebraically identical to `weights_from(..., "model")`).
  ICs/nets/fills exact.

### B.2 Hidden-execution 5-order gap (no PnL effect)

- Window, prices, costs identical: per nonzero `diff(Wt)` at `t`, `T=t+4h`; missing-T 1m ->
  taker 0.0005 at 4h open*(1+/-0.0002); else `p0`=1m open at T, maker 0.0002 iff any 1m bar
  with `open_time` in `[T+2m, T+14m]` has `low<p0` (buy) / `high>p0` (sell) strictly;
  else taker 0.0005 at T+15m 1m open (`p0` if missing) + 0.0002 adverse
  (`v104_candidate.py:59-80` vs blind `run_hidden_execution_v104`). Cost model identical:
  `|dW|*rate + dW*rel` with maker 0.0002 / taker 0.0005 (`:102-104`).
- Counts: makers 7053 on both sides; blind orders 8244 vs leader 8249 (+5, 0.06%).
  The only structural difference is the last OOS decision bar (2026-09-23 20:00, `T` beyond
  the 4h OOS panel so no 4h limit baseline exists): blind skips bars with `T` outside the
  4h index, leader executes them from 1m (which extends past the 4h panel). Those bars have
  no forward 4h return (`r_next` NaN->0) and sub-rounding cost, so net/DD/fills are unaffected
  (28.27/11.46/2122 exact). The rate gap 0.8555 vs 0.855 is the same 5-order denominator plus
  4dp-vs-3dp rounding (7053/8244=0.85553; 7053/8249=0.85501->0.855).

## C. Look-ahead audit

### `v103_flow_short_horizon.py` — no look-ahead found

- Data: `v92.load_asset` (spot prefix strictly before first USD-M bar) + `v92.features`
  (past closes, ewm `adjust=False`, daily SMA/ribbon + funding via `merge_asof backward`,
  volume z past 180) + `flow_features` on the same closed 4h bar (`qv`, taker, trades,
  high/low/close, causal rolling). Pass.
- Labels/embargo: `y6/y18` from the grid's own opens/vol42 (`:77-80`); per-horizon filter
  `t<cutoff and t+(h+1)*4h<cutoff`, `cutoff=A-78*4h` (`:89,94`); `y` (v92 H=42) reused only
  for the `ic_y42` diagnostic. Pass.
- HGB hygiene: `base` excludes `y` and every `y*` label (`:121`), so the two horizon models
  train/predict on 36 features only; `pred=mean`; ICs are OOS spearman. Pass.
- Weights/vol/execution: `v94.weights_ls`, `v94.vol_target_scale` (trailing, `W.shift(2)`,
  cap 2, NaN->1), `v92.simulate` (2-bar delay, fee+funding), `v92.stats` yearly cuts —
  same timing as audited v92/v94. Blend scales each leg with its own trailing vol before
  combining and uses scale 1.0 after (`:144-147`); all scale inputs lagged. Pass.

### `v104_candidate.py` — no look-ahead found (one carry-timing note, as in v99/v93)

- Books: retrains audited v92/v94/v103 paths over the same 5 anchors (`:42-50`); each leg's
  own trailing 20% scale applied before `0.5*v96 + 0.5*v103scaled` (`:52-56`). All lagged. Pass.
- Wrapper: `realized=0.8*(books.shift(2)*ret1).sum + 0.6*carry.shift(1)` trailing 360/min-120,
  `s=min(0.15/vol,2)` NaN->1 (`:88-90`); model leg `Wt=0.8*s*books` earns `o[t+2]/o[t+1]-1`
  with fee+funding on scaled turnover; carry leg `carry_exp[t]*carry[t]` with
  `|diff|*2*0.0004/1.2`, first diff 0 (`:96-106`). The carry-vs-model delay asymmetry is the
  same labelled execution assumption as v99/v93, not leakage. Pass.
- Hidden execution: orders `dW>1e-9` at `t>=HIDDEN` (`:65`), `T=t+4h` (`:66`), limit at T open,
  through-test on strictly later 1m bars `[T+2,T+14]` (`:73`), fallback T+15m (`:77`), both at
  or after T — correct 1-bar delay, no future beyond the execution bar. Strict through,
  missing-T taker default. Pass with the B.2 counting note.

### `v105_flow_ablation.py` — no look-ahead found

- Primary reuses `v103.build/train_predict` with `noflow` feats (v92 only), same embargo/labels,
  LS book + 20% vol (`:41-45`). Pass.
- Secondary sets `v92.FEATS=allf` (36 feats) then `v92.train_predict` (102-bar embargo, y42)
  and `v92.weights_from(..., "model")` + `v92.vol_target_scale` (`:46-54`); all inputs
  contemporaneous at `t`, training rows satisfy `t+43*4h<cutoff`. Pass.

## D. Manifest notes

- `v103/result_manifest.json`: track B, `rejected`, `live_approved:false`, pending-audit flags.
  Normal monthly 2.667%, worst DD 24.59%, fills 10300/60mo; blend monthly 2.619%, worst DD 17.94%.
- `v104/result_manifest.json`: track A, `rejected`, `live_approved:false`. Normal monthly 2.44%,
  worst DD 15.79%, fills 10431/60mo; hidden strict net 28.27% / DD 11.46% / maker 0.855 / 8249 orders.
- `v105/result_manifest.json`: track C, `rejected`, `live_approved:false`. Primary (no-flow LS)
  monthly 2.166%, worst DD 23.43%, fills 10221/60mo; secondary monthly 2.502%, worst DD 24.64%.

## E. Verdict

- v103, v104 (all scenarios), v105 (both legs) blind reproductions are bit-exact on train rows,
  ICs (y6/y18/y42), yearly normal/fee/execution nets, DDs, and fills. The only numeric gap is
  5 hidden-execution orders (8244 vs 8249) with identical makers (7053) and identical net/DD,
  fully attributed to the last-bar counting convention plus 4dp/3dp rounding.
- No look-ahead found in flow features, short-horizon labels/embargo, LS/LO weights, vol targets,
  v99-wrapper timing, 1m execution, or ablations. The carry-leg contemporaneous timing
  (`exposure[t]*carry[t]` vs 2-bar model delay) is carried as the labelled execution assumption
  from v93/v99. Audit complete; leader files untouched.
