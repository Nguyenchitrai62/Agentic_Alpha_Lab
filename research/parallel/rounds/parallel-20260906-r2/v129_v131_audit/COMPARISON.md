# v129 + v130 + v131 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v129_v131_audit/` +
`tests/test_v129_v131_audit.py` only. Base: audited v126 (phase runs of the
v115 portfolio) and v103_v105 replications. No leader files edited.

Blind protocol: `replication.json` (`replicate_v129_v131.py`,
`tests/test_v129_v131_audit.py` passing 4/4) was saved BEFORE opening `v129/`,
`v130/` or `v131/`. Pre-save reads were limited to the allowed base
(`v126_audit/` replication + script, `v103_v105_audit/` replication + script,
`v113_v114_audit/` OOS CSVs + script, `v115/`, `v127_v128_audit/` phase helpers,
raw data, carry). `v129/` (`v129_vol_forecast_sizing.py`, `v129_result.json`,
manifest, log), `v130/` (`v130_spot_perp_flow.py`, `v130_result.json`,
manifest, log), `v131/` (`v131_signal_strength.py`, `v131_result.json`,
manifest, log) were first opened after the Part A save. Part A imports no
v129/v130/v131/v125/v115/v114/v110/v104/v103/v92/v94 leader module (all formulas
inline from the assignment text + audited OOS CSVs + raw data + carry +
audited panel code).

## A. Number comparison (blind vs leader)

Key maps: blind `v129.phases_with_pvol` <-> leader `primary_phase_mean`
(`per_phase` [monthly, fullDD] pairs); blind `v129.anchors_v114/v103`
spearman <-> leader `vol_quality`; blind `v129.phases_with_vol42` <->
leader `reference_vol42_phase_mean` (= v126); blind `v130.phases` <->
leader `primary_phase_mean`; blind `v130.anchors` IC <-> leader `ic`;
blind `v131.phases` <-> leader `primary_phase_mean`; blind `v131.k_stats`
<-> leader `k_mean_by_book`.

### v129 (vol-forecast sizing) — bit-exact

- Vol quality blind (4dp) vs leader (3dp): max abs spearman diff 0.0005
  (rounding only). e.g. v114 panel pvol 0.5275/0.5283/0.6272/0.6935/0.6604 vs
  0.528/0.528/0.627/0.693/0.660; vol42 0.5462/0.5835/0.4872/0.6561/0.6135 vs
  0.546/0.584/0.487/0.656/0.614. v103 panel pvol 0.5068/0.5031/0.6141/0.7032/
  0.665 vs 0.507/0.503/0.614/0.703/0.665. No 0.01 threshold exceeded.
- All 6 phases x 3 scenarios: max abs monthly diff 0.000pp, max abs
  full-path DD diff 0.00pp. Headlines blind = leader: normal monthly 2.370 /
  worst DD 19.82; fee 2.154 / 21.17; exec 1.883 / 22.82. Per-phase normal
  2.669/15.57, 2.548/14.38, 2.623/15.24, 2.199/12.16, 2.090/17.36,
  2.091/19.82 exact.
- Reference blind = leader = v126 bit-exact (normal 2.311 / 20.93, fee 2.09 /
  22.44, exec 1.815 / 24.32; per-phase p0 2.608/16.78 … p5 2.029/20.93).
- No 1pp / 0.5pp / 0.01 threshold exceeded anywhere in v129.

### v131 (signal-strength timing) — bit-exact

- All 6 phases x 3 scenarios: max abs monthly diff 0.000pp, max abs
  full-path DD diff 0.00pp. Headlines blind = leader: normal 2.398 / 24.04;
  fee 2.186 / 25.49; exec 1.922 / 27.26. Per-phase normal 2.613/18.40,
  2.754/19.78, 2.696/18.30, 2.207/13.56, 2.169/21.84, 1.947/24.04 exact.
- k means blind = leader: lo 1.1478 -> 1.148, ls94 1.099 -> 1.099, ls103
  1.0894 -> 1.089 (rounding only).
- No threshold exceeded anywhere in v131.

### v130 (spot-vs-perp flow) — close but NOT bit-exact

