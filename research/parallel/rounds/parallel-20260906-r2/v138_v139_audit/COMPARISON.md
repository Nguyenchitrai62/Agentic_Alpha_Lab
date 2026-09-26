# v138 + v139 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v138_v139_audit/` +
`tests/test_v138_v139_audit.py` only. Base: audited v132_v133 replication
(v133 5-asset tranched + pvol configuration). No leader files edited.

Blind protocol: `replication.json` (`replicate_v138_v139.py`,
`tests/test_v138_v139_audit.py` passing) was saved BEFORE opening `v138/`
or `v139/`. Pre-save reads were limited to the allowed base
(`v132_v133_audit/`, `v129_v131_audit/`, `v113_v114_audit/` OOS CSVs,
`v103_v105_audit/`, raw data incl `um_metrics_20260926/`, carry).
`v138/` (`v138_hgb_ridge_blend.py`, `v138_result.json`, manifest, logs) and
`v139/` (`v139_positioning.py`, `v139_result.json`, manifest, logs) were
first opened after the Part A save. Part A imports no v138/v139/v133/v129/
v125/v115/v114/v110/v104/v103/v92/v94 leader module (all formulas inline
from the assignment text + audited OOS CSVs + raw data + carry + audited
panel code).

Key maps: blind `v138.anchors_v92` (`ic_hgb/ic_ridge/ic_blend`) <->
leader `ic_v92` (`hgb/ridge/blend`); blind `v138.scenarios.{hgb,ridge,blend}`
<-> leader `primary_scenarios` (blend); blind `v139.anchors_v103`
(`ic_vs_y6/ic_vs_y18`) <-> leader `ic_v103` (`ic_y6/ic_y18`); blind
`v139.scenarios` <-> leader `primary_scenarios`; blind
`v139.coverage_panel` <-> leader `coverage`.
Thresholds per assignment: IC diff > 0.01, return diff > 1pp, DD diff > 0.5pp.

## A. Number comparison (blind vs leader)

### v138 (HGB+Ridge blend) — DIVERGES on HGB path (spec ambiguity), Ridge exact

- Ridge IC exact (max abs diff 0.0): 2021 0.0852, 2022 -0.0906, 2023 0.0403,
  2024 -0.035, 2025 0.0405. Confirms panels, embargoes, row filters, and
  Ridge standardisation (up to ddof, see B) are correct.
- HGB IC (blind standardized-HGB vs leader raw-HGB):
  2021 0.0824 vs 0.0863 (-0.0039, pass);
  2022 -0.0484 vs -0.032 (-0.0164, EXCEED);
  2023 0.0897 vs 0.1152 (-0.0255, EXCEED);
  2024 0.1212 vs 0.1064 (+0.0148, EXCEED);
  2025 0.1545 vs 0.163 (-0.0085, pass).
- Blend IC: 2021 0.107 vs 0.1064 (+0.0006, pass);
  2022 -0.0871 vs -0.0787 (-0.0084, pass);
  2023 0.073 vs 0.0865 (-0.0135, EXCEED);
  2024 0.0393 vs 0.0311 (+0.0082, pass);
  2025 0.1018 vs 0.1084 (-0.0066, pass).
- Scenarios (blind blend vs leader blend):
  normal monthly 2.122 vs 2.075 (+0.047pp);
  yearly nets 25.13 vs 21.67 (+3.46pp EXCEED, 2021),
  8.42 vs 8.11 (+0.31 pass), 51.88 vs 51.23 (+0.65 pass),
  42.54 vs 41.75 (+0.79 pass), 19.99 vs 21.58 (-1.59 EXCEED, 2025);
  full-path DD 13.46 vs 14.73 (-1.27pp EXCEED).
  fee monthly 1.898 vs 1.852 (+0.046); yearly 2021 +3.34 EXCEED,
  2025 -1.67 EXCEED; fullDD 14.47 vs 16.44 (-1.97 EXCEED).
  exec monthly 1.618 vs 1.575 (+0.043); yearly 2021 +3.18 EXCEED,
  2025 -1.76 EXCEED; fullDD 16.27 vs 18.53 (-2.26 EXCEED).
- Reference v133 (2.44/2.222/1.95) matches the audited number on both sides.
  Blind hgb-only normal 2.392 / ridge-only 1.963 / blend 2.122: blend sits
  between components as expected; leader blend 2.075 is 0.047pp below blind
  blend because leader HGB is raw.

### v139 (positioning) — bit-exact

- Scenarios blind = leader: normal monthly 2.422 / full-path DD 19.06;
  fee 2.174 / 20.69; exec 1.865 / 22.69. Max abs monthly/full-DD diff
  0.000pp/0.00pp. Yearly nets/DD/fills exact in all 3 scenarios x 5 years
  (e.g. normal 24.96/14.63/2071, 16.83/10.47/2190, 63.45/9.42/2190,
  53.74/8.56/2189, 14.56/19.06/2164).
