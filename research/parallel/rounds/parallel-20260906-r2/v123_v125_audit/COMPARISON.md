# v123 + v124 + v125 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v123_v125_audit/` +
`tests/test_v123_v125_audit.py` only. Base: audited v115 replication
(books, v110 sequential engine, v104 hidden path), v118 bands, v113_v114
(v114 extended panel, v92/v94 training). No leader files edited.

Blind protocol: `replication.json` (+ `predictions_v123_v92.csv`,
`predictions_v123_v94.csv`, `held_v124.csv`, `replicate_v123_v125.py`,
`tests/test_v123_v125_audit.py` passing) was saved BEFORE opening `v123/`,
`v124/` or `v125/`. Pre-save reads were limited to the allowed base
(`v115_audit/`, `v113_v114_audit/`, `v118_v119_audit/`, `v103_v105_audit/`
listing, raw data, carry). `v123/` / `v124/` / `v125/` (scripts, results,
manifests, logs) were first opened after Part A save. Part A imports no
v123/v124/v125/v115/v114 leader module (all formulas inline from assignment
text + audited OOS CSVs + raw data).

## A. Number comparison (blind vs leader)

Key maps: blind `v123.primary` <-> leader `primary_portfolio`;
blind `v123.blend` <-> leader `secondary_v96_blend`;
blind `v124.hidden_year_1m_execution_strict` <->
leader `primary_hidden_year_strict_band005`;
blind `v125.tranched` <-> leader `primary_tranched`;
blind `v125.reference_phase0` <-> leader `reference_phase0_v115`.

### v123 (MTF ribbon on v114 panel) — bit-exact, all scenarios

- ICs blind = leader (`run.log` lines 1-5): v92 0.0674/-0.0413/0.1308/
  0.1094/0.1458; v94 0.1516/-0.0382/0.0794/0.1026/0.1431. Max abs IC diff
  0. No 0.01 threshold exceeded.
- Primary (v115 portfolio t15 ungoverned) yearly net/DD/fills/sharpe/
  monthly: max abs net diff 0.00pp over 3 scenarios x 5 years (15 cells);
  max abs DD diff 0.00pp (15 yearly + 3 full-path). No 1pp / 0.5pp
  threshold exceeded.
- Headlines blind = leader: primary normal monthly 2.589 / worst DD
  15.98 / full-path 15.98; fee 2.371/16.44/17.22; exec 2.101/17.05/19.45.
- Yearly primary normal blind = leader: 16.33/17.78/62.74/49.26/39.24;
  DDs 15.98/11.07/8.15/7.15/9.88; fills 1811/2184/2178/2187/2126.
- Secondary blend normal blind = leader: 8.43/29.26/64.88/47.88/38.23;
  DDs 20.61/8.79/7.98/7.15/12.11; fills 1593/2166/2152/2176/2049;
  monthly 2.621/2.413/2.154. Fee/exec cells exact.

### v124 (band 0.05 hidden strict) — bit-exact after fix (see D)

- Final blind = leader: net 33.95, monthly 2.468, DD 9.61, sharpe 1.81,
  fills 259, maker 0.819, orders 474. Reference band0 36.0/10.31/0.853.
- Initial blind (pre-fix) was 26.98/12.15/0.926/436/251 (return diff
  6.97pp, DD diff 2.54pp — thresholds exceeded). Cause was auditor bug
  (wrong books + live gating + maker mask), not leader error. After fix,
  diffs 0.

### v125 (tranched daily) — bit-exact, all scenarios

- Tranched normal blind = leader: 19.76/12.09/51.43/47.24/36.86;
  DDs 15.37/12.27/7.93/9.43/8.58; fills 2086/2190/2190/2189/2156;
  monthly 2.378/2.156/1.879; full-path 16.76/18.23/20.24.
- Reference phase0 blind = leader = v115 primary: 13.91/16.73/63.52/
  51.22/42.55; DDs 16.78/12.69/7.44/10.60/9.01; monthly 2.608/2.388/2.114.
  Confirms phase0 = v115.

## B. Why blind matched

- v123: panel rebuilt from raw with audited v113_v114 formulas +
  MTF extras (4h SMA50/200 log-ratios, rib4 NaN while SMA200 NaN; daily
  SMA350/1400 w50/w50_slope/ribw 0-while-1400-NaN NaN-while-350-NaN
  asof-backward, rib_agree sum). HGB v92 h42/408h + v94 h18/42/84/576h,
  all non-target cols (33 feats). Books 0.25/0.25/0.5 with audited v103,
  20%-cap-2 scales, s 0.15 sequential v110, blend 0.5/0.5 scale1.
  Train rows match v114 audit (45915/56865/67815/78795/89745).
