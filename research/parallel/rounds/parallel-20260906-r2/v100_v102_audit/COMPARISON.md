# v100 + v101 + v102 blind audit — COMPARISON.md (Part B)

Blind replication was saved BEFORE opening `v100/` / `v101/` / `v102/` (see
`replication.json`, `predictions_v100_primary1200.csv`,
`predictions_v100_sens300.csv`, `predictions_v101_primary_w1.csv`,
`predictions_v101_sens_w05.csv`, `predictions_v102.csv`,
`equity_v100_primary1200.csv`, `equity_v100_sens300.csv`,
`equity_v101_primary_w1.csv`, `equity_v101_sens_w05.csv`,
`equity_v102_neutral.csv`, `equity_v102_blend.csv`,
`equity_v99_leader_convention.csv` in this folder).
Audit scope: `v100/v100_offset_rows.py`, `v100/v100_result.json`,
`v100/result_manifest.json`, `v101/v101_broad_train.py`,
`v101/v101_result.json`, `v101/result_manifest.json`,
`v102/v102_xs_neutral.py`, `v102/v102_result.json`,
`v102/result_manifest.json` (plus `v92/v92_pooled_hgb_vt.py`,
`v94/v94_long_short_ensemble.py`, `v99/v99_candidate.py` as shared base).
No leader files were edited. All writes are under `v100_v102_audit/` +
`tests/test_v100_v102_audit.py`.

## A. Number comparison (blind audit vs leader)

### v100 (A1, phase-shifted extra training rows): exact match

Per-anchor IC + train rows (blind vs leader `primary_leaf_1200.ic`):

| anchor | train blind | train leader (0/1/2/3) | IC blind | IC leader | diff |
|---|---|---|---|---|---|
| 2021-09-24 | 84393 | 33088/17101/17101/17103 (=84393) | 0.0831 | 0.0831 | 0 |
| 2022-09-24 | 128193 | 44038/28051/28051/28053 (=128193) | -0.0009 | -0.0009 | 0 |
| 2023-09-24 | 171993 | 54988/39001/39001/39003 (=171993) | 0.1265 | 0.1265 | 0 |
| 2024-09-24 | 215913 | 65968/49981/49981/49983 (=215913) | 0.1379 | 0.1379 | 0 |
| 2025-09-24 | 259713 | 76918/60931/60931/60933 (=259713) | 0.1838 | 0.1838 | 0 |

Sensitivity leaf 300 ICs: 0.0578 / 0.0018 / 0.0949 / 0.1444 / 0.2131 blind,
identical to leader `sensitivity_leaf_300.ic`.

Yearly normal primary (blind vs leader `primary_leaf_1200.normal.yearly`):

| anchor | net % blind | net % leader | diff | DD % blind | DD % leader | fills blind | fills leader |
|---|---|---|---|---|---|---|---|
| 2021-09-24 | -8.64 | -8.64 | 0 | 22.88 | 22.88 | 1323 | 1323 |
| 2022-09-24 | 29.80 | 29.80 | 0 | 14.02 | 14.02 | 1567 | 1567 |
| 2023-09-24 | 44.68 | 44.68 | 0 | 21.16 | 21.16 | 1624 | 1624 |
| 2024-09-24 | 52.12 | 52.12 | 0 | 12.18 | 12.18 | 1774 | 1774 |
| 2025-09-24 | 29.32 | 29.32 | 0 | 21.86 | 21.86 | 1247 | 1247 |

Sensitivity yearly (-0.12 / 46.10 / 37.02 / 52.64 / 30.45) likewise exact.
No threshold exceeded.

### v101 (A2, extra assets training only): exact match

Per-anchor (blind vs leader `primary_w1.ic`):

| anchor | train blind (maj/ext) | train leader maj/ext | IC blind | IC leader | diff |
|---|---|---|---|---|---|
| 2021-09-24 | 70209 (33088/37121) | 33088/37121 | 0.1115 | 0.1115 | 0 |
| 2022-09-24 | 109629 (44038/65591) | 44038/65591 | -0.0166 | -0.0166 | 0 |
| 2023-09-24 | 149049 (54988/94061) | 54988/94061 | 0.1371 | 0.1371 | 0 |
| 2024-09-24 | 188577 (65968/122609) | 65968/122609 | 0.1267 | 0.1267 | 0 |
| 2025-09-24 | 227997 (76918/151079) | 76918/151079 | 0.1678 | 0.1678 | 0 |

Sensitivity w0.5 ICs (0.1082 / -0.0329 / 0.1329 / 0.1162 / 0.1706) identical.

