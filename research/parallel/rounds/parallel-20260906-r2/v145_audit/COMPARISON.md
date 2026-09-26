# v145 blind audit — COMPARISON.md

Scope: `research/parallel/rounds/parallel-20260906-r2/v145_audit/` +
`tests/test_v145_audit.py` only. Base: audited v141_v142 replication
(`v141_v142_audit/replication.json`, `replicate_v141_v142.py`). No leader
files edited.

Blind protocol: `replication.json` (`replicate_v145.py`,
`tests/test_v145_audit.py` passing 3/3) was saved BEFORE opening
`v145/v145_result.json` or `v145/v145_xs_all_features.py`. Pre-save reads
were limited to the allowed base (`v141_v142_audit/` replication +
COMPARISON, `v132_v133_audit/` replication, `v129_v131_audit/` pvol rows,
`v113_v114_audit/` + `v103_v105_audit/` OOS CSVs, raw 4h/1d/funding/spot/
Coinbase/Bitstamp panels, carry, `v142/v142_cross_sectional_features.py` +
`v142_result.json` as the v142 literal-pipeline reference; directory listing
showed `v145/` filenames only, plus `v145/register.log` contents
(`closed: v142, successor: v145`) seen during listing). Part A imports no
v145/v142/v141/v133/v129/v125/v115/v114/v110/v104/v103/v92/v94 leader module
(all formulas inline from the audited replication + assignment text + raw
data + carry).

Key maps: blind `scenarios.{normal,fee_stress,execution_stress}` <->
leader `primary_scenarios.{normal,fee_stress,execution_stress}`;
blind `anchors_v92[].ic` <-> leader `ic[anchor].v92`;
blind `anchors_v103[].ic_vs_y6` <-> leader `ic[anchor].v103_y6`;
blind `xs_spec.{xs_v114,xs_v103}` <-> leader
`xs_features.{v114_panel,v103_panel_extra}`.
Thresholds per assignment: IC diff > 0.01, return diff > 1pp, DD diff > 0.5pp.

## A. Number comparison (blind vs leader)

### ICs — bit-exact

| anchor | blind v92 | leader v92 | blind v103_y6 | leader v103_y6 |
|---|---|---|---|---|
| 2021-09-24 | 0.1293 | 0.1293 | 0.0541 | 0.0541 |
| 2022-09-24 | -0.0413 | -0.0413 | 0.0247 | 0.0247 |
| 2023-09-24 | 0.0924 | 0.0924 | 0.0700 | 0.0700 |
| 2024-09-24 | 0.0887 | 0.0887 | 0.0301 | 0.0301 |
| 2025-09-24 | 0.1656 | 0.1656 | 0.0641 | 0.0641 |

Max abs IC diff 0.0 (threshold 0.01). Blind extras `ic_vs_y18`
(0.0540/0.0539/0.1052/0.0594/0.1106) and `anchors_v94.ic_mean_vs_h42`
(0.1625/-0.0395/0.1085/0.1039/0.1535) have no leader counterpart (leader
reports v92 + v103_y6 only). No IC threshold exceeded.

### Scenarios (literal v133 pipeline: 0.15 ungoverned flat-fee) — bit-exact

| scenario | blind monthly / fullDD | leader monthly / fullDD | diff |
|---|---|---|---|
| normal | 2.196 / 18.30 | 2.196 / 18.30 | 0 / 0.00pp |
| fee_stress | 1.974 / 19.24 | 1.974 / 19.24 | 0 / 0.00pp |
| execution_stress | 1.698 / 20.38 | 1.698 / 20.38 | 0 / 0.00pp |

Yearly nets/DDs/fills blind = leader in all 3 scenarios x 5 years (max abs
net diff 0.00pp, DD diff 0.00pp, fills diff 0):
normal: 11.89/16.04/2021, 21.11/7.57/2189, 54.15/12.02/2188,
32.86/9.35/2190, 32.62/9.09/2176;
fee: 9.77/16.39/2021, 18.22/7.99/2189, 49.85/12.54/2188,
28.69/9.56/2190, 29.14/9.14/2176;
exec: 7.17/16.94/2021, 14.70/8.50/2189, 44.65/13.18/2188,
23.65/9.83/2190, 24.91/9.23/2176.
No 1pp / 0.5pp threshold exceeded anywhere.

### Feature lists — exact

Blind `xs_v114` (20) = leader `v114_panel` (20):
ret6 snr6 ret42 snr42 ret90 snr90 ret180 snr180 ret540 snr540 vol42 vol180
vol_ratio ema20 ema200 d50 d200 f7 f30 volz.
Blind `xs_v103` (30) = leader `v114_panel` + `v103_panel_extra` (20+10):
above + tbr_1 tbr_6 tbr_42 flow_6 flow_42 tbr_z tsize_z ntr_z rng6 clv6.
Blind `feats114x_n=66` (26+40), `feats103x_n=96` (36+60). No mismatch.

## B. Why blind matched

- Panels: blind rebuilds v114-extended (Bitstamp>=2013-01-01 + Coinbase BTC,
  Coinbase ETH, spot_2017 prefix) + v103-base + flow exactly as the audited
  v141_v142 replication (26/36 feats, btc_* join). pvol on original sets
  matches v129 bit-exact (46120/../89950 + 0.5275/../0.6604 and
  33293/../77123 + 0.5068/../0.6650).
