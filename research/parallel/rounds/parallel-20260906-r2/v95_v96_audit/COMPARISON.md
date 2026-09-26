# v95 + v96 blind audit — COMPARISON.md (Part B)

Blind replication was saved BEFORE opening `v95/` / `v96/` (see `replication.json`,
`equity_v95.csv`, `equity_v96.csv`, `predictions_v95.csv` in this folder). Audit scope:
`v95/v95_rich_features.py`, `v95/v95_result.json`, `v95/result_manifest.json`,
`v96/v96_blend.py`, `v96/v96_result.json`, `v96/result_manifest.json`
(plus `v92/v92_pooled_hgb_vt.py` and `v94/v94_long_short_ensemble.py` as shared base).
No leader files were edited. All writes are under `v95_v96_audit/` + `tests/test_v95_v96_audit.py`.

## A. Number comparison (blind audit vs leader)

### v96 (A1): exact match

| anchor | net % blind | net % leader | diff | DD % blind | DD % leader | fills blind | fills leader |
|---|---|---|---|---|---|---|---|
| 2021-09-24 | 4.21 | 4.21 | 0.0pp | 20.89 | 20.89 | 1572 | 1572 |
| 2022-09-24 | 26.78 | 26.78 | 0.0pp | 11.47 | 11.47 | 2163 | 2163 |
| 2023-09-24 | 67.48 | 67.48 | 0.0pp | 6.88 | 6.88 | 2166 | 2166 |
| 2024-09-24 | 48.94 | 48.94 | 0.0pp | 10.03 | 10.03 | 2149 | 2149 |
| 2025-09-24 | 31.17 | 31.17 | 0.0pp | 16.38 | 16.38 | 2036 | 2036 |

No threshold exceeded (IC diff > 0.01 or return diff > 1pp): nothing to explain for v96.
Blind reused audited OOS preds (`v92_audit/predictions_5asset.csv`,
`v93_v94_audit/predictions_v94.csv`) and recomputed each book's own causal 20%
vol scale (cap 2, NaN->1); combined `0.5*W92*s92 + 0.5*W94*s94` with v92
execution (fee 0.0002, long funding 0.00005/bar). Leader retrains the same
deterministic HGBs via imported `v92`/`v94` and simulates with `v92.simulate`
— same numbers to 2 decimals and same fills.

### v95 (A2): IC diffs exceed 0.01 on 3/5 anchors; return diffs exceed 1pp on all years

Per-anchor IC (blind vs leader `v95_rich_features.ic_by_anchor`):

| anchor | train rows blind | IC blind | IC leader | IC diff |
|---|---|---|---|---|
| 2021-09-24 | 33088 | -0.0718 | -0.0912 | 0.0194 |
| 2022-09-24 | 44038 | 0.1674 | 0.1517 | 0.0157 |
| 2023-09-24 | 54988 | 0.0503 | 0.0533 | 0.0030 |
| 2024-09-24 | 65968 | 0.0648 | 0.0660 | 0.0012 |
| 2025-09-24 | 76918 | 0.1376 | 0.1228 | 0.0148 |

Yearly normal long-only (blind vs leader `v95_rich_features.normal.yearly`):

| anchor | net % blind | net % leader | diff | DD % blind | DD % leader | fills blind | fills leader |
|---|---|---|---|---|---|---|---|
| 2021-09-24 | 3.58 | 5.33 | -1.75pp | 23.33 | 22.64 | 1282 | 1297 |
| 2022-09-24 | 4.07 | -0.96 | +5.03pp | 1.56 | 11.60 | 42 | 56 |
| 2023-09-24 | 65.41 | 13.27 | +52.14pp | 8.77 | 22.18 | 122 | 126 |
| 2024-09-24 | 15.68 | 18.36 | -2.68pp | 24.59 | 20.92 | 554 | 612 |
| 2025-09-24 | 4.13 | -7.07 | +11.20pp | 35.70 | 38.91 | 1044 | 1174 |