Yearly normal primary (blind vs leader `primary_w1.normal.yearly`):

| anchor | net % blind | net % leader | diff | DD % blind | DD % leader | fills |
|---|---|---|---|---|---|---|
| 2021-09-24 | -2.66 | -2.66 | 0 | 23.72 | 23.72 | 1257/1257 |
| 2022-09-24 | 70.22 | 70.22 | 0 | 11.10 | 11.10 | 1363/1363 |
| 2023-09-24 | 70.51 | 70.51 | 0 | 20.65 | 20.65 | 1487/1487 |
| 2024-09-24 | 75.28 | 75.28 | 0 | 7.97 | 7.97 | 1869/1869 |
| 2025-09-24 | 5.74 | 5.74 | 0 | 29.96 | 29.96 | 1238/1238 |

Sensitivity yearly (4.43 / 44.20 / 76.60 / 61.34 / 13.20) exact.
No threshold exceeded.

### v102 (A3, market-neutral + blend): exact match on ICs, nets, DDs, fills

Per-anchor (blind vs leader `ic`):

| anchor | train blind | train leader | IC pooled b/l | IC per-bar b/l |
|---|---|---|---|---|
| 2021-09-24 | 32619 | 32619 | -0.0138 / -0.0138 | 0.012 / 0.012 |
| 2022-09-24 | 43569 | 43569 | 0.0485 / 0.0485 | 0.0245 / 0.0245 |
| 2023-09-24 | 54519 | 54519 | 0.0677 / 0.0677 | 0.0187 / 0.0187 |
| 2024-09-24 | 65499 | 65499 | 0.0469 / 0.0469 | 0.053 / 0.053 |
| 2025-09-24 | 76449 | 76449 | -0.0196 / -0.0196 | -0.0116 / -0.0116 |

Pooled 5y blind 0.0299, per-bar 0.0195 (leader has no 5y field; per-anchor exact).

Yearly normal neutral (blind vs leader `normal.neutral.yearly`):

| anchor | net % b/l | DD % b/l | fills b/l |
|---|---|---|---|
| 2021-09-24 | -2.62 / -2.62 | 10.46 / 10.46 | 2080/2080 |
| 2022-09-24 | 10.75 / 10.75 | 12.91 / 12.91 | 2155/2155 |
| 2023-09-24 | 10.83 / 10.83 | 8.13 / 8.13 | 2174/2174 |
| 2024-09-24 | -0.70 / -0.70 | 10.76 / 10.76 | 2168/2168 |
| 2025-09-24 | -2.37 / -2.37 | 11.25 / 11.25 | 2181/2181 |

Yearly normal blend (blind vs leader `normal.blend.yearly`):

| anchor | net % b/l | DD % b/l | fills b/l |
|---|---|---|---|
| 2021-09-24 | 8.12 / 8.12 | 9.98 / 9.98 | 2080/2080 |
| 2022-09-24 | 27.57 / 27.57 | 8.80 / 8.80 | 2186/2186 |
| 2023-09-24 | 43.38 / 43.38 | 5.75 / 5.75 | 2189/2189 |
| 2024-09-24 | 27.64 / 27.64 | 7.65 / 7.65 | 2185/2185 |
| 2025-09-24 | 15.36 / 15.36 | 9.51 / 9.51 | 2186/2186 |

v99 leg recomputed with leader convention matches leader `normal.v99.yearly`
(11.13 / 33.07 / 55.30 / 37.95 / 21.32) exactly, confirming the
`exposure[t]*carry[t]` convention was applied on both sides.

Correlation neutral vs v99 daily: blind 0.1061 (every-6-bar geometric daily)
vs leader 0.101 (calendar-day sums, `floor("D")`). Recomputing blind nets with
the leader day definition gives 0.1007 -> 0.101, so the gap is aggregation
definition only, not PnL. No IC (>0.01) or return (>1pp) threshold exceeded.

## B. Why blind matched (method notes)

- v100 phase construction: blind required 4 consecutive 1h bars exactly 1h
  apart with first `hour%4==phase`; leader groups by
  `(open_time-phase).floor("4h")+phase` with `n==4` and `open_time==key`
  (`v100_offset_rows.py:35-45`). Both enforce the same complete aligned
  groups; train-row totals agree for every anchor, and daily/funding joins use
  the same `v92.load_asset` d/f via `v92.features` with same-phase BTC context.
- v101 extras: spec order ADA..FIL ids 5..17; leader `EXTRA` tuple identical
  (`v101_broad_train.py:29`). Both use `v92.load_asset` (spot prefix files do
  not exist for extras, so leader and blind nospot paths coincide) and BTC
  context from the v92 BTC panel. Sample weights 1 / w are passed as HGB
  `sample_weight`. Train-row splits (majors/extras) agree exactly.