- ICs (blind vs leader): y6 0.0476/0.0508 (-0.0032), 0.0277/0.0255 (+0.0022),
  0.0675/0.0662 (+0.0013), 0.0365/0.0371 (-0.0006), 0.0668/0.0648 (+0.0020);
  y18 0.0646/0.0654 (-0.0008), 0.0545/0.0506 (+0.0039), 0.1181/0.1161
  (+0.0020), 0.0694/0.064 (+0.0054), 0.1081/0.1081 (0.0). Max abs IC diff
  0.0054 < 0.01: no IC threshold exceeded. Train rows match the v103
  baseline exactly (33388/33328 … 77218/77158), so embargo/labels/panel
  spans coincide.
- Phase-mean monthly blind vs leader: normal 2.314 vs 2.321 (-0.007pp); fee
  2.085 vs 2.091 (-0.006pp); exec 1.801 vs 1.803 (-0.002pp). Worst DD blind
  vs leader: normal 20.77 vs 20.85 (-0.08pp); fee 22.36 vs 22.44 (-0.08pp);
  exec 24.39 vs 24.43 (-0.04pp). No phase-mean threshold exceeded.
- Per-phase monthly: max abs diff 0.129pp (p1 normal 2.525 vs 2.654)
  < 1pp: no return threshold exceeded at per-phase monthly level.
- Per-phase full-path DD: 4 of 18 cells exceed 0.5pp and are explained
  below (B.3): p0 normal 16.54 vs 16.03 (+0.51pp); p2 normal 13.93 vs 14.56
  (-0.63pp); p2 exec 16.15 vs 17.01 (-0.86pp); p3 exec 16.47 vs 15.95
  (+0.52pp). Max abs DD diff 0.86pp. All other per-phase DD diffs <= 0.5pp.
- Yearly means (mean over 6 phases per anchor year) differ > 1pp in most
  years and are explained below (B.3): normal 18.76/20.65 (-1.89),
  15.22/13.84 (+1.38), 52.05/48.58 (+3.47), 45.15/46.54 (-1.39),
  31.69/33.59 (-1.90); fee/exec show the same pattern (up to +3.39pp in
  2023, -1.84pp in 2025). These are the same retrain-sensitivity effect,
  not a phase-mean failure: the 5-year geometric phase mean still agrees
  to 0.007pp.

## B. Why blind matched + why v130 differs

### B.1 v129 (see also C)

- fv: blind `log(rolling-42 std of diff(log open)).shift(-43)` per asset bar
  order (ddof=1, min 42) == leader `log(r.rolling(42).std().shift(-43))`
  (`r = log(open).diff()`, std of r[t+2..t+43]). Train rows agree
  (46120/57070/68020/79000/89950 v114; 33293/44243/55193/66173/77123 v103),
  confirming identical panels, embargo (102 bars) and `t+44*4h < cutoff`
  filter (leader `HV+2 = 44`). HGB v92 params identical; pvol = exp(pred).
- Swap: blind left-joins pvol on (t, sym) and replaces vol42 where available
  == leader `vol42 = pvol.fillna(vol42)`. Counts replaced: v114 LO/LS and
  v103 LS all > 0 (full OOS coverage). Un-subsampled LO/LS formulas +
  per-phase keep pos%6==p ffill + own 0.20-cap-2 scales + union
  >= first v103 t + books 0.25/0.25/0.5 + sequential engine target 0.15
  ungoverned reproduce the leader `v125.raw_lo/raw_ls/phased` +
  `vol_target_scale` + `v110.run/summarize` path bit-exact.

### B.2 v131 (see also C)

- Strength: blind mean over assets of `max(pred,0)*(rib != -1)` (LO) /
  `|pred|` (LS) grouped by t == leader `strength()` (same gating; groupby t
  mean). Median: blind `rolling(2160, min 360).median().shift(1)` ==
  leader `rolling(360*PD=2160, min 60*PD=360).median().shift(1)` (2160 4h
  rows = 360 days). k = clip(/, 0.5, 2) NaN/inf -> 1 both sides.
- Sampling: blind keeps k on rows pos%6==p of that book's raw index then
  ffill to idx == leader `k.reindex(idx).where(keep).ffill().fillna(1.0)`
  with `keep = arange(len(idx))%6==ph` (same daily-rebalance hold; indices
  coincide because v114/v103 OOS spans are identical 10950 bars). Scales
  computed on un-multiplied phased weights then multiplied by k both
  sides; books/engine identical. Bit-exact confirms the interpretation.

