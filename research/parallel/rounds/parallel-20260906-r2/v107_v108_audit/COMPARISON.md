# v107 + v108 blind audit — COMPARISON.md (Part B)

Blind replication was saved BEFORE opening `v107/` / `v108/` (see `replication.json`,
`predictions_v103.csv`, `predictions_v107.csv`, `equity_v107_LS_normal.csv`,
`equity_v107_LS_fee_stress.csv`, `equity_v107_LS_execution_stress.csv`,
`equity_v107_blend_*.csv`, `equity_v108_k{1,3,6}_*.csv` in this folder).
Audit scope: `v107/v107_intrabar.py`, `v107/v107_result.json`, `v107/result_manifest.json`,
`v107/run.log`, `v108/v108_rebalance_freq.py`, `v108/v108_result.json`
(note: v108 JSON carries the provisional label `"version": "v106"`),
`v108/result_manifest.json`, `v108/run.log`
(plus `v103/v103_flow_short_horizon.py`, `v92/v92_pooled_hgb_vt.py`,
`v94/v94_long_short_ensemble.py`, `v96/v96_blend.py` as shared base).
No leader files were edited. All writes are under `v107_v108_audit/` + `tests/test_v107_v108_audit.py`.

## A. Number comparison (blind audit vs leader)

### v107 (A1): exact match on ICs, train rows, LS all scenarios, blend all scenarios

Per-anchor IC + train rows (blind vs leader `ic`):

| anchor | train h6 b/l | train h18 b/l | IC y6 b/l | IC y18 b/l |
|---|---|---|---|---|
| 2021-09-24 | 33388/33388 | 33328/33328 | 0.061/0.061 | 0.0676/0.0676 |
| 2022-09-24 | 44338/44338 | 44278/44278 | 0.0236/0.0236 | 0.0507/0.0507 |
| 2023-09-24 | 55288/55288 | 55228/55228 | 0.0633/0.0633 | 0.0909/0.0909 |
| 2024-09-24 | 66268/66268 | 66208/66208 | 0.0256/0.0256 | 0.0442/0.0442 |
| 2025-09-24 | 77218/77218 | 77158/77158 | 0.0646/0.0646 | 0.1131/0.1131 |

Yearly LS normal (blind vs leader `primary_long_short.normal.yearly`):

| anchor | net % b/l | DD % b/l | fills b/l |
|---|---|---|---|
| 2021-09-24 | 25.27/25.27 | 17.99/17.99 | 1752/1752 |
| 2022-09-24 | -1.44/-1.44 | 25.91/25.91 | 2145/2145 |
| 2023-09-24 | 67.47/67.47 | 10.28/10.28 | 2159/2159 |
| 2024-09-24 | 47.93/47.93 | 14.75/14.75 | 2144/2144 |
| 2025-09-24 | 45.30/45.30 | 14.62/14.62 | 2031/2031 |

Fee-stress yearly: 21.35/21.35, -4.88/-4.88, 61.52/61.52, 42.47/42.47, 38.99/38.99 exact;
execution-stress yearly: 16.62/16.62, -9.02/-9.02, 54.38/54.38, 35.93/35.93, 31.49/31.49 exact;
DDs and fills exact in both stresses.

Yearly 0.5*v96 + 0.5*v107 blend (blind vs leader `secondary_blend_v96`):
normal 14.77/14.77, 12.81/12.81, 68.25/68.25, 49.34/49.34, 38.81/38.81;
fee 12.28/12.28, 9.94/9.94, 63.82/63.82, 44.92/44.92, 34.11/34.11;
execution 9.23/9.23, 6.46/6.46, 58.43/58.43, 39.58/39.58, 28.46/28.46;
DDs and fills exact (normal fills 1758/1758, 2176/2176, 2179/2179, 2162/2162, 2099/2099).

Base v103 check inside blind (k=6 leg): ICs 0.0602/0.0651, 0.0258/0.0551, 0.054/0.0788,
0.0298/0.0579, 0.0611/0.112 and LS nets 24.17/2.03/66.52/50.52/52.77 all bit-exact
vs `v103/v103_result.json` and the audited `v103_v105_audit/replication.json`.

No IC (>0.01) or return (>1pp) threshold exceeded for v107.

### v108 (A2): exact match on k=1, k=3, k=6 in all three scenarios

