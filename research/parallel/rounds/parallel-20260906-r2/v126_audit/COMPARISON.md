# v126 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v126_audit/` +
`tests/test_v126_audit.py` only. Base: audited v123_v125 replication
(v125 un-subsampled LO/LS weight formulas and phase helper) and audited
v115 (books, v110 sequential engine). No leader files edited.

Blind protocol: `replication.json` (`replicate_v126.py`,
`tests/test_v126_audit.py` passing) was saved BEFORE opening `v126/`.
Pre-save reads were limited to the allowed base (`v115/`
`v115_result.json`/`v115_candidate.py` + `v115_audit/`, `v113_v114_audit/`
OOS CSVs, `v103_v105_audit/`, `v123_v125_audit/` replication + script,
raw data, carry). `v126/` (script, result, manifest, log) was first
opened after the Part A save (phase0==v115 verified pre-open:
phase0 normal monthly 2.608 / fullDD 16.78). Part A imports no
v126/v125/v115/v114/v103/v110/v92/v94 leader module (all formulas inline
from the assignment text + audited OOS CSVs + carry + v103 opens).

## A. Number comparison (blind vs leader `v126/v126_result.json`)

Key map: blind `phases["0".."5"]` <-> leader `phases.p0..p5`;
blind `phase_summary` <-> leader `summary`/`primary_phase_mean`.

- All 6 phases x 3 scenarios: max abs monthly diff 0.000pp,
  max abs full-path DD diff 0.00pp, max abs worst-year DD diff 0.00pp,
  max abs yearly net diff 0.00pp (30 cells), max abs yearly DD diff
  0.00pp (30 cells), max abs fills diff 0. No 1pp return / 0.5pp DD
  threshold exceeded anywhere.
- Headlines blind = leader (`run.log` lines 1-6):
  p0 2.608/2.388/2.114 DD 16.78/17.31/19.13;
  p1 2.501/2.281/2.008 DD 15.87/17.12/19.30;
  p2 2.566/2.346/2.072 DD 16.74/18.05/20.18;
  p3 2.094/1.871/1.592 DD 12.59/13.34/14.89;
  p4 2.067/1.847/1.573 DD 18.65/20.13/21.94;
  p5 2.029/1.808/1.532 DD 20.93/22.44/24.32.
- Yearly normal nets blind = leader: p0 13.91/16.73/63.52/51.22/42.55;
  p1 21.46/13.17/58.02/49.25/35.78; p2 33.24/14.09/47.42/56.30/30.53;
  p3 24.18/18.24/37.55/39.01/23.53; p4 16.50/6.02/55.93/36.04/30.26;
  p5 5.31/6.13/41.04/41.23/49.91. DDs/fills/sharpe exact (e.g. p0
  DDs 16.78/12.69/7.44/10.60/9.01 fills 1831/2180/2180/2177/2115).
- Summary blind = leader: normal mean 2.311 min 2.029 max 2.608
  max_full_dd 20.93; fee 2.090/1.808/2.388/22.44; exec 1.815/1.532/
  2.114/24.32. (Blind file additionally stores full_path_dd
  mean/min per scenario: 16.93/12.59 normal, 18.07/13.34 fee,
  19.96/14.89 exec — same max.)
- Phase 0 = v115: blind phases["0"] == `v115_audit/replication.json`
  `primary_t15` bit-exact in all scenarios/years (asserted in tests).

## B. Why blind matched

- Books: blind recomputes un-subsampled LO/LS frames from audited OOS
  CSVs with inline v125 formulas (ribbon gating, vol42 normalisation,
  gross/active scaling), then per phase keeps pos%6==p ffill fillna0 —
  identical to leader `v125.raw_lo/raw_ls` + `v125.phased(R,[ph])`
  (leader asserts phase0 equals audited `weights_from`/`weights_ls`).
  Position base (0..10949 over the sorted 10950-bar OOS index) matches:
  leader `pos=np.arange(len(W))`, blind `np.arange(len(W_raw))`.