### B.3 v130 difference (explained, no look-ahead)

- What matches: feature SET matches exactly (36 + 7: sp_share_z,
  sp_share_chg, tbr_gap6, tbr_gap42, basis6, basis_chg, basis_z; share/basis
  raw are intermediates on both sides), train-row counts match exactly,
  embargo/labels/HGB match, left-join on (t, sym) matches, phase method
  matches. Coverage is consistent with the leader (leader per-sym all-7
  fractions 0.759–0.986 reflecting the 2019-09-01 spot-start + 180-bar
  warmup; blind per-feature counts 71906–72801 of ~10950x5 rows show the
  same warmup structure).
- What differs: blind ICs are off by -0.0032..+0.0054 and the retrained
  books redistribute PnL across years (2023 +3.47pp, 2021/2025 ≈ -1.9pp)
  while the 5-year phase-mean monthly stays within 0.007pp. This is the
  expected sensitivity of pooled HGB retrains with 7 new NaN-heavy
  microstructure features: small differences in spot-feature edge handling
  (inner-join start / rolling min-periods warmup / float precision in
  share-basis-tbr construction from the raw perp+spot 4h files) move a few
  OOS predictions enough to shift yearly nets by 1–3pp and a few per-phase
  DDs by up to 0.86pp, without breaking the IC (< 0.01) or phase-mean
  monthly (< 1pp) gates.
- The assignment text pins the formulas but not the edge conventions
  (rolling min_periods/dtype at the 2019 spot-start, exact inner-join
  duplicate handling); blind chose pandas defaults (inner join,
  rolling min_periods=window, ddof=1, clip-then-roll). The residual is
  attributed to that unspecified edge, not to leakage (C passes) or to a
  different hypothesis. v130 needs a leader-edge rerun if bit-exactness
  is required; the economic conclusion (phase mean ≈ v126: 2.314 vs 2.311
  normal) is unaffected.

## C. Look-ahead audit

### `v129/v129_vol_forecast_sizing.py` — no look-ahead found

- `add_fv` (:34-41): per-sym time-sorted `r = log(open).diff()`,
  `fv = log(r.rolling(42).std().shift(-43))` = std of r[t+2..t+43]. Target
  is forward-only by construction. Pass (the shift is the critical
  correctness point and it is correct: -43 lands on [t+2, t+43]).
- `vol_predict` (:44-59): per anchor `cutoff = A - 102*4h`; train requires
  `t < cutoff`, finite fv, AND `t + 44*4h < cutoff` (HV+2). Since fv at t
  consumes opens through t+43, the +44 filter leaves a 1-bar buffer before
  the cutoff — no target peek across the embargo. Features are the
  contemporaneous panel feats at t (past-only by audited v92/v103
  construction). `pvol = exp(pred)`; quality ICs are OOS rank correlations
  per anchor year. Pass.
- `swap` (:96-99): `vol42 = pvol.fillna(vol42)` on (t, sym) — sizing at t
  uses only the causal pvol(t) (whose features are past-only) or the
  contemporaneous vol42(t). Signals/targets unchanged. Pass.
- `phase_mean` (:62-76): `v125.raw_lo/raw_ls` (contemporaneous
  pred/rib/vol-or-pvol only) + `v125.phased(R, [ph])` single-phase keep
  pos%6==ph ffill (past-only) + causal `vol_target_scale` (W.shift(2),
  trailing window, cap 2) + `v110.run/summarize` (2-bar execution lag,
  target 0.15 ungoverned). Reporting is phase mean monthly / worst DD /
  yearly means. Pass.
- No normalisation/threshold fitting on locked test; costs/funding per
  AGENTS.md.

### `v130/v130_spot_perp_flow.py` — no look-ahead found

- `sp_features` (:38-57): per asset inner-join of USD-M perp 4h and
  `spot_majors_20260925/{SYM}_spot_4h.parquet` on open_time; share/tbr-gap/
  basis built from same-t closes/volumes/taker ratios with causal
  rolling(6/42/180) means/stds (current-bar inclusive, no shift — correct
  because the signal at t fills at t+1). Rows before the first perp bar
  are NaN (panel rows there are the spot prefix itself, per docstring) and
  stay NaN through the left-join; HGB is NaN-native. No future bar enters
  any feature. Pass.
