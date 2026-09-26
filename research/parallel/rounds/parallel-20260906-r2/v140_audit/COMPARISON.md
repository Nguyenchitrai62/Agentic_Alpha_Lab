# v140 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v140_audit/` +
`tests/test_v140_audit.py` only. Base: audited v132_v133 replication
(v133 5-asset configuration). No leader files edited.

Blind protocol: `replication.json` (`replicate_v140.py`,
`tests/test_v140_audit.py` passing 3/3) was saved BEFORE opening `v140/`.
Pre-save reads were limited to the allowed base (`AGENTS.md`,
`OPENCODE_VF_COMMON.md`, `OPENCODE_V140_AUDIT.md`, skill,
`v132_v133_audit/replicate_v132_v133.py` + `replication.json` +
`COMPARISON.md`, `tests/test_v132_v133_audit.py`, raw data dirs, carry;
directory listing showed `v140/` filenames but no `v140/` file contents
were read). Part A imports no v140/v138/v133/v129/v125/v115/v114/v110/
v104/v103/v92/v94 leader module (all formulas inline from the assignment
text + audited v132_v133 code + raw data + carry).

## A. Number comparison (blind vs leader)

Key maps: blind `anchors_v92[].ic_vs_s42/ic_vs_y` <-> leader
`ic_v92[anchor].ic_new/ic_old_y`; blind `scenarios[sc].yearly/monthly_pct/
full_path_dd` <-> leader `primary_scenarios[sc]` (same keys).

### v92 IC — bit-exact

| anchor | blind s42 | leader new | blind y | leader old y |
|---|---|---|---|---|
| 2021-09-24 | 0.0647 | 0.0647 | 0.0729 | 0.0729 |
| 2022-09-24 | 0.0013 | 0.0013 | 0.0060 | 0.0060 |
| 2023-09-24 | 0.0766 | 0.0766 | 0.0986 | 0.0986 |
| 2024-09-24 | 0.1033 | 0.1033 | 0.0991 | 0.0991 |
| 2025-09-24 | 0.1925 | 0.1925 | 0.2043 | 0.2043 |

Max abs IC diff 0.0 (threshold 0.01). No threshold exceeded.

### Scenarios — bit-exact

| scenario | blind monthly | leader monthly | blind fullDD | leader fullDD |
|---|---|---|---|---|
| normal | 1.368 | 1.368 | 18.58 | 18.58 |
| fee_stress | 1.127 | 1.127 | 20.24 | 20.24 |
| execution_stress | 0.826 | 0.826 | 22.26 | 22.26 |

Yearly cells blind = leader in all 3 scenarios x 5 years
(net/DD/fills exact, max abs net diff 0.00pp, DD diff 0.00pp, fills diff 0):
normal 9.75/14.26/2101, 11.82/12.70/2190, 21.59/14.23/2190,
32.31/11.52/2190, 14.47/13.12/2151; fee/exec cells exact.
No 1pp return / 0.5pp DD threshold exceeded anywhere.

Reference v133 (2.44/2.222/1.95) matches the audited number; forward-Sharpe
targets lower the tranched result to 1.368/1.127/0.826.

## B. Why blind matched

- Targets: blind per-asset time order `r=log(open/open[-1])`,
  `R=log(open[t+1+h]/open[t+1])`, `fv=rolling-h std(ddof=1,min=h)` of `r`
  `shift(-(h+1))`, `s=clip(R/(fv*sqrt(h)),-4,4)` non-finite->NaN — identical
  to leader `add_sharpe_targets` (`diff(log open, prepend nan)`,
  `R=lo[1+h:]-lo[1:]`, `rolling(h).std().shift(-(h+1))`, clip, non-finite->NaN).
- Panels/embargoes: blind 5-asset v114-extended (Bitstamp>=2013-01-01+
  Coinbase BTC, Coinbase ETH, spot_2017 prefix where exists) + v103-base
  +flow, HGB v92 params, v92 s42 cutoff-102h + t+43h<cutoff, v94
  s18/s42/s84 cutoff-144h + t+(h+1)h<cutoff mean, v103 s6/s18 cutoff-78h
  mean — identical to leader `v138.window` + `H/EMBARGO_BARS`
  (42/102, (18,42,84)/144, (6,18)/78, verified programmatically).
