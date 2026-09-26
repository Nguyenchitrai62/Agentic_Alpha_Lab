# v136 + v137 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v136_v137_audit/` +
`tests/test_v136_v137_audit.py` only. Base: audited v132_v133 (v133
configuration) and v135 (1m bar stats, limit-offset execution) replications.
No leader files edited.

Blind protocol: `replication.json` (`replicate_v136_v137.py`,
`tests/test_v136_v137_audit.py` passing 3/3) was saved BEFORE opening `v136/`
or `v137/`. Pre-save reads were limited to the allowed base
(`v132_v133_audit/`, `v135_audit/`, `v113_v114_audit/` OOS CSVs,
`v103_v105_audit/`, raw data, carry). `v136/` (`v136_feature_selection.py`,
`v136_result.json`, manifest, logs) and `v137/` (`v137_realistic_frontier.py`,
`v137_result.json`, manifest, logs) were first opened after the Part A save.
Part A imports no v136/v137/v135/v133/v129/v125/v115/v114/v110/v104/v103/v92/v94
leader module (all formulas inline from the assignment text + audited OOS CSVs
+ raw data + carry + audited panel code).

## A. Number comparison (blind vs leader)

Key maps: blind `v136.scenarios` <-> leader `primary_scenarios`; blind
`v136.kept_counts`/`kept_detail` <-> leader `kept_features`; blind
`v137.per_target["0.15"/"0.17"/"0.19"/"0.21"]` <-> leader `frontier`
`t15/t17/t19/t21`.

### v136 (permutation-importance selection + v133 pipeline) — bit-exact

- Scenarios blind = leader: normal monthly 1.974 / full-path DD 19.38;
  fee 1.758 / 21.10; exec 1.488 / 23.20. Max abs monthly diff 0.000pp,
  max abs full-path DD diff 0.00pp.
- Yearly blind = leader in all 3 scenarios x 5 years (net/DD/fills exact):
  normal 11.62/13.03/2184, 5.62/12.72/2190, 44.39/9.00/2190,
  31.40/8.92/2190, 44.47/7.65/2178; fee/exec cells exact.
- Kept-feature counts blind = leader exact (30/30 cells):
  v92 [13,12,15,10,19]; v94_h18 [19,17,16,14,16];
  v94_h42 [16,15,15,12,18]; v94_h84 [16,15,14,14,15];
  v103_h6 [22,21,23,19,21]; v103_h18 [17,21,27,19,22].
- Kept-feature sets blind = leader exact as sets AND in order (30/30 cells
  verified programmatically, 0 set diffs, 0 order diffs).
- Reference v133 (2.44/2.222/1.95) matches the audited v133 numbers;
  selection lowers tranched return 2.440 -> 1.974 while full-path DD worsens
  15.18 -> 19.38 (normal).
- No 1pp / 0.5pp threshold exceeded anywhere.

### v137 (v133 books x vol-target frontier, v135 exec d=10bps) — bit-exact

- Per-target blind = leader: 0.15 monthly 2.241 / full-path DD 16.25;
  0.17 2.486 / 17.88; 0.19 2.726 / 19.32; 0.21 2.933 / 20.28.
  Max abs monthly/full-DD diff 0.000pp/0.00pp.
- Yearly blind = leader in all 4 targets x 5 years (net/DD/fills exact):
  t15 21.04/14.52/2085, 14.06/11.09/2190, 46.54/8.03/2190,
  43.13/10.03/2189, 30.51/9.69/2161;
  t17 20.81/16.35/2083, 16.44/12.52/2190, 53.55/9.06/2190,
  49.76/11.31/2189, 34.93/10.98/2161;
  t19/t21 cells exact (verified programmatically).
- Blind 0.15 = audited v135 10bps row bit-exact (monthly/yearly/DD/maker/
  orders), confirming the v133-books + v135-execution base.
- No 1pp / 0.5pp threshold exceeded anywhere.

## B. Why blind matched

- v136: blind rebuilds the 5-asset v114 extended panel (Bitstamp >= 2013-01-01
  + Coinbase BTC, Coinbase ETH, spot_2017 prefix where exists) and the v103
  base panel (spot prefix + USD-M + flow feats), 26 + 36 feats, HGB v92 params.
  Per (model, horizon, anchor): training rows as audited
  (t < cutoff, target notna, t+(h+1)*4h < cutoff; embargoes 102/144/78);
  val = training rows with t >= cutoff-730d (sample 20000 seed 0 if larger);
  inner = training rows with t+(h+1)*4h < val_start-embargo*4h; HGB on inner,
  permutation_importance on val (Spearman scorer, n_repeats=3, seed 0), keep
  mean>0 else top-5, refit on all training rows; v94/v103 mean over horizons.
  pvol NOT selected (assignment lists only return models), retrained by the
  v129 method — pvol Spearman matches audited v129 bit-exact
  (v114 0.5275/0.5283/0.6272/0.6935/0.6604;
  v103 0.5068/0.5031/0.6141/0.7032/0.6650). Then N=5 LO/LS weights, tranche
  mean/6, own 0.20-cap-2 scales, books 0.25/0.25/0.5, sequential engine target
  0.15. Bit-exact kept sets (order included) + scenarios confirm identical
  panels, embargoes, val/inner splits, sampling, scorer, and pipeline.