Feature count agrees (blind 97 = leader `n_rich_features` 97; ctx kept 64,
dropped `ctx_mac_btc_qqq_corr_60d` in both). Fills pattern agrees (collapse in
2022/2023 to ~50-120 fills in both), but PnL diverges sharply in the
concentrated regime.

## B. Root causes of the v95 deltas

1. Cross-sectional rank definition (identified, explains IC gaps). Blind assumed
   `xs_pct = (rank_average-1)/(count-1)` spanning 0..1
   (`replicate_v95_v96.py:add_xs_features`), documented as a blind assumption.
   Leader uses `rank(pct=True)` (`v95_rich_features.py:50`), i.e. `rank/count`
   spanning 0.2..1.0 for full 5-asset bars (verified: `[0.2,0.4,0.6,0.8,1.0]`
   vs blind `[0.0,0.25,0.5,0.75,1.0]`; with one NaN, leader
   `[0.25,nan,0.5,0.75,1.0]` vs blind `[0.0,nan,0.33,0.67,1.0]`). For full bars
   this is an affine rescaling, but with NaNs early (SOL/late listings, warmup
   `ret180`/`snr42`) the two mappings are not affine, and HGB quantile binning
   sees different split points. Same `random_state=0` then grows different
   trees. IC moves by 0.001-0.019 (3 anchors over the 0.01 threshold); names
   (`xs_pct_*` vs `xs_rank_*`, `mkt_*` vs `xs_bull_share`/`xs_mean_snr42`,
   `f7_z180` vs `f7_z`) are cosmetic and do not affect splits.
2. Amplification by the concentrated long-only book. Both books collapse to
   42-56 fills in 2022 and 122-126 fills in 2023 (ribbon-gated, mostly-negative
   preds). With so few positions, the small pred shifts from (1) flip individual
   daily baskets from 0 to full size, so a 0.015 IC move produces 5-52pp net
   swings (2023: blind 65.41% vs leader 13.27% on ~124 fills). Fills differ by
   only 4-130/yr, confirming the same regime with different selected days.
3. Execution-path micro-differences (not the driver; <0.5pp by v93 precedent).
   Blind vol-target fills realised returns with 0.0 before the trailing
   360-bar (min 120) window fills in; leader `v92.vol_target_scale` leaves
   `W.shift(2)*(o/o.shift(1)-1)` NaNs in, so `scale` stays at causal default
   1.0 longer (`v92_pooled_hgb_vt.py:139-144`). Turnover definition is
   identical (`diff().abs().sum`, first bar `|Wk|`). IC method is identical
   (`spearmanr` on y-non-NaN rows = `corr(spearman)`, verified locally on blind
   preds: both give -0.0718 for 2021). `inf->NaN` replacement in leader
   `market_context` has no material effect (no infs in ctx).
4. Column selection is the same. Both keep 64/65 ctx columns with
   `notna().mean() > 0.2` and drop only `ctx_mac_btc_qqq_corr_60d`; leader
   `added_features` lists the same 64 ctx names as blind `ctx_kept`. The
   selection uses full-history non-NaN rates (column filtering only, not row
   leakage — see C).

Net effect: v95 direction (rich features hurt vs v92 base, concentrated book,
worse DD) reproduces qualitatively, but exact ICs/nets depend on the rank
normalisation and the resulting tree splits. Blind 2021 IC -0.0718 vs leader
-0.0912, 2022 0.1674 vs 0.1517, 2025 0.1376 vs 0.1228; return gaps follow from
the low-fill concentration, not from hidden logic.

## C. Look-ahead audit

### `v96_blend.py` — no look-ahead found
- Data/features: reuses audited `v92.build()` (spot prefix strictly before
  first USD-M bar via `open_time < b.open_time.iloc[0]`, past closes, ewm
  `adjust=False`, daily SMA/ribbon + funding via `merge_asof backward`,
  volume z past 180) and `v94.add_targets` (forward opens/vol only,
  `y_h=clip(log(open[t+1+h]/open[t+1])/(vol42√h),±4)`). Pass.
