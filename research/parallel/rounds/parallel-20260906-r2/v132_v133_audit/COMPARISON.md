# v132 + v133 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v132_v133_audit/` +
`tests/test_v132_v133_audit.py` only. Base: audited v126/v129_v131 (phase
mean, vol forecast) and v127 (tranched deployment) replications. No leader
files edited.

Blind protocol: `replication.json` (`replicate_v132_v133.py`,
`tests/test_v132_v133_audit.py` passing 3/3) was saved BEFORE opening `v132/`
or `v133/`. Pre-save reads were limited to the allowed base (`v126_audit/`,
`v129_v131_audit/`, `v127_v128_audit/`, `v115_audit/`, `v113_v114_audit/` OOS
CSVs, `v103_v105_audit/`, raw data, carry). `v132/` (`v132_breadth.py`,
`v132_result.json`, manifest, logs) and `v133/` (`v133_deploy_v2.py`,
`v133_result.json`, manifest, logs) were first opened after the Part A save.
Part A imports no v132/v133/v129/v125/v115/v114/v110/v104/v103/v92/v94 leader
module (all formulas inline from the assignment text + audited OOS CSVs + raw
data + carry + audited panel code).

## A. Number comparison (blind vs leader)

Key maps: blind `v132.phases`/`phase_summary`/`ic_per_asset` <->
leader `primary_phase_mean` (`per_phase` [monthly, fullDD] pairs,
`monthly_pct`, `worst_year_dd`, `yearly_mean`) + `ic_by_asset`;
blind `v133.scenarios` <-> leader `primary_scenarios`; blind
`v133.hidden_year_1m_execution_strict` (`orders_hidden_year`) <-> leader
`hidden_year_1m_execution_strict` (`orders`).

### v132 (8-asset breadth) — bit-exact

- Phase mean blind = leader: normal monthly 2.125 / worst DD 24.01;
  fee 1.866 / 25.78; exec 1.543 / 27.94. Max abs monthly diff 0.000pp
  (6 phases x 3 scenarios + means), max abs full-path DD diff 0.00pp.
- Per-phase normal blind = leader: [2.272/20.80, 2.438/20.71,
  2.219/18.47, 1.750/24.01, 1.970/21.83, 2.100/19.72]. Fee/exec cells
  exact (verified programmatically).
- Yearly means (mean over 6 blind phase yearlies) vs leader `yearly_mean`:
  max abs diff 0.005pp (rounding only; e.g. normal -1.35/16.24/48.79/
  52.63/36.67). No 1pp threshold exceeded.
- Per-asset OOS IC blind = leader exact (max abs diff 0.0):
  v92 vs y: ADA 0.0341, BNB 0.1088, BTC 0.0496, DOGE 0.0369, ETH 0.0648,
  SOL 0.0511, TRX 0.0050, XRP 0.0662;
  v94 vs y42: ADA 0.0215, BNB 0.1079, BTC 0.0342, DOGE 0.0444, ETH 0.0857,
  SOL 0.0445, TRX 0.0098, XRP 0.0598;
  v103 vs y6: ADA 0.0371, BNB 0.0459, BTC 0.0246, DOGE 0.0329, ETH 0.0268,
  SOL 0.0407, TRX -0.0168, XRP 0.0383. No 0.01 threshold exceeded.
- Reference 5-asset v126 (2.311/2.09/1.815) matches the audited number;
  8-asset breadth lowers the phase mean (2.125) and raises worst DD
  (24.01 vs 20.93).

### v133 (tranched + pvol, 5-asset) — bit-exact

- Scenarios blind = leader: normal monthly 2.440 / full-path DD 15.18;
  fee 2.222 / 16.64; exec 1.950 / 18.42. Max abs monthly/full-DD diff
  0.000pp/0.00pp.
- Yearly blind = leader in all 3 scenarios x 5 years (net/DD/fills exact):
  normal 22.64/14.17/2085, 15.85/10.56/2190, 49.61/8.08/2190,
  47.51/9.39/2189, 35.49/8.69/2156; fee/exec cells exact.
