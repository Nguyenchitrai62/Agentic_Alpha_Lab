# v127 + v128 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v127_v128_audit/` +
`tests/test_v127_v128_audit.py` only. Base: audited v123_v125 (tranching),
v126 (phase runs) and v115 replications. No leader files edited.

Blind protocol: `replication.json` (+ `predictions_v128_v92.csv`,
`predictions_v128_v94.csv`, `replicate_v127_v128.py`,
`tests/test_v127_v128_audit.py` passing) was saved BEFORE opening `v127/`
or `v128/`. Pre-save reads were limited to the allowed base
(`v123_v125_audit/`, `v126_audit/`, `v115_audit/`, `v113_v114_audit/` OOS
CSVs, `v110_audit/`, `v103_v105_audit/`, raw data, carry). `v127/`
(`v127_tranched_deploy.py`, `v127_result.json`, manifest, logs) and `v128/`
(`v128_halving_cycle.py`, `v128_result.json`, manifest, logs) were first
opened after the Part A save. Part A imports no v127/v128/v125/v115/v114/
v110/v104/v103/v92/v94 leader module (all formulas inline from the
assignment text + audited OOS CSVs + raw data + carry).

## A. Number comparison (blind vs leader)

Key maps: blind `v127.scenarios` <-> leader `primary_tranched_scenarios`;
blind `v127.hidden_year_1m_execution_strict` <-> leader
`hidden_year_1m_execution_strict` (leader key `orders` = blind
`orders_hidden_year`); blind `v128.anchors_v92_with` <->
leader `primary_cycle_features.ic_v92`; blind `v128.phases_with` <->
leader `primary_cycle_features.per_phase` (pairs
`[monthly_pct, full_path_dd]`); blind `v128.phase_summary_with` <->
leader `primary_cycle_features.summary` + `primary_phase_mean`; blind
`v128.phases_without`/`phase_summary_without` <-> leader
`reference_no_cycle` (same layout).

### v127 (tranched deploy + hidden strict) — bit-exact, all scenarios

- Scenarios blind = leader: normal monthly 2.378 / full-path DD 16.76;
  fee 2.156 / 18.23; exec 1.879 / 20.24. Max abs yearly net diff 0.00pp
  over 3 scenarios x 5 years (15 cells); max abs yearly DD diff 0.00pp;
  max abs monthly/full-path DD diff 0.00pp. No 1pp / 0.5pp threshold
  exceeded.
- Yearly normal blind = leader: 19.76/12.09/51.43/47.24/36.86; DDs
  15.37/12.27/7.93/9.43/8.58; fills 2086/2190/2190/2189/2156. Fee/exec
  cells exact (verified programmatically).
- Hidden blind = leader: net 30.17, monthly 2.223, DD 9.98, sharpe 1.62,
  fills 2161, maker 0.85, orders 9206. Diffs 0 on all fields. Reference
  v115 phase-0 hidden (36.0/10.31/0.853) is richer but rougher: tranching
  cuts hidden net 36.0 -> 30.17 while DD improves 10.31 -> 9.98.

### v128 (halving cycle) — bit-exact with and without features

- v92 ICs blind = leader, with features: 0.2392/0.0477/0.0876/0.0640/
  0.0246 (max abs diff 0.0). Reference without: 0.0863/-0.032/0.1152/
  0.1064/0.163 — matches the audited v114 ICs exactly (leader retrain
  reproduces the OOS CSVs). No blind-vs-leader 0.01 threshold exceeded
  anywhere.
- Per-phase (6 phases x 3 scenarios) blind = leader: max abs monthly
  diff 0.000pp, max abs full-path DD diff 0.00pp. E.g. with-features
  normal: p0 2.726/19.48, p1 2.471/18.76, p2 2.591/18.80, p3 2.233/
  18.97, p4 2.255/20.90, p5 2.265/23.45. Without-features phases equal
  the audited v126 phases bit-exact (p0 2.608/16.78 … p5 2.029/20.93).
- Summaries blind = leader: with normal mean 2.424 / worst DD 23.45;
  fee 2.213 / 24.70; exec 1.950 / 26.23. Without normal 2.311 / 20.93;
  fee 2.090 / 22.44; exec 1.815 / 24.32.
- `yearly_mean` blind (mean of the six blind phase yearlies) = leader in
  all 3 scenarios x 5 years (e.g. with normal 37.78/13.53/40.62/50.01/
  28.44; without normal 19.10/12.40/50.58/45.51/35.43).

### With- vs without-features effect (finding, not a mismatch)

- Per-anchor v92 IC with-minus-without: +0.1529/+0.0797/-0.0276/-0.0424/
  -0.1384. Four of five |diffs| > 0.01: the cycle features materially
  move OOS rank correlation (up in 2021/2022, down in 2023-2025).
- Phase-mean monthly with-minus-without: +0.113 normal, +0.123 fee,
  +0.135 exec. Worst full-path DD with-minus-without: +2.52pp normal
  (20.93 -> 23.45), +2.26pp fee, +1.91pp exec. Yearly redistribution
  (normal): 2021 19.1 -> 37.8, 2024 45.5 -> 50.0 up; 2023 50.6 -> 40.6,
  2025 35.4 -> 28.4 down. Cycle adds return and drawdown together.

## B. Why blind matched