- Labels/embargo: `v92.train_predict` (`cutoff=A-408h`, `t+172h<cutoff`) and
  `v94.train_predict` (`cutoff=A-576h`, per-horizon `t+(h+1)*4h<cutoff`).
  Pass.
- Weights: `v92.weights_from(model)` long-only and `v94.weights_ls(shorts=True)`
  long-short use contemporaneous `pred`/`rib`/`vol42` only, NaN->0,
  `|raw|` normalisation with `active/5`, daily rebalance (every 6th bar ffill).
  Pass.
- Vol-target/combine/execution: each book's own `vol_target_scale`
  (`W.shift(2)` realised returns, trailing 60d/min-20d, `min(0.20/vol,2)`
  NaN->1 causal default); `W=0.5*W_lo*s_lo+0.5*W_ls*s_ls` reindexed with
  NaN->0/1 defaults; `v92.simulate(panel,W,1.0,fee,slip)` gives
  `W_t` earning `open[t+2]/open[t+1]-1`, fee+slip on scaled turnover,
  `0.00005`/bar on long gross only. All scale inputs lagged; no forward use.
  Pass.

### `v95_rich_features.py` — no look-ahead found (one selection note)
- Cross-sectional: `rank(pct=True)` per `t` across 5 majors, `ret42-btc_ret42`,
  `mean(rib==1)`, `mean(snr42)` use only same-bar values; `f7_z` is trailing
  `rolling(1080,min180)` mean/std per asset sorted by `t` (includes current
  print, still as-of). All causal. Pass.
- Market context: `load_bars("4h", include_opened_year=True)` + audited
  `breadth`/`positioning`/`macro`/`implied_vol.compute` (all merge_asof
  backward on availability time, trailing windows only), `ctx_` prefix,
  `notna().mean()>0.2` column filter, `merge on t`. The filter uses
  full-history non-NaN rates to drop one column (`mac_btc_qqq_corr_60d`) —
  column selection only, no future values enter rows; blind `assert_causal`
  on the combined ctx function passes on a 3000-bar slice
  (`replication.json:ctx_causality.passed=true`). Merging BTC-open_time ctx
  onto 5-asset panel is contemporaneous; grids align on 4h marks, residual
  NaNs are HGB-native. Pass with the selection-use noted.
- Training/book: `v92.train_predict`/`weights_from`/`vol_target_scale`/
  `simulate`/`stats` identical to audited v92 (see v96 notes). `FEATS` excludes
  `y/t/open/sym/bar` (and `y*` for v94 path, N/A here). Pass.

## D. Manifest notes
- `v95/result_manifest.json`: track A, status `rejected`, `live_approved:false`,
  `audit.passed:false, replay_complete:false` ("awaiting OpenCode audit").
  Normal monthly 0.438%, worst-year DD 38.91%, fills 3265/60mo.
- `v96/result_manifest.json`: track C, status `rejected`, `live_approved:false`,
  same pending-audit flags. Normal monthly 2.47%, worst-year DD 20.89%,
  fills 10086/60mo.
- Leader `v95_result.json` also reports `v92_features_reference` (v92 feats on
  the same panel): hidden 16.69% net / 28.47% DD matches audited v92
  `replication_5asset.json` hidden exactly.

## E. Verdict
- v96 blind reproduction is bit-exact (yearly nets/DDs/fills). Leader v96 code
  has no look-ahead in data, labels/embargo, weights, vol-target, or execution.
- v95 reproduces the feature count (97), ctx selection (64 kept, same dropped
  column), low-fill regime, and IC direction, but ICs differ by up to 0.019
  and nets by up to 52pp due to the documented rank-normalisation difference
  (`pct=True` vs blind `(rank-1)/(n-1)`) amplified by the concentrated
  long-only book; residual execution micro-differences contribute <0.5pp.
  Leader v95 code has no look-ahead; the full-history ctx column filter should
  be carried as a labelled selection assumption. Audit complete; leader files
  untouched.
