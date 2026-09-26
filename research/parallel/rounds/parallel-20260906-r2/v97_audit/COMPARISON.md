# v97 blind audit — COMPARISON.md (Part B)

Blind replication was saved BEFORE opening `v97/` (see `replication.json`,
`predictions.csv`, `equity.csv` in this folder, plus `tests/test_v97_audit.py`
passing). Audit scope: `v97/v97_tree_ensemble.py`, `v97/v97_result.json`,
`v97/result_manifest.json`. No leader files were edited. All writes are under
`v97_audit/` + `tests/test_v97_audit.py`.

## A. Number comparison (blind audit vs leader v97)

Train rows match exactly for every anchor (same v92 features/target/cutoff/embargo).

| anchor | train rows blind | train rows leader | IC blind (16-mean, all imputed) | IC leader ensemble | IC diff |
|---|---|---|---|---|---|
| 2021-09-24 | 33088 | 33088 | 0.0733 | 0.0781 | -0.0048 |
| 2022-09-24 | 44038 | 44038 | -0.0083 | 0.0055 | -0.0138 |
| 2023-09-24 | 54988 | 54988 | 0.0933 | 0.1015 | -0.0082 |
| 2024-09-24 | 65968 | 65968 | 0.1223 | 0.1187 | +0.0036 |
| 2025-09-24 | 76918 | 76918 | 0.1652 | 0.1724 | -0.0072 |

Yearly long-only book, causal 20% vol target, normal costs:

| anchor | net blind % | net leader % | diff | DD blind % | DD leader % | fills blind | fills leader |
|---|---|---|---|---|---|---|---|
| 2021-09-24 | 5.56 | 4.81 | +0.75pp | 18.19 | 20.00 | 1262 | 1308 |
| 2022-09-24 | 37.44 | 39.16 | -1.72pp | 14.04 | 14.72 | 1333 | 1490 |
| 2023-09-24 | 72.76 | 81.14 | -8.38pp | 13.26 | 11.80 | 1456 | 1543 |
| 2024-09-24 | 55.89 | 50.97 | +4.92pp | 11.12 | 12.07 | 1797 | 1787 |
| 2025-09-24 | 14.82 | 21.69 | -6.87pp | 27.16 | 23.79 | 1130 | 1172 |

Thresholds from spec (IC diff > 0.01 or return diff > 1pp = explain):
exceeded for 1/5 anchors on IC (2022: 0.0138) and 4/5 years on return
(2022, 2023, 2024, 2025). Root cause isolated below.

## B. Root cause (spec deviation in HGB imputation, not a universe/cutoff error)

Spec: all 16 members "fitted on features with NaN replaced by the
TRAINING-ROW medians (same medians applied to prediction rows)".
Blind replication does exactly that (15 HGB + 1 ET all on median-imputed
matrices; prediction = mean of 16).

Leader `v97_tree_ensemble.py::train_predict_ensemble` (lines 44-53) does not:

- HGB members: `m.fit(tr[feats], tr["y"])` and `m.predict(te[feats])` on raw
  features — HGB NaN-native, no imputation.
- Only the ExtraTrees member uses `med = tr[feats].median()` with
  `fillna(med)` on train and prediction rows.

Everything else matches: same depths/seeds/params (3,4,6 x seeds 0-4;
ET 300/min_samples_leaf 300/max_features 0.5/seed 0), same v92 training-row
filter (`t < A-408h`, `t+172h < cutoff`, `y` not NaN), same 26 features and
5-asset universe. Train-row counts are therefore identical, and the ET leg is
identical. The IC gaps (-0.014..+0.004) come from HGB learning different splits
on early training NaNs (spot-prefix funding NaNs, vol180/ret540/volz warmup,
d50/d200 warmup) under native-NaN vs median handling; OOS predictions then
differ even where OOS NaNs are rare. Portfolio gaps (up to 8.4pp) follow from
different weights through the same v92 sizing/vol-target path, plus fills
differences (e.g. 2022: 1333 vs 1490).

Minor method note (non-material): leader `book()` simulates the vol-scaled
book once over the full 5-year span and cuts yearly net/turn windows, while
the blind audit (like `v92_pooled_hgb_vt.py::main`) re-simulates each yearly
`W/K` slice per year (first-bar turnover = `abs` vs cross-year `diff`). This
moves at most a few boundary bars per year and cannot explain multi-pp gaps;
it is noted for exactness only.

## C. Look-ahead audit of `v97_tree_ensemble.py`

- Pipeline reuse: `v92.build()` (spot prefix strictly before first USD-M bar,
  funding USD-M only), v92 features/label/embargo, `v92.weights_from`,
  `v92.vol_target_scale`, `v92.simulate`, `v92.stats` — all previously audited
  as causal. No new feature or label code. Pass.
- Imputation medians (the flagged area): `med = tr[feats].median()` where `tr`
  is the per-anchor training rows only (`t < cutoff`, label realized before
  cutoff). The same `med` is applied to that anchor's prediction rows. No
  OOS/full-sample median, no future information. Causal. Pass on leakage; FAIL
  on spec fidelity only (applied to ET, not to HGB).
- OOS construction: per-anchor `[A, A+365d)` predictions concatenated; weights
  use contemporaneous pred/rib/vol42 only. Pass.
- Vol-target timing: inherited v92 causal trailing vol (`rolling360/min120`,
  cap 2, NaN->1), scale known at close `t`, earnings forward
  `open[t+2]/open[t+1]-1`. Pass.
- Execution timing: inherited v92 one-bar delay, fee 0.0002, long funding
  0.00005/bar. Pass.
- Reference blend (`reference_blend_with_v94`): 50/50 of vol-scaled v92
  long-only and v94 long/short legs, each with its own vol target, simulated
  with scale 1.0 on the combined weights. Out of scope for the v97-ensemble
  audit; not checked for v94-side leakage here.

No look-ahead found in medians, features, labels/embargo, spot prefix,
vol-target timing, or execution. The only finding is the HGB-vs-spec
imputation deviation above.

## D. Manifest note

`result_manifest.json`: v97/track B, status `rejected`, `live_approved:false`,
`audit.passed:false, replay_complete:false` ("awaiting OpenCode audit").
Scenarios monthly 2.668/2.466/2.215 with worst-year DD 23.79/25.06/26.87;
yearly normal nets as in section A; reference blend monthly 2.34.

## E. Verdict

Blind reproduced train rows, features, cutoff/embargo, and the v92 book, but
IC/return gaps exceed spec thresholds on 2022 IC and 4/5 yearly nets. Cause is
the leader fitting the 15 HGB members NaN-native instead of on training-row
median-imputed features as specified; the median computation itself is causal
(training rows only). Leader code has no look-ahead in the imputed medians or
elsewhere in the ensemble path. Audit complete; leader files untouched.