- v102: `y_xs` NaN if <2 labelled (`v102_xs_neutral.py:48-49`), `xs_c` via
  same-bar mean, HGB on 26+9 feats, weights double-demeaned `/sum|W|` with
  `<2 predictions -> 0` and every-6th-bar ffill (`:65-73`), 10% vol target via
  `v92.vol_target_scale(panel,W,target=0.10)`, `v92.simulate` costs, blend
  `0.75*v99+0.25*neutral` with `exposure[t]*carry[t]` (`:89-99`). Blind
  implements the same steps; all ICs/nets/DDs/fills agree.

## C. Look-ahead audit

### `v100_offset_rows.py` — no look-ahead found

- Data: 1h -> 4h aggregation uses only the 4 bars inside each group
  (open first, high max, low min, close last, close_time last, quote_volume
  sum); `n==4` + key check drops gapped/incomplete groups. No future 1h bars.
- Features/labels: calls audited `v92.features(b,d,f)` with the same daily
  (incl spot prefix) and funding files; daily/funding via `merge_asof
  backward`, ewm `adjust=False`, volume z past 180. Label from the phase
  grid's own opens/vol42. Pass.
- BTC context: same-phase BTC grid joined by `open_time` (`:57`); both sides
  known at the phase bar close. Pass.
- Embargo: reuses `v92.EMBARGO_BARS` (102) and `t+43*4h<cutoff`
  (`:63-66`), test `[A,A+365d)` on phase 0 only. Pass.
- Weights/vol/execution: `v92.weights_from(oos,"model")`,
  `v92.vol_target_scale`, `v92.simulate` with `v92.SCEN` — same causal timing
  as audited v92 (daily ffill, trailing vol, 2-bar delay, fee+funding). Pass.

### `v101_broad_train.py` — no look-ahead found

- Extras use `v92.features` unchanged with ids 5..17 in spec order and BTC
  context from the v92 BTC rows (`:33-42`); no spot files exist for extras so
  no prefix question. Pass.
- Pool mixes majors+extras only for training; test/book/vol/trading use
  majors only (`:51,65-66`). Sample weights are constants (1 / w), no future
  input. Embargo/labels/HGB/vol/execution as v92. Pass.

### `v102_xs_neutral.py` — no look-ahead found

- `add_xs`: `xs_c = c - groupby(t).mean` and `y_xs = y - same-bar mean y`
  with NaN if `<2` labelled (`:43-50`); all inputs contemporaneous at bar `t`.
  Pass.
- Training uses `y_xs.notna()` + same `t+43*4h<cutoff` embargo (`:56-57`);
  prediction uses contemporaneous 35 feats. Pass.
- `weights_neutral` double-demeans pred then raw, `fillna(0)`, zeroes bars
  with `<2` predictions, `/sum|W|`, daily ffill (`:65-73`) — contemporaneous
  only. Vol target 10% via `v92.vol_target_scale`, `v92.simulate` costs with
  long funding on long side. Pass.
- `v99_nets` rebuilds v99 through the audited `v92`/`v94`/`v99` code path with
  `carry[t]` contemporaneous (`:89,99`) and trailing vol; blend is a fixed
  0.75/0.25 per-bar combination with per-stream costs (no netting,
  conservative). Correlation uses post-hoc daily sums — reporting only. Pass.

## D. Manifest notes

- `v100/result_manifest.json`: track B, `rejected`, `live_approved:false`,
  pending-audit flags; normal monthly 2.048%, worst DD 22.88%, fills 7535/60mo.
- `v101/result_manifest.json`: track A, `rejected`, `live_approved:false`;
  normal monthly 2.798%, worst DD 29.96%, fills 7214/60mo.
- `v102/result_manifest.json`: track C, `rejected`, `live_approved:false`;
  blend monthly 1.797%, worst DD 9.98%, fills 10826/60mo; neutral monthly
  0.246%, corr 0.101.

## E. Verdict

- v100, v101, v102 blind reproductions are bit-exact on train rows, ICs
  (pooled and per-bar), yearly normal nets/DDs/fills for primary and
  sensitivity legs. The only numeric gap is the daily correlation rounding /
  day definition (0.106 vs 0.101), fully attributed and not PnL-relevant.
- No look-ahead found in phase construction, extra-asset training, xs
  targets/features, neutral weights, vol-target, execution, or blend.
  Audit complete; leader files untouched.