k=1 primary every-4h (blind vs leader `primary_every_4h`):
normal 30.79/30.79, 5.94/5.94, 43.27/43.27, 52.64/52.64, 33.07/33.07;
fee 18.13/18.13, -4.28/-4.28, 28.24/28.24, 36.17/36.17, 16.87/16.87;
execution 4.02/4.02, -15.68/-15.68, 11.64/11.64, 18.06/18.06, -0.64/-0.64;
DDs and fills exact (normal fills 1933/1933, 2183/2183, 2183/2183, 2162/2162, 2093/2093).

k=3 secondary every-12h (blind vs leader `secondary_every_12h`):
normal 35.41/35.41, 7.83/7.83, 46.16/46.16, 50.90/50.90, 37.60/37.60;
fee 28.55/28.55, 2.25/2.25, 38.32/38.32, 42.23/42.23, 29.28/29.28;
execution 20.47/20.47, -4.33/-4.33, 29.09/29.09, 32.09/32.09, 19.57/19.57;
DDs and fills exact (normal fills 1830/1830, 2159/2159, 2163/2163, 2140/2140, 2064/2064).

k=6 reference daily v103 (blind vs leader `reference_daily_v103`):
normal 24.17/24.17, 2.03/2.03, 66.52/66.52, 50.52/50.52, 52.77/52.77;
fee and execution rows also bit-exact vs `v103/v103_result.json`
fee/execution stresses (20.24/-1.45/60.45/45.08/46.51 and 15.50/-5.64/53.18/38.56/39.04).

Label note: `v108/v108_result.json` has `"version": "v106"` (provisional label per
`v108/result_manifest.json:process_note`); the numbers under `primary_every_4h`,
`secondary_every_12h`, `reference_daily_v103` are the v108 contract and match blind exactly.

No threshold exceeded anywhere in v107/v108.

## B. Why blind matched (no PnL-relevant difference)

- 1h series: blind filters spot rows with `open_time < first USD-M 1h`, concats, dedups
  on `open_time`, sorts; leader `load_1h` (`v107_intrabar.py:47-55`) does
  `pre[pre.open_time < h.open_time.min()]`, same concat/dedup/sort. Spot max is exactly
  1h before the first perp bar for all five majors, so the prefix is a clean prepend.
- 1h formulas: blind `ih_features` and leader `intrabar` (`:58-70`) coincide:
  `r1=diff(log close)`, `sd168=rolling(168,min84).std`, `tbr=clip(taker/quote.clip(1),0,1)`,
  `ih_last=r1/sd`, `ih_jump=|r1|.rolling(4).max/sd`, `ih_rv=rolling(24).std/sd`,
  `ih_ac=rolling(72).corr(shift1)`, `ih_tbr=tbr-rolling(24).mean`,
  `ih_up=(r1>0).where(r1.notna()).rolling(24).mean-0.5`. Blind adds `inf->NaN`;
  no inf occurs (sd168>0 on majors), so no numeric effect.
- 1h->4h mapping: blind computes `t1=t+3h` then left-joins 1h `open_time==t1`;
  leader builds `t=h.open_time-3h` then merges on `["t","sym"]` left (`:63,81`).
  Algebraically identical: 4h T <-> 1h T+3h. Both are left joins (missing -> NaN,
  HGB NaN-native). Train rows agree for every anchor/horizon, so join, embargo
  (78 bars, per-horizon `t+(h+1)*4h<cutoff`), HGB params, and NaN handling coincide.
- Weights/vol/execution: blind reimplements audited `v94.weights_ls` / `vol_target_scale`
  / `v92.simulate`; leader calls them via `v103.evaluate` (`:99,110`) and
  `weights_ls_every` with an `np.allclose(ref, v94.weights_ls)` guard
  (`v108_rebalance_freq.py:57-58`). Nets/DDs/fills agree bit-exact on all books.
- v96 blend provenance (no PnL effect): leader retrains v92/v94/v103 inside
  `v107_intrabar.py:100-109` (deterministic HGB); blind reuses the audited OOS CSVs
  (`v92_audit/predictions_5asset.csv`, `v93_v94_audit/predictions_v94.csv`) with the
  leader `vol_target_scale` for the v96 leg and its own v107 OOS for the v107 leg.
  Blend nets agree exactly; blend uses scale 1.0 after (`evaluate(...,scale=1.0)`
  vs blind `simulate(...,1.0)`).