- XS: blind `xs_c=c-mean_t(c)`, `xr_c=rank(pct=True)` per t over 5 majors
  for the exact 20 v114 cols + 10 extra v103 cols matches leader
  `base92`/`base103` + `v142.BASE/FLOWX` override (same col tuples; rank
  default average method; NaNs propagate). v92/v94 on all columns (26+40=66
  feats), v103 on all columns (36+60=96), same HGB params/embargoes
  (v92 h42/102, v94 h18/42/84/144, v103 h6/h18/78), pvol on original sets
  both sides. Bit-exact ICs confirm identical panels, xs/xr timing,
  embargoes, and feature sets.
- Portfolio: blind tranche-mean/6 + own 0.20-cap-2 scales + books
  0.25/0.25/0.5 + union idx>=first-v103 + sequential flat-fee engine
  (target 0.15 ungoverned, SCEN fees 0.0002/0.0006/0.0006+0.0005 slip,
  funding 0.00005 long, carry cost 2*0.0004/1.2) matches leader
  `v125.phased/raw` + `vol_target_scale` + `v110.run(p103,books,0.15,False,
  fee,slip)/summarize`. Bit-exact monthlies/yearlies/DDs/fills confirm
  identical books, vol/s, cost accounting, and full-path DD.

## C. Look-ahead audit

### `v145/v145_xs_all_features.py` — no look-ahead found

- Chain (:21-23): imports audited `v142` module (which chains
  `v129/v125/v115/v103/v110/v104/...`); no data touched. Pass.
- XS lists (:32-37): `base92` = all p92 cols except y/t/open/sym/bar +
  asset/rib + btc_*; `base103` = all p103 cols except y/t/open/sym/bar +
  asset/rib + btc_* + startswith-y. Verified against live builds: p92 has
  31 cols with a single `y` target (no y6/y18/y42/y84), so base92 = 20 cols
  with no target leakage; p103 has 43 cols with y/y6/y18, all three excluded
  via `y` + `startswith("y")`, so base103 = 30 cols with no target leakage.
  Lists match blind exactly (20 + 10 extra). Pass.
- `v142.BASE/FLOWX` override (:36-37): sets v114 XS to base92 (20) and v103
  extra to base103-not-in-base92 (10 flow cols); then calls `v142.main()`
  with `HERE` overridden so outputs land in `v145/`. Same `add_xs`
  (groupby-t mean + `rank(pct=True)`) over majors present at the same bar t;
  all inputs are already-causal feature values at t (bars close
  simultaneously); no future-t row enters. Rank default average; NaNs
  propagate. Pass (see v142 audit).
- Models/pvol/books (:39 + v142 :43-87): v92/v94 on expanded v114 sets,
  v103 on expanded v103 set, same anchors/embargoes/targets; pvol on
  `p92/f92_base` + `p103/f103_base` (original sets, xs excluded) via
  `swap` fillna — audited causal sizing; tranched books + `v110.run` target
  0.15 ungoverned x3 fee scenarios. Forward return is execution accounting.
  Pass.
- Plumbing (:40-47): reads the `v142_result.json` just written by the
  overridden `v142.main()`, renames version to v145, attaches `xs_features`
  + `reference_v142`, writes `v145_result.json`, deletes the temp file.
  No data transform; `reference_v142` 2.551/2.33/2.055 matches audited v142.
  Pass.
- No threshold tuning on locked test; costs/funding per AGENTS.md. Pass.

## D. Post-hoc corrections / protocol log

- No spec reinterpretation after opening `v145/`. Part A script and
  `replication.json` frozen pre-open; tests pass 3/3 pre- and post-open.
- One pre-save disclosure (not a numeric input): `v145/` directory listing
  (filenames only) + `v145/register.log` contents (closed v142, successor
  v145) were seen while verifying the write scope before Part A ran. No
  `v145_result.json` or `v145_xs_all_features.py` contents were opened
  before the Part A save.
- Blind extras with no numeric impact: `anchors_v94`, `ic_vs_y18`,
  `feats114x/feats103x` lists, `n_replaced`, pvol anchors, per-year sharpe/
  fills/months.

## E. Manifest notes / verdict

- `v145/result_manifest.json`: track C, `rejected`, `live_approved:false`,
  audit pending. primary_scenarios 2.196/1.974/1.698 (full-path
  18.30/19.24/20.38) vs reference_v142 2.551/2.33/2.055 and reference_v133
  2.44/2.222/1.95 — all-features xs/xr underperforms the 9+3-col v142 XS on
  monthly (-0.355pp normal) at higher DD (18.30 vs 16.26), with yearly mix
  11.89/21.11/54.15/32.86/32.62. Blind reproduces it bit-exact.
- Blind replication is bit-exact on all ICs, all scenario rows/yearlies/
  fills/DDs, and all XS feature lists. No look-ahead in xs/xr timing, target
  exclusion, pvol exclusion, tranching, scales, or flat-fee cost path. Audit
  complete; leader files untouched.

## Files

- `replication.json` (Part A, blind), `replicate_v145.py`,
  `tests/test_v145_audit.py` pass 3/3.