- v124: v115 books from audited OOS CSVs, s 0.15 vectorised whole-index,
  held band 0.05 continuously from first row (no live gating), v104
  fill_strict + cost path (carry 0.6*s, funding 0.00005 on held).
- v125: un-subsampled LO/LS frames (no keep), per-phase keep
  pos%6==phase ffill mean over 6, own 0.20-cap-2 scales, books
  0.25/0.25/0.5, s 0.15 sequential. Phase0 reproduces v115 bit-exact.

## C. Look-ahead audit

### `v123/v123_mtf_ribbon.py` — no look-ahead found
- `mtf_features` (:41-56): 4h rolling SMA50/200 on closed closes incl
  current (available at close_time[t]); rib4 NaN while SMA200 NaN;
  daily SMA350/1400 on closed daily closes, asof-backward on close_time
  (same as v92 daily); w50_slope diff(5) on log SMA350. Pass.
- Training (:66-85): `train_predict` with v92/v94 embargoes, all
  non-target cols (assert MTF present). Test year never used for fit.
  Books/scales (`weights_from`/`weights_ls`/`vol_target_scale`) causal
  (daily ffill, W.shift(2) trailing). Portfolio `v110.run/summarize`
  with p103 opens target 0.15 ungov; blend `v103.evaluate` scale1. Pass.

### `v124/v124_band_execution.py` — no look-ahead found
- Books/s (:32-38): `v115.books_v115` + `v99` wrapper (shift-2/shift-1,
  trailing 360/min-120 cap2). No new training. Pass.
- Band (:40-45): held from 0, per-asset `held=row if |row-held|>0.05`
  continuously over whole index (docstring notes path differences before
  hidden year are possible — expected, held state is causal). Turnover
  `diff held`; gross `held*r_next`; funding on held; carry unchanged.
  Forward return is execution accounting (same lag as v104). Pass.
- Hidden (:46-57): `v104.fill_strict` + v104 cost path; 1m post-T data
  only affects fill cost at t, not signal. Pass.

### `v125/v125_tranching.py` — no look-ahead found
- Raw frames (:37-58): audited LO/LS formulas without keep step;
  `phased` (:61-63) keeps pos%6==phase ffill mean — each phase uses only
  past kept rows, mean is causal smoothing. Asserts phase0 equals audited
  `weights_from`/`weights_ls`. Pass.
- Scales/books (:87-89): own vol targets on tranched weights (shift-2
  trailing), union `>=p103.t.min()`, `v110.run` target 0.15 ungov. Pass.

## D. Post-hoc corrections / protocol log

- Initial Part A blind v124 bug (disclosed): `part_a2_v124` took
  v123-retrained books (extra-feature panel) instead of v115 books, used
  live-gated held for the first (unused) path, and computed maker rate
  with `maker[mask.values]` (row filter) instead of `maker[mask]`
  (elementwise). Result 26.98/12.15/0.926/436 vs leader 33.95/9.61/
  0.819/474.
- Fix after opening (documented here, script + replication.json updated):
  added `build_v115_books()` from audited OOS CSVs, held continuously
  from first row with no live gating (matching leader `:40-44`), maker
  rate `maker[orders].stack().mean()` elementwise. Re-ran A2 only
  (v123/v125 unchanged, train rows/ICs untouched). Now bit-exact on
  net/DD/sharpe/fills/maker/orders. Tests still pass.
- No spec reinterpretation for v123/v125; v123 ICs/nets and v125
  tranched/reference were bit-exact on first blind run.

## E. Manifest notes / verdict

- `v123/result_manifest.json`: track A, `rejected`, `live_approved:false`,
  audit pending. Primary monthly 2.589 / fills 10486 / 60 months and
  yearly 16.33/17.78/62.74/49.26/39.24 match blind.
- `v124/result_manifest.json`: track B, `rejected`, `live_approved:false`,
  audit pending. Hidden 33.95/9.61/0.819/474 and note (band cuts orders
  ~17x, DD 10.3->9.6 but net 36.0->33.95 under maker/taker) match blind.
- `v125/result_manifest.json`: track C, `rejected`, `live_approved:false`,
  audit pending. Tranched monthly 2.378 / fills 10811 and yearly
  19.76/12.09/51.43/47.24/36.86 match blind.
- Blind replication is bit-exact on all v123 ICs/yearlies, v124 hidden
  execution, and v125 tranched/reference in all scenarios. No look-ahead
  in MTF features, band timing, tranching, scales, or hidden fill rule.
  Audit complete; leader files untouched.