- v137: blind reuses the audited 5-asset OOS CSVs + the same retrained pvol
  (left-join replace), N=5 weights, tranche, own scales, books — then sweeps
  the portfolio vol target (0.15/0.17/0.19/0.21, cap 2) with the v135 1m rule
  at d=10bps (p0 minute-0, lo/hi offsets 2..14, p15 minute-15, maker fee
  0.0002 rel -/+d else taker 0.0005 rel p15/p0-1 +/-0.0002). Bit-exact
  frontier confirms v133-books base and the target-only risk dial.
- Carry unchanged (`carry_oos_fee0.0004.parquet`); live [2021-09-24, 2026-09-23).

## C. Look-ahead audit

### `v136/v136_feature_selection.py` — no look-ahead found

- Setup (:28-35): reuses audited `v129` module chain
  (`v125`/`v115`/`v103`/`v110`); HGB v92 params; Spearman via
  `pd.Series.corr(method="spearman")` (equivalent to blind `spearmanr` scorer
  — bit-exact kept sets confirm). No data touched. Pass.
- Panels/feats (:67-77): audited `build` + `add_targets`; FEATS exclude
  y*/t/open/sym/bar (v92 excludes y/t/open/sym/bar; v94/v103 additionally
  exclude `y*` prefix). Test year never used for fit. Pass.
- Selection (:45-63): training rows as audited (cutoff, target notna,
  t+(h+1)*4h < cutoff); val = last 730d of training rows (sample 20000 seed 0
  if larger); inner = label realized before val_start-embargo; fit inner,
  importance on val, keep mean>0 else top-5, refit on all training rows,
  predict test year. Val/inner/retrain all pre-cutoff; no test labels used.
  Pass.
- pvol (:91-97): `v129.vol_predict` with audited embargo + `pvol.fillna(vol42)`
  swap on (t, sym) — audited fv shift (-43) and +44 filter; sizing at t uses
  only causal pvol(t) or contemporaneous vol42(t). Pass.
- Portfolio (:99-111): `v125.phased(raw, 0..5)` past-only schedules,
  `vol_target_scale` causal (W.shift(2), trailing window, cap 2), books
  0.25/0.25/0.5, `v110.run/summarize` target 0.15 (2-bar lag). Pass.
- Reporting (:108-114): scenarios + kept features + static v133 reference. No
  selection or refit on locked test; costs/funding per AGENTS.md.
  No look-ahead found.

### `v137/v137_realistic_frontier.py` — no look-ahead found

- Rebuild (:30-44): same 5-asset panel builds + `train_predict` per anchor
  with audited embargoes; test year never used for fit. Pass.
- pvol (:43-49): `v129.vol_predict` + fillna swap — same audited causal path
  as v136. Pass.
- Books (:51-59): `v125.phased` past-only tranches, causal `vol_target_scale`,
  books 0.25/0.25/0.5. Pass.
- Frontier (:60-97): whole-index trailing vol (rolling 360/min-120, cap 2),
  per-target scalar s=tgt/vol (causal), Wt/carry_exp causal, `v135.bar_stats`
  reindexed to idx+4h (as-of T), d=10bps maker/taker rule identical to v135;
  1m post-T data affects only fill cost at t, not the signal. Pass.
- Reporting (:93-98): monthly/yearly/full-path DD per target; primary t17
  declared an ex-post risk-budget choice ("Reporting frontier only"). No
  normalisation/threshold fitting on locked test; costs/funding per AGENTS.md.
  No look-ahead found.

## D. Post-hoc corrections / protocol log

- No spec reinterpretation after opening `v136/`/`v137/`. Part A script and
  `replication.json` were frozen pre-open; no pre-open fix was needed.
- Blind Spearman scorer uses `scipy.stats.spearmanr` returning 0.0 on
  non-finite/short inputs; leader uses `pd.Series.corr(method="spearman")`.
  Bit-exact kept sets in all 30 cells confirm scorer equivalence on this data.
- Blind `kept_detail` nests v94/v103 by horizon (`kept_detail.v94[h]`,
  `kept_detail.v103[h]`) vs leader flat keys (`kept_features.v94_h{h}`);
  counts/sets/orders identical. Blind v137 keys are `"0.15"..` (= leader
  `t15`..); blind v136 scenarios carry no `mean_g` extra key. No numeric impact.

## E. Manifest notes / verdict

- `v136/result_manifest.json`: track A, `rejected`, `live_approved:false`,
  audit pending. Monthly 1.974/worst-DD 13.03, fee 1.758/14.09,
  exec 1.488/15.77 matches blind bit-exact (manifest worst-DD is the yearly
  max; full-path DD 19.38/21.10/23.20 in result file).
- `v137/result_manifest.json`: track C, `rejected`, `live_approved:false`,
  audit pending. Frontier t15..t21 monthlies/DDs/yearlies match blind
  bit-exact; manifest repeats the single realistic-execution frontier in all
  three scenario slots with an ex-post-choice note.
- Blind replication is bit-exact on all v136 kept sets/scenario yearlies and
  all v137 frontier yearlies. No look-ahead in selection splits, pvol swap,
  tranching, scales, engine, or 1m execution/target sweep. Audit complete;
  leader files untouched.