- Hidden blind = leader: net 29.00, monthly 2.146, DD 10.06, sharpe 1.56,
  fills 2161, maker 0.849, orders 9206 (blind key `orders_hidden_year` =
  leader `orders`). Diffs 0 on all fields.
- Reference v127 (2.378/2.156/1.879, hidden 30.17/9.98) matches the audited
  number; pvol sizing raises tranched return 2.378 -> 2.440 while full-path
  DD improves 16.76 -> 15.18 (normal).
- No 1pp / 0.5pp / 0.01 threshold exceeded anywhere in v132 or v133.

## B. Why blind matched

- v132: blind rebuilds the v114 extended panel (Bitstamp >= 2013-01-01 +
  Coinbase BTC, Coinbase ETH, spot_2017 prefix where exists, none for
  DOGE/TRX/ADA) and the v103 base panel (spot prefix + USD-M + flow feats)
  for all 8 assets (ids 0..7 in assignment order), HGB v92 h42 cutoff-408h /
  v94 h18/42/84 cutoff-576h / v103 h6/h18 cutoff-312h over all non-target
  columns (26 v114 + 36 v103 feats), un-subsampled LO/LS weights with
  n_active/8 exposure, own 0.20-cap-2 scales (W.shift(2), trailing 360/
  min-120), union >= first v103 t, books 0.25/0.25/0.5, sequential v110
  engine target 0.15 ungoverned. Bit-exact ICs + phases confirm identical
  panels, embargoes, asset-id order, and N=8 exposure.
- v133: blind retrains 5-asset pvol by the v129 method (fv = log rolling-42
  std of diff(log open) shift -43, HGB v92 params, cutoff anchor-102*4h,
  t+44*4h < cutoff, pvol = exp(pred)) on the v114 extended + v103 base
  5-asset panels — pvol Spearman matches the audited v129 numbers bit-exact
  (v114 0.5275/0.5283/0.6272/0.6935/0.6604; v103 0.5068/0.5031/0.6141/
  0.7032/0.6650) — then left-joins pvol onto the audited 5-asset OOS CSVs,
  replaces vol42 where available, recomputes LO/LS weights (N=5), tranches
  (mean over 6 phase schedules), own scales, books/engine/hidden identical
  to v127. Bit-exact scenarios + hidden confirm the 5-asset (not 8-asset)
  interpretation: leader `v133_deploy_v2.py` never overrides SYMS, so it
  trains on 5 assets (see C).
- Carry unchanged (`carry_oos_fee0.0004.parquet`) on both sides; v103-panel
  opens drive the engine; live [2021-09-24, 2026-09-23).

## C. Look-ahead audit

### `v132/v132_breadth.py` — no look-ahead found

- Setup (:31-36): reuses audited `v129` module chain (`v125`/`v115`/`v103`);
  overrides `SYMS` to SYMS8 in `ext.v92`, `ext.v94.v92`, `v103.v92` and
  `v125.SYMS = 8` (partial-exposure N). No data touched. Pass.
- Panels/training (:37-45): `ext.v92.build()` (v114 extended), `ext.v94`
  targets, `v103.build()` (v103 base) with audited `train_predict` per
  anchor (v92/v94/v103 embargoes as in v113/v114 + v103 audits); test year
  never used for fit; FEATS exclude y*/t/open/sym/bar (all non-target cols).
  New assets use xs_universe bars with no spot prefix and ids 5..7 per
  docstring — blind rebuild with the same rule matches bit-exact,
  confirming the leader's `load_asset_ext` obeys the assignment. Pass
  (see v113/v114 + v103 audits for panel causality).