- Scales/books: blind own 0.20-cap-2 `vol_scale` (W.shift(2),
  trailing 360/min-120, NaN->1) on phased weights with v114 opens
  (b_lo/b94) and v103 opens (b103); union `>= first v103 t`; books
  0.25/0.25/0.5 — identical to leader `:45-49`
  (`vol_target_scale` + reindex/fillna). v114-vs-v103 OOS spans are
  identical 10950 bars so the union restriction is a no-op.
- Engine: blind sequential loop mirrors `v110.run` (0.8 books + 0.6
  carry, live [2021-09-24,2026-09-23), ungoverned, fee/slip per v92
  SCEN, 0.00005 long funding, 2*0.0004/1.2 carry cost) with p103 opens
  and target 0.15; `summarize_seq` mirrors `v110.summarize` (yearly
  [anchor,anchor+365d), geometric monthly, full-path DD over live
  equity). Bit-exact match confirms identical timing (first rebalance
  hours 00/04/08/12/16/20 UTC per `run.log`).

## C. Look-ahead audit (`v126/v126_phase_dispersion.py`)

- Docstring (:1-9): diagnostic, no selection; phase 0 = v115; phase
  mean is the timing-luck-free estimate. Fixed before running. Pass
  (intent is measurement, manifest `rejected` matches).
- Panel/training (:29-40): rebuilds the v114 extended panel and
  retrains v92 LO / v94 LS / v103 LS per anchor via `train_predict`
  with the audited v92/v94 embargoes (same call pattern as
  `v115_candidate.books_v115` and `v125_tranching.main`). No new
  features; test year never used for fit. Pass (see v115/v123 audits).
- Raw frames (:41): `v125.raw_lo/raw_ls` — contemporaneous
  pred/rib/vol42 only, no forward input. Pass.
- Phasing (:44): `v125.phased(R,[ph])` keeps pos%6==ph ffill then
  single-phase mean — each phase uses only past kept rows; no future
  row enters any weight. `phased` sums over the requested list only.
  Pass.
- Scales/books (:45-49): union restricted to `>= p103.t.min()`;
  `vol_target_scale` is causal (W.shift(2), trailing window, cap 2);
  per-book opens (v114 panel for b_lo/b94, v103 panel for b103).
  Pass.
- Portfolio (:51-52): `v110.run/summarize` with p103 panel opens,
  target 0.15 ungoverned, three v92 scenarios. Governor unused
  (False); forward return is execution accounting with the same 2-bar
  lag as v104/v110. Pass.
- Reporting (:55-59): mean/min/max monthly + max full-path DD across
  phases; `primary_phase_mean = summary` alias. Pure reporting, no
  selection or refit. Pass.
- No normalisation/threshold fitting on locked test; no forward-return
  peek outside embargoed training; costs/funding per AGENTS.md. No
  look-ahead found.

## D. Post-hoc corrections / protocol log

- No spec reinterpretation after opening `v126/`. Part A script and
  `replication.json` unchanged since the pre-open save (phase0==v115
  asserted before opening).
- One test-only fix after the save: `test_replication_structure`
  compared the rounded `monthly_pct_mean` (3dp) against the float mean
  with `< 1e-9`; rounding accounts for up to ~0.0002 (observed
  0.00017). Tolerance relaxed to `< 1e-3`. No replication change.

## E. Manifest notes / verdict

- `v126/result_manifest.json`: track C, `rejected`,
  `live_approved:false`, audit pending ("awaiting OpenCode blind
  audit"). Scenario slots hold the phase-mean monthly and worst
  full-path DD (2.311/20.93, 2.09/22.44, 1.815/24.32); per-phase
  monthly + yearly normal nets all match blind. Note ("phase 0 is the
  best of six; luck-free estimate 2.31/2.09/1.82") matches the numbers.
- Blind replication is bit-exact on all six phases, all scenarios,
  all yearly nets/DDs/fills, and the mean/min/max summary. No
  look-ahead in phasing, scales, or engine. Audit complete; leader
  files untouched.