- v108 k-variants: blind `weights_ls(...,k)` with `arange%k==0` + ffill matches leader
  `weights_ls_every(every)` (`:49-50`); k=6 asserts equal to `v94.weights_ls`.
  Own 20% vol target per k, `v92.SCEN` costs. All exact.

## C. Look-ahead audit

### `v107_intrabar.py` — no look-ahead found

- Data: spot 1h prefix strictly before the first USD-M 1h bar (`:54`), dedup/sort;
  same convention as audited v92/v103 4h/1d prefix. No future rows enter the prefix. Pass.
- 1h features: all causal rolling on closed 1h bars (`diff`, `rolling().std/max/mean/corr`,
  `shift(1)`); `sd168` min_periods 84 is a warmup rule, not future data. Pass.
- 1h->4h mapping (focus): 4h T takes the 1h bar opening at T+3h, i.e. the last hourly
  sub-bar `[T+3h,T+4h)` which closes exactly at the 4h `close_time` (`t=open_time-3h`
  construction `:63` + left merge `:81`). At the 4h close all six values are known;
  nothing beyond the 4h close is used. A T+4h mapping would leak the next hour;
  the code does not do that. Strictly-later 1m-style through-test is not needed here
  because the 1h close equals the 4h close. Pass.
- Labels/embargo/HGB: reuses audited `v103.build/train_predict` (y6/y18 from own
  opens/vol42, `cutoff=A-78*4h`, per-horizon `t+(h+1)*4h<cutoff`, 36+6 feats only,
  `pred=mean`, OOS spearman). Train rows identical to blind. Pass.
- Weights/vol/execution/blend: `v94.weights_ls` (daily k=6), `v94.vol_target_scale`
  (trailing, `W.shift(2)`, cap 2, NaN->1), `v92.simulate` (2-bar delay, fee+funding),
  blend scales each leg with its own trailing vol before combining with scale 1.0
  (`:106-110`); all scale inputs lagged. Pass.
- Coverage 0.998/1.0 (`run.log:1`) is rolling-warmup NaN, not a join gap; HGB is
  NaN-native and train rows match, so no selection bias. Pass.

### `v108_rebalance_freq.py` — no look-ahead found

- Predictions unchanged: rebuilds the v103 panel and calls `v103.train_predict`
  per anchor (`:54-56`); no new features. Pass.
- Rebalance: `weights_ls_every` is `v94.weights_ls` with only the `keep` mask
  parameterised (`arange%every==0`, ffill `:49-50`); k=1 keeps every 4h bar,
  k=3 every 12h, k=6 asserts bit-equal to daily v103. Rebalance uses only the
  contemporaneous `pred/rib/vol42` at `t`; ffill carries past weights forward. Pass.
- Vol/execution: own trailing 20% vol target per k and `v103.evaluate` (= `v92`
  costs/scenarios, 2-bar delay, funding). All lagged. Pass.

## D. Manifest notes

- `v107/result_manifest.json`: track B, `rejected`, `live_approved:false`, pending-audit flags.
  Normal monthly 2.517%, worst DD 25.91%, fills 10231/60mo; blend monthly 2.544%, worst DD 18.12%.
- `v108/result_manifest.json`: track C, `rejected`, `live_approved:false`, pending-audit flags.
  Primary (k=1) monthly 2.351%, worst DD 19.98%, fills 10554/60mo;
  secondary (k=3) monthly 2.512%, worst DD 17.12%; reference daily v103 monthly 2.667%.
  `process_note` documents the provisional v106 folder/label rename with unchanged
  result bytes (JSON still says `"version": "v106"`); hash recorded in manifest.
  No parameter changed after seeing results per that note; numbers reproduce blind exactly.

## E. Verdict

- v107 (ICs y6/y18, LS normal/fee/execution, v96 blend normal/fee/execution) and v108
  (k=1,3,6 x normal/fee/execution) blind reproductions are bit-exact on train rows,
  ICs, yearly nets, DDs, and fills. The only non-numeric item is the v108 provisional
  `"v106"` version label, explained by the manifest rename note.
- No look-ahead found in the 1h prefix, causal 1h rolling formulas, the T->T+3h
  1h->4h mapping, short-horizon labels/embargo, LS weights at any rebalance frequency,
  vol targets, or v96-blend timing. Audit complete; leader files untouched.