- Features: blind 26 v114 + 36 v103 cols excluding `y*`/`s*` — identical to
  leader `f92` (p92 has only `y`, so excluding `y` = excluding `y*`; p92 has
  no `s`), `f94`/`f103` (explicit `not startswith y` + `s\d+` regex).
- Pipeline: blind pvol v129 method (fv=log roll42 std shift-43, cutoff-102h,
  t+44h<cutoff, exp(pred), left-join replace) matches audited v129 rows
  bit-exact (v114 46120/../89950, v103 33293/../77123); LO/LS weights N=5,
  `tranche_mean`, own 0.20-cap-2 scales (`W.shift(2)`, trailing 360/min-120),
  books 0.25/0.25/0.5, sequential engine target 0.15 + carry — identical to
  leader `v125.raw_lo/raw_ls/phased/vol_target_scale` + `v110.run/summarize`.

## C. Look-ahead audit

### `v140/v140_forward_sharpe_target.py` — no look-ahead found

- Target timing (:33-48): `r[k]` uses opens <= k only; `R`/`fv` use opens
  up to `t+1+h` (label realised at `t+1+h`, same time as old `y`). Labels
  are not features. `window` (:52-58) keeps the audited cutoffs/embargoes
  and the `t+(h+1)*4h<cutoff` row filter, so every training label is fully
  realised before the cutoff. Test rows are reporting only. Pass — the
  docstring claim "label is realised at the same time as before" is correct.
- Features (:60-67): `p92` has only `y` (verified: 26-col `f92` excludes it);
  `p94=add_targets(p92)` + `s` targets, `f94` excludes `y*` and `s\d+`;
  `p103` + `s`, `f103` excludes `y*` and `s\d+`. No target in features. Pass.
- Training (:69-84): `window(p94,a,"s42",42,102)` / per-horizon `s18/s42/s84`
  with 144 / `s6/s18` with 78, HGB v92 params, mean over horizons for
  v94/v103 — as specified. No refit on test; no normalisation/threshold fit.
  Pass.
- pvol (:87-93): `v129.vol_predict` on `p92/f92` + `p103/f103` with 102-bar
  embargo (audited fv shift -43 +44 filter); `swap` is `pvol.fillna(vol42)`
  on `(t,sym)` — sizing at `t` uses only causal `pvol(t)`/`vol42(t)`. Pass.
- Tranching/books (:96-103): `v125.phased(raw,0..5)` = mean over six
  past-only schedules; causal `vol_target_scale` (`W.shift(2)`, trailing
  window, cap 2); books 0.25/0.25/0.5; `idx>=p103.t.min()`. Pass.
- Portfolio (:106-108): `v110.run/summarize` target 0.15 ungoverned, three
  `SCEN` fees; forward return is execution accounting with 2-bar lag. Pass.
- Costs/funding per AGENTS.md; no normalisation/threshold tuning on locked
  test. No look-ahead found.

## D. Post-hoc corrections / protocol log

- No spec reinterpretation after opening `v140/`. Part A script and
  `replication.json` were frozen pre-open except for one pre-open test fix
  (logged here): `tests/test_v140_audit.py` initially asserted constant-drift
  `s` is all-NaN; corrected pre-open to expect clip-to-4 (floating-point
  residual variance makes `fv` tiny-but-finite, so the huge ratio clips).
  Replication numbers unchanged; tests pass 3/3.
- Blind extras (`ic_per_asset`, `anchors_v94/v103`, `anchors_pvol_*`,
  `n_replaced`, `feats*`, `union_bars 10950`, `oos_span`) have no numeric
  impact on the compared fields.

## E. Manifest notes / verdict

- `v140/result_manifest.json`: track A, `rejected`, `live_approved:false`,
  audit pending. Scenarios 1.368/14.26, 1.127/15.0, 0.826/17.28
  (full-path DD 18.58/20.24/22.26) match blind bit-exact.
- Blind replication is bit-exact on all v92 ICs (new + old) and all scenario
  yearlies/summaries. No look-ahead in target timing, features, embargoes,
  pvol swap, tranching, scales, or engine. Audit complete; leader files untouched.