- ICs (:46-50): per-asset OOS Spearman(pred, y/y42/y6) — reporting. Pass.
- Portfolio (:52): `v129.phase_mean(ext, p92, p103, lo, ls, fl)` — audited
  v125 raw/phased (past-only keep pos%6==p ffill), causal vol scales,
  `v110.run/summarize` (2-bar execution lag, target 0.15 ungoverned),
  phase-mean reporting. Pass (see v126/v129 audits).
- Reporting (:53): phase mean + static 5-asset reference. No selection or
  refit. No normalisation/threshold fitting on locked test; costs/funding
  per AGENTS.md. No look-ahead found.

### `v133/v133_deploy_v2.py` — no look-ahead found

- Rebuild (:39-50): same 5-asset panel builds + `train_predict` as v132
  but WITHOUT any SYMS override — confirms v133 is 5-asset (v127 base),
  not 8-asset. Pass.
- pvol (:51-57): `v129.vol_predict` on v114/v103 panels with
  `EMBARGO_BARS` (102) + `swap` (pvol.fillna(vol42) on (t, sym)) — audited
  v129 fv shift (-43 = std of r[t+2..t+43]) and +44 filter; sizing at t
  uses only causal pvol(t) or contemporaneous vol42(t). Pass.
- Tranching/books (:59-68): `v125.phased(raw, 0..5)` mean over six
  past-only schedules; `vol_target_scale` causal (W.shift(2), trailing
  window, cap 2); per-book opens; books 0.25/0.25/0.5. Pass.
- Portfolio (:70-73): `v110.run/summarize` target 0.15 ungoverned, three
  v92 scenarios; forward return is execution accounting with 2-bar lag.
  Pass.
- Hidden (:75-91): whole-index s 0.15, Wt/carry_exp causal, `v104`
  fill_strict + v104 cost path; 1m post-T data affects only fill cost at
  t, not the signal; no band. Pass.
- No normalisation/threshold fitting on locked test; costs/funding per
  AGENTS.md. No look-ahead found.

## D. Post-hoc corrections / protocol log

- No spec reinterpretation after opening `v132/`/`v133/`. Part A script
  and `replication.json` were frozen pre-open except for one pre-open fix
  (logged here): the first blind run extended BOTH the v114 and v103
  panels with Coinbase/Bitstamp history; corrected before the Part A save
  to extend ONLY the v114 panel (v103 stays base-only, matching the
  audited v103 construction). After the fix, v133 pvol train rows match
  the audited v129 rows exactly (v114 46120/…/89950, v103 33293/…/77123)
  and v132 v103 train rows drop to base-8 levels (42965/…/113093). The
  saved `replication.json` is the corrected run; tests pass 3/3.
- Blind `v133.hidden` stores `orders_hidden_year` (= leader `orders`,
  9206) and additionally `fills_hidden_year` (2161); blind v132 IC dicts
  carry `_pooled`/`_n_rows` extras. No numeric impact.
- Leader v132 `yearly_mean` is rounded to 2dp; blind recomputed means from
  rounded phase nets differ by <= 0.005pp (rounding only).

## E. Manifest notes / verdict

- `v132/result_manifest.json`: track B, `rejected`, `live_approved:false`,
  audit pending. Phase-mean 2.125/24.01, 1.866/25.78, 1.543/27.94 matches
  blind bit-exact. Note (8 assets, weak new-asset IC incl TRX ~0, worse
  than 5-asset 2.311/2.09/1.815) matches the numbers.
- `v133/result_manifest.json`: track A, `rejected`, `live_approved:false`,
  audit pending. Tranched scenarios 2.44/14.17, 2.222/14.73, 1.95/15.43
  (full-path DD 15.18/16.64/18.42) and hidden 29.0/10.06/0.849/9206 match
  blind bit-exact. Reference v127 matches the audited numbers.
- Blind replication is bit-exact on all v132 ICs/per-phase cells/summaries
  and all v133 scenario yearlies/hidden execution. No look-ahead in panel
  breadth, pvol swap, tranching, scales, or engine/hidden paths. Audit
  complete; leader files untouched.