- v127: tranched books recomputed from audited OOS CSVs with inline v125
  formulas (un-subsampled LO/LS, per-phase keep pos%6==phase ffill
  fillna0, mean over 6; own 0.20-cap-2 `vol_scale` with W.shift(2),
  trailing 360/min-120 on tranched weights; v114 opens for b_lo/b94,
  v103 opens for b103; union >= first v103 t; books 0.25/0.25/0.5) +
  sequential v110 engine (0.8 books + 0.6 carry, live [2021-09-24,
  2026-09-23), ungoverned, fee/slip per v92 SCEN, 0.00005 long funding,
  2*0.0004/1.2 carry cost, target 0.15). Hidden: whole-index s target
  0.15, Wt = 0.8*s*books, r_next = o[t+2]/o[t+1]-1, carry_exp = 0.6*s,
  `fill_strict` [T+2m,T+14m] T+15m fallback missing-T taker + v104 cost
  path, no band. Train-free replay reproduces the leader retrain path
  bit-exact (leader re-derives the same v125 books by retraining).
- v128: v114 panel rebuilt from raw with audited v113_v114 formulas
  (Bitstamp >= 2013-01-01 + Coinbase BTC, Coinbase ETH, spot prefix,
  UTC floor agg 4h>=3/1d>=20); train-row counts match the audit
  (45915/56865/67815/78795/89745), confirming a bit-exact panel. hv
  triple added per bar open_time (last halving <= t over the four listed
  UTC dates; hv_days = elapsed/1461d; sin/cos of 2*pi*hv_days); HGB v92
  h42 cutoff-408h / v94 h18/42/84 cutoff-576h over all 29 non-target
  columns. Phased v115 portfolios (unchanged v103 from audited CSV, own
  scales, 0.25/0.25/0.5, s 0.15 sequential ungoverned) reproduce the
  leader per-phase monthlies/DDs and yearly means. The without-features
  branch (audited CSVs + identical phase code) reproduces v126 and the
  leader's retrained reference bit-exact, confirming the leader baseline
  equals the audited books.

## C. Look-ahead audit

### `v127/v127_tranched_deploy.py` — no look-ahead found

- Panel/training (:30-42): reuses audited `v115.v114` extended build +
  `train_predict` per anchor (audited v92/v94 embargoes); test year never
  used for fit. `v125.phased(raw, 0..5)` (:44) is the mean over six
  past-only phase schedules. Pass (blind replay of the same books is
  bit-exact).
- Scales/books (:45-50): union `>= p103.t.min()`; `vol_target_scale`
  causal (W.shift(2), trailing window, cap 2); per-book opens (v114 panel
  for b_lo/b94, v103 panel for b103); books 0.25/0.25/0.5. Pass.
- Portfolio (:53-55): `v110.run/summarize` with p103 opens, target 0.15
  ungoverned, three v92 scenarios; forward return is execution accounting
  with the same 2-bar lag as v104/v110. Pass.
- Hidden (:57-73): whole-index s 0.15, Wt/carry_exp causal (shifted
  books/carry, trailing vol); `v104.fill_strict` + v104 cost path; 1m
  post-T data only affects fill cost at t, not the signal; hidden slice
  is reporting. No band (matches spec). Pass.

### `v128/v128_halving_cycle.py` — no look-ahead found

- `add_cycle` (:31-35): `last` = last halving with `<= t` via
  `searchsorted(..., side="right") - 1` over the four public UTC dates;
  hv_days/sin/cos are deterministic functions of bar time t and public
  calendar dates only. No price/volume/funding input, no future halving
  used for any in-panel bar (panel starts 2013-01-01, after the 2012
  halving; the -1 wrap case never triggers in range). Pass with note.
- Training/IC (`phase_mean` :38-51): `ext.v92.FEATS` rebuilt from panel
  columns including hv (all non-target cols); v92/v94 `train_predict`
  with audited embargoes; v103 (`fl`) trained once without hv and reused
  for both branches (unchanged v103 per spec). IC is OOS rank correlation
  per anchor year. Pass.
- Phasing/books (:43-50): `v125.phased(R, [ph])` single-phase keep
  pos%6==ph ffill (past-only), own causal vol scales, union
  `>= p103.t.min()`, books 0.25/0.25/0.5, `v110` target 0.15 ungoverned.
  Summary (:52-55) is pure reporting (phase mean monthly, max full-path
  DD, yearly means). Pass.
- No normalisation/threshold fitting on locked test; costs/funding per
  AGENTS.md. No look-ahead found in either script.

## D. Post-hoc corrections / protocol log

- No spec reinterpretation after opening `v127/`/`v128/`. Part A script
  and `replication.json` unchanged since the pre-open save.
- One blind choice confirmed post-open: hv `t` = bar open_time (panel
  `t`). Leader `add_cycle` uses `p["t"]`, the same panel `t` (open_time),
  and the same last-halving<=t rule — values match bit-exact (ICs and
  phases exact), so no alignment fix was needed.
- Key-name note: leader v127 hidden uses `orders`; blind stores
  `orders_hidden_year` (values equal, 9206). Leader v128 per-phase cells
  are `[monthly, dd]` pairs; blind stores the full phase summaries (means
  verified equal). No numeric impact.

## E. Manifest notes / verdict

- `v127/result_manifest.json`: track A, `rejected`, `live_approved:false`,
  audit pending ("awaiting OpenCode blind audit"). Tranched scenarios and
  hidden 30.17/9.98/0.85/9206 match blind.
- `v128/result_manifest.json`: track B, `rejected`, `live_approved:false`,
  audit pending. Cycle ICs, per-phase monthlies/DDs, summaries, and
  yearly means match blind in both branches.
- Blind replication is bit-exact on all v127 scenario yearlies, hidden
  execution, and all v128 ICs/per-phase cells/summaries/yearly-means with
  and without the cycle features. No look-ahead in tranching, halving
  features, phasing, scales, or engine/hidden paths. Audit complete;
  leader files untouched.