- v103 IC blind = leader exact (max abs diff 0.0):
  2021 y6 0.0687 / y18 0.075; 2022 0.0503 / 0.0896; 2023 0.0915 / 0.1412;
  2024 0.0501 / 0.08; 2025 0.0459 / 0.0885.
- Coverage blind shares = leader shares to 3dp: BNB 0.450 vs 0.45,
  BTC 0.555 vs 0.555, ETH 0.429 vs 0.429, SOL 0.632 vs 0.632,
  XRP 0.472 vs 0.472. Leader first-full dates BTC 2020-09-15, others
  2021-12-15 20:00; blind row counts (8341/11060/8344/8344/8341 full rows)
  reproduce the same shares; method identical (see B/C).
- No 1pp / 0.5pp / 0.01 threshold exceeded anywhere in v139.

## B. Why blind matched / diverged

- Base config confirmed: blind pvol train rows + Spearman match audited v129
  bit-exact (v114 46120/57070/68020/79000/89950 with 0.5275/0.5283/0.6272/
  0.6935/0.6604; v103 33293/44243/55193/66173/77123 with 0.5068/0.5031/
  0.6141/0.7032/0.6650). Panels, embargoes (v92 102/H42, v94 144/18-42-84,
  v103 78/6-18, pvol 102/+44), row filters, tranche_mean, own 0.20-cap-2
  scales, books 0.25/0.25/0.5, sequential engine target 0.15 — all correct.
- v138 divergence root cause: assignment says "fit HGB (v92 params) and
  Ridge(alpha=10) on standardized features"; blind standardised BOTH models
  (population ddof=0, clip +-5, NaN->0; sd_h/sd_r = population std of
  in-sample preds on standardised train). Leader docstring says "HGB as
  before, plus Ridge on the same features after ... standardisation" and
  code (`v138_hgb_ridge_blend.py:36-44`) fits HGB on RAW `tr[feats]`
  (`h.fit(tr[feats], ...)`; `sd_h = std(h.predict(X))` with `X = tr[feats]`
  raw) and only Ridge on standardised (`z(tr)` with train median/mean/std
  sample ddof=1, clip +-5, NaN->0; `sd_r` from `z(tr)`). Hence Ridge ICs
  match (ddof 0 vs 1 scales all feats by ~1.00001 for n~30-90k, rounds to
  same 4dp), HGB/blend differ. Leader `sd_r` guard is `or 1.0`
  (0 -> 1, NaN stays NaN); blind maps 0/nonfinite -> 1 and nonfinite sd_h
  -> 0. No numeric impact here (no zero-variance in-sample preds).
  If blind HGB is switched to raw (one-line change), HGB/blend ICs and
  scenarios reproduce the leader (Ridge already exact, panels exact).
- v139 match: blind rebuilds positioning with `target = t+4h-5min`,
  merge_asof backward tolerance 4h per asset, log-where->0, diff(6/42),
  z = (s-roll180mean_min90)/roll180std_min90 ddof=1, taker roll6mean_min3 —
  identical to leader `pos_features` (`v139_positioning.py:37-52`, key =
  `t+4h-5min`, same logs/diffs/rollings, 8 feats). Blind `pos_` prefix vs
  leader bare names is cosmetic. v103 HGB raw on augmented feats, v103 pvol
  on base feats without POS (`[c for c in f103 if c not in POS]`), v92/v94
  OOS reused audited CSVs — matches leader (v92/v94 retrained same as v133,
  pvol excludes POS). Bit-exact ICs + scenarios confirm identical join
  timing, warmup, and pipeline.

## C. Look-ahead audit

### `v138/v138_hgb_ridge_blend.py` — no look-ahead found

- Setup (:27-31): reuses audited `v129` module chain
  (`v125/v115/v103/v110`); no data touched. Pass.
- `fit_blend` (:35-49): HGB on raw train feats; Ridge median/mu/sd from
  train only (`tr[feats].median/mean/std`), applied to test via `z(te)`;
  sd_h/sd_r from train in-sample only; test preds `h.predict(te)` /
  `r.predict(z(te))`; blend arithmetic. Test never used for fit. Pass.
- `window` (:52-58): cutoff `A-4*embargo`, train filter
  `t+4*(h+1)<cutoff`, test `[A, A+365)` — audited embargoes/row filters.
  Pass.
- Main (:62-85): v114 extended + v103 base builds, `FEATS` exclude
  y/t/open/sym/bar (v94/v103 also exclude `y*`), per-anchor/horizon
  `fit_blend`, v94/v103 mean over horizons. No test-year fit. Pass.
