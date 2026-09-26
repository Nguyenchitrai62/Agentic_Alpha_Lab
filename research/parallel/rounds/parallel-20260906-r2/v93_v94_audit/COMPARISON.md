# v93 + v94 blind audit — COMPARISON.md (Part B)

Blind replication was saved BEFORE opening `v93/` / `v94/` (see `replication.json`,
`predictions_v94.csv`, `equity_v94.csv`, `equity_v93.csv` in this folder). Audit scope:
`v94/v94_long_short_ensemble.py`, `v94/v94_result.json`, `v94/result_manifest.json`,
`v93/v93_portfolio.py`, `v93/v93_result.json`, `v93/result_manifest.json`
(plus `v92/v92_pooled_hgb_vt.py` as the shared base). No leader files were edited.
All writes are under `v93_v94_audit/` + `tests/test_v93_v94_audit.py`.

## A. Number comparison (blind audit vs leader)

### v94 (A1): exact match

| anchor | train rows blind (18/42/84) | train rows leader | IC blind (mean vs y42) | IC leader (`ic7`) | IC diff |
|---|---|---|---|---|---|
| 2021-09-24 | 32998 / 32878 / 32668 | 32998 / 32878 / 32668 | 0.1166 | 0.1166 | 0.0 |
| 2022-09-24 | 43948 / 43828 / 43618 | 43948 / 43828 / 43618 | -0.02 | -0.02 | 0.0 |
| 2023-09-24 | 54898 / 54778 / 54568 | 54898 / 54778 / 54568 | 0.093 | 0.093 | 0.0 |
| 2024-09-24 | 65878 / 65758 / 65548 | 65878 / 65758 / 65548 | 0.0959 | 0.0959 | 0.0 |
| 2025-09-24 | 76828 / 76708 / 76498 | 76828 / 76708 / 76498 | 0.1679 | 0.1679 | 0.0 |

Yearly normal long-short (blind vs leader `long_short.normal.yearly`):

| anchor | net % blind | net % leader | diff | DD % blind | DD % leader | fills blind | fills leader |
|---|---|---|---|---|---|---|---|
| 2021-09-24 | -0.26 | -0.26 | 0.0pp | 23.75 | 23.75 | 1576 | 1576 |
| 2022-09-24 | 4.25 | 4.25 | 0.0pp | 13.39 | 13.39 | 2150 | 2150 |
| 2023-09-24 | 47.75 | 47.75 | 0.0pp | 12.31 | 12.31 | 2158 | 2158 |
| 2024-09-24 | 40.94 | 40.94 | 0.0pp | 10.54 | 10.54 | 2146 | 2146 |
| 2025-09-24 | 45.52 | 45.52 | 0.0pp | 14.39 | 14.39 | 2038 | 2038 |

No threshold exceeded (IC diff > 0.01 or return diff > 1pp): nothing to explain for v94.

### v93 (A2): nets within threshold; fills differ by construction

Yearly normal (blind vs leader `normal.yearly`):

| anchor | net % blind | net % leader | diff | DD % blind | DD % leader | fills blind | fills leader |
|---|---|---|---|---|---|---|---|
| 2021-09-24 | 6.43 | 6.84 | 0.41pp | 14.21 | 14.19 | 1668 | 1289 |
| 2022-09-24 | 36.34 | 36.35 | 0.01pp | 9.25 | 9.26 | 1924 | 1477 |
| 2023-09-24 | 68.44 | 68.46 | 0.02pp | 6.15 | 6.16 | 2082 | 1593 |
| 2024-09-24 | 42.11 | 42.11 | 0.0pp | 8.54 | 8.54 | 2139 | 1839 |
| 2025-09-24 | 12.89 | 12.89 | 0.0pp | 21.60 | 21.60 | 1604 | 1081 |

Return diffs are all < 1pp (max 0.41pp in 2021), so the spec threshold is not
exceeded. Fills differ systematically (blind higher by ~300-500/yr) for an
identified reporting reason below, not a PnL-relevant error.

## B. Root causes of the v93 deltas (all small; no IC check — leader `anchors: []`)