- Panel/train (:70-79): `v103.build().merge(sp, on=[t,sym], how=left)`;
  `f103` = all non-target cols (asserts all 7 SP present); `v103.train_
  predict` with the audited v103 embargo/labels per horizon; test year
  never used for fit. ICs are OOS spearman. `secondary_ls_book` is the
  phase-0 LS book (reporting). Pass.
- `primary_phase_mean` uses `v129.phase_mean` (same audited phasing/scales/
  engine as v129). Reference is the static v126 number (reporting). Pass
  with the B.3 edge note (warmup conventions, not leakage).

### `v131/v131_signal_strength.py` — no look-ahead found (strength-median focus)

- `strength` (:32-37): per-book `st` = groupby-t mean of gated magnitude
  (LO: `pred.clip(lower=0)` where `rib != -1`; LS: `|pred|`) — all inputs
  contemporaneous at t. `med = st.rolling(2160, min 360).median().shift(1)`
  (trailing 360 days, min 60 days, shifted 1) so the denominator at t uses
  strictly prior bars; `k = (st/med).clip(0.5, 2).fillna(1)`. The shift(1)
  is the critical correctness point and it is present. Pass.
- Phasing (:56-64): raw frames via audited `v125.raw_*`; single-phase
  `v125.phased(R, [ph])`; `k.reindex(idx).where(keep).ffill().fillna(1)`
  holds k on the book's daily rebalance schedule (last daily sample ≤ t —
  causal); scales computed on un-multiplied weights (`vol_target_scale`
  before `* k`, so the vol target cannot undo k, as documented); books
  0.25/0.25/0.5; `v110` target 0.15 ungoverned. Pass.
- Reporting (:67-71): phase mean monthly / worst DD / yearly means;
  reference is the static v126 number. Pass.
- No normalisation/threshold fitting on locked test; costs/funding per
  AGENTS.md.

## D. Post-hoc corrections / protocol log

- No spec reinterpretation after opening `v129/`/`v130/`/`v131/`. Part A
  script and `replication.json` unchanged since the pre-open save
  (v129/v131 bit-exact confirms the blind fv and strength/median
  interpretations; v130 blind choices documented in `meta` were frozen
  pre-open).
- One rounding note (no numeric impact): blind stores spearman/IC at 4dp,
  leader at 3dp (v129) / 4dp (v130) — max rounding gap 0.0005.
- Blind `v130.new_feature_coverage` stores per-feature non-NaN counts
  rather than the leader per-sym all-7 fractions; values are consistent
  (same warmup) but not directly keyed — noted here, no replication
  change.

## E. Manifest notes / verdict

- `v129/result_manifest.json`: track B, `rejected`, `live_approved:false`,
  audit pending. Phase-mean 2.37/19.82, 2.154/21.17, 1.883/22.82 matches
  blind bit-exact. Note (phase-mean over six phases; reference vol42
  2.311/2.09/1.815) matches the numbers.
- `v130/result_manifest.json`: track C, `rejected`, `live_approved:false`,
  audit pending. Phase-mean 2.321/20.85, 2.091/22.44, 1.803/24.43 vs blind
  2.314/20.77, 2.085/22.36, 1.801/24.39 (headline gaps ≤ 0.08pp). Per-phase
  monthly gaps ≤ 0.129pp; 4 per-phase DD cells and most yearly means
  exceed the explain-thresholds and are attributed in B.3 to HGB
  retrain sensitivity to unspecified spot-feature warmup edges.
- `v131/result_manifest.json`: track A, `rejected`, `live_approved:false`,
  audit pending. Phase-mean 2.398/24.04, 2.186/25.49, 1.922/27.26 matches
  blind bit-exact. Note (k means ~1.1; worst DD 20.9 -> 24.0) matches.
- v129 and v131 blind replications are bit-exact on all phases/scenarios,
  spearman/ICs, and references. v130 reproduces the hypothesis and phase
  mean (2.314 vs 2.321) with IC gaps < 0.01 but shows the documented
  retrain-sensitivity residuals in yearly/per-phase DDs. No look-ahead in
  the fv shift, spot/perp features, or strength median. Audit complete;
  leader files untouched.