- pvol (:88-94): `v129.vol_predict` on base panels, `swap`
  (pvol.fillna(vol42)) — audited causal sizing. Pass.
- Portfolio (:96-109): `v125.phased/raw_lo/raw_ls` (past-only), own
  `vol_target_scale`, books 0.25/0.25/0.5, `v110.run/summarize` target 0.15
  (2-bar lag), three scenarios. Pass.
- No normalisation/threshold fitting on locked test beyond train-only
  standardisation; costs/funding per AGENTS.md. No look-ahead found.

### `v139/v139_positioning.py` — no look-ahead found (metrics timing checked)

- `pos_features` (:37-52): key = `t + 4h - 5min` (= bar close_time - 5min
  + 1ms; metrics are 5-min rows so same row as `close_time - 5min`),
  `merge_asof` backward tolerance 4h per asset-sorted frame. At 4h bar
  close (e.g. 04:00), the joined metrics row is 03:55 — available before
  close. Tolerance gaps -> NaN (no forward fill). Pass: no future metrics
  row (04:00 or later) can join.
- Logs (:45-48): `log(where>0)` else NaN — no forward data. Pass.
- Diffs/rollings (:49-52): `diff(6/42)`, `rolling(180,min90)` z,
  `rolling(6,min3)` mean, computed per-asset in `t` order
  (`:66` groups by sym, sorts by `t`). All use only past/current rows of
  the already-causal joined series. Warmup NaNs (-> HGB-native) explain
  first-full 2021-12-15 (alts) / 2020-09-15 (BTC) + 0.43-0.63 shares. Pass.
- Main (:55-80): v92/v94 retrained same as v133 (unchanged books); POS
  merged left onto v103 panel; `f103` includes POS (assert `:71`); v103
  `train_predict` per anchor (audited embargoes); ICs reporting. Pass.
- pvol (:79-80): v114 pvol on base feats; v103 pvol on
  `[c for c in f103 if c not in POS]` — positioning excluded from vol
  forecast per spec. Pass.
- Portfolio (:87-100): same tranched/books/engine as v133 (past-only
  tranching, causal scales, 2-bar lag). `vol_target_scale(p103, ...)` uses
  opens/index, not future POS values. Pass.
- No threshold tuning on locked test; costs/funding per AGENTS.md.
  No look-ahead found.

## D. Post-hoc corrections / protocol log

- No spec reinterpretation after opening `v138/`/`v139/`. Part A script and
  `replication.json` frozen pre-open. One pre-open choice logged here (not
  a post-open fix): A1 standardised both HGB and Ridge per the literal
  assignment text; leader standardises Ridge only (HGB raw per "as before").
  Blind Ridge already exact; switching blind HGB to raw reproduces leader.
  A2 8-feature list (`pos_oi_chg6/oi_chg42/oi_z/top_ls/top_ls_chg6/top_ls_z/
  crowd_ls_z/taker_ls6`) matches leader `POS` exactly (prefix only).
- Blind `v139` stores shares/row counts but not first-date strings; leader
  first dates quoted above. No numeric impact (shares match to 3dp,
  scenarios/ICs bit-exact).
- Blind pvol Spearman matches v129 bit-exact; no hidden-year strict path
  required by the assignment (scenarios + full-path DD only).

## E. Manifest notes / verdict

- `v138/result_manifest.json`: track B, `rejected`, `live_approved:false`,
  audit pending. Scenarios 2.075/14.73, 1.852/16.44, 1.575/18.53 match
  leader `v138_result.json` bit-exact. Note: blend underperforms v133
  reference (2.44/2.222/1.95) in all scenarios; Ridge-only would be weaker
  still (blind ridge-only 1.963 normal). Matches the numbers.
- `v139/result_manifest.json`: track C, `rejected`, `live_approved:false`,
  audit pending. Scenarios 2.422/19.06, 2.174/20.69, 1.865/22.69 and ICs
  match blind bit-exact. Note: positioning lifts return 2.44 -> 2.422? No —
  normal monthly 2.422 is 0.018pp BELOW v133 2.44, but yearly mix shifts
  (2023 63.45 vs 49.61 up, 2025 14.56 vs 35.49 down) while full-path DD
  worsens 15.18 -> 19.06. Matches the numbers.
- Blind replication is bit-exact on all v139 ICs/coverage/scenarios and on
  v138 Ridge ICs/pvol; v138 HGB/blend divergence is explained by the
  raw-vs-standardised HGB ambiguity (assignment literal vs leader "as
  before"). No look-ahead in standardisation, blending, metrics join,
  POS warmup, pvol exclusion, tranching, scales, or engine paths. Audit
  complete; leader files untouched.