1. Carry-leg timing convention. Blind assumed a uniform forward convention:
   `pos_t = 0.9*s_t` earns `carry[t+1]` (book uses `carry[t-1]` realised at `t`,
   mirroring the model leg's 2-bar delay). The leader script uses
   `carry_net = carry_exposure * carry` contemporaneously (`exposure[t]*carry[t]`,
   `v93_portfolio.py:52`) while its vol book uses `carry.shift(1)`. Recomputing
   with the leader's contemporaneous timing moves blind 2021 from 6.43 to 6.52
   (verified locally); the remaining ~0.3pp is (2)+(3).
2. Early-window NaN handling. Leader's `realized` leaves the first-bar NaNs in
   (`W.shift(2)*(o/o.shift(1)-1)` with no `fillna(0)`, `v93_portfolio.py:42`),
   so `vol` stays NaN longer and `s` stays at the causal default 1.0; blind filled
   realised returns with 0.0, giving a slightly different scale path only in the
   first ~120-360 bars of 2021. Later years are unaffected (full vol window).
3. Initial carry-turnover cost. Leader fills the first `carry_exposure.diff()`
   with 0.0 (no establishment cost on the carry leg); blind filled it with
   `|pos|` (consistent with the model leg). One-off level effect in 2021 only.
4. Fills definition (explains the whole fills gap). Leader's yearly
   `stats(net[m], turn[m])` passes **model-leg turnover only**
   (`Wm.diff`, `v93_portfolio.py:47-58`); carry rescaling costs are charged in
   `carry_net` but never counted in `turn`. Blind passed
   `turn = model_turn + carry_turn`, so every carry-rescale bar adds a "fill".
   Recomputing model-turn-only fills gives 1290 vs leader 1289 in 2021 (1-bar
   edge from (2)); PnL is unaffected.
5. Weight source. Blind built `W` from the saved audited v92 replication
   (`v92_audit/predictions_5asset.csv` + v92 long-only formula); the leader
   retrains via imported `v92.train_predict` inside `v93_portfolio.py:36`.
   Both are the same deterministic HGB pipeline, so this contributes ~0 after
   (1)-(3); it is noted for provenance, not as an error.

Net effect: 2022-2025 nets agree to <= 0.02pp and DDs to <= 0.01pp; 2021 agrees
to 0.41pp once the documented timing/default conventions are accounted for.

## C. Look-ahead audit

### `v94_long_short_ensemble.py` — no look-ahead found
- Data/features: reuses audited `v92.build()` (spot prefix strictly before first
  USD-M bar, past closes, ewm `adjust=False`, daily SMA/ribbon + funding via
  `merge_asof backward`, volume z past 180). Pass.
- Labels/embargo: `add_targets` computes
  `y_h = clip(log(open[t+1+h]/open[t+1])/(vol42*sqrt(h)), ±4)` per asset from past
  opens/vol only; per-horizon train filter `t < cutoff` and
  `t+(h+1)*4h < cutoff` with `cutoff = anchor - 4h*(84+60)` (label realised
  before cutoff). Pass.
- Feature hygiene: `feats` excludes `y` and every `y*` label column, so the three
  HGBs train/predict on the 26 v92 features only. `te["pred"] = mean` of the
  three horizon models; IC is `spearman(pred, y42)` on OOS rows (NaN-dropped by
  corr). Pass.
- Weights: `weights_ls` uses contemporaneous `pred`/`rib`/`vol42` only, NaN->0,
  `|raw|` normalisation with `active/5` partial-exposure factor, daily rebalance
  (every 6th bar, ffill). Pass.
- Vol-target/execution: `vol_target_scale` uses `W.shift(2)` returns and a
  trailing 360-bar (min 120) window, `fillna(1.0)` causal default; `v92.simulate`
  gives `W_t*scale_t` earning `open[t+2]/open[t+1]-1`, fee on scaled turnover,
  `0.00005`/bar on long gross only. Same timing as audited v92. Pass.

### `v93_portfolio.py` — no look-ahead found (one timing-asymmetry note)
- Model book: retrains the audited v92 pipeline (`v92.train_predict`) and
  `v92.weights_from(oos, "model")` — same causal features/labels/embargo/weights
  as v92. Carry file is the precomputed OOS series
  (`carry_oos_fee0.0004.parquet`, selection before each anchor per docstring,
  reindexed to `W.index`, NaN->0). Pass.
- Vol path: `realized = 0.7*(W.shift(2)*ret1).sum + 0.9*carry.shift(1)` uses only
  realised (lagged) returns; `vol` is trailing 360-bar (min 120) `*sqrt(2190)`;
  `s = min(0.15/vol, 2)`, NaN->1 causal default. Pass.
- Execution: model leg is `v92`-identical forward timing (`Wm_t` earns
  `o[t+2]/o[t+1]-1`, costs on scaled turnover + long funding). Carry leg charges
  `|diff(exposure)|*2*0.0004/1.2`. The carry leg uses `exposure[t]*carry[t]`
  (0-bar delay) while the model leg uses a 2-bar delay — an inconsistent
  execution assumption (carry implicitly fills faster), but all scale inputs are
  lagged, so it is not forward leakage. Fills exclude the carry leg (reporting
  choice noted in B.4). Pass with note.

## D. Manifest notes
- `v94/result_manifest.json`: track A, status `rejected`, `live_approved:false`,
  `audit.passed:false, replay_complete:false` ("awaiting OpenCode audit").
  Normal monthly 1.931%, worst-year DD 23.75%, fills 10068/60mo.
- `v93/result_manifest.json`: track C, status `rejected`, `live_approved:false`,
  same pending-audit flags. Normal monthly 2.31%, worst-year DD 21.6%,
  fills 7279/60mo (model-leg fills only, per B.4).

## E. Verdict
- v94 blind reproduction is bit-exact (train rows, ICs, yearly nets/DDs/fills).
  Leader v94 code has no look-ahead in data, labels/embargo, features, weights,
  vol-target, or execution.
- v93 nets reproduce within 0.41pp (threshold 1pp) with DDs within 0.02pp;
  residual deltas are fully attributed to documented carry-timing,
  early-NaN/default, and fills-counting conventions, not to hidden logic or
  leakage. Leader v93 code has no look-ahead; the carry-vs-model delay asymmetry
  and model-only fills count should be carried as labelled execution/reporting
  assumptions. Audit complete; leader files untouched.
