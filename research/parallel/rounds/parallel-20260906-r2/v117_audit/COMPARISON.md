# v117 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v117_audit/` +
`tests/test_v117_audit.py` only. Base: audited v115 replication
(target 0.15 ungoverned v110 engine). No leader files edited.

## A. Number comparison (blind `replication.json` vs leader `v117/v117_result.json`)

- Keys: blind `k12_primary_t15`/`k42_primary_t15`/`k6_reference_primary_t15`
  <-> leader `primary_k12`/`secondary_k42`/`reference_k6_v115`.
  3 k-values x 3 scenarios x 5 years = 45 yearly cells + 9 full-path DDs:
  max abs yearly net diff 0.00pp, max abs yearly DD diff 0.00pp,
  max abs fills/sharpe/monthly diff 0. No 1pp return / 0.5pp DD threshold exceeded.
- Headlines blind = leader:
  k12 normal monthly 2.374 / worst-year DD 17.06 / full-path DD 20.62;
  fee 2.182/18.01/21.96; exec 1.942/19.45/23.80.
  k42 normal 2.042/21.48/22.64; fee 1.868/22.12/23.83; exec 1.650/22.90/25.28.
  k6 reference normal 2.608/16.78/16.78; fee 2.388/17.31/17.31; exec 2.114/17.96/19.13.
- Yearly blind = leader, normal scenario:
  k12 nets 14.04/6.38/60.66/46.61/43.05; DDs 15.05/17.06/6.93/9.57/8.06;
  fills 1854/2181/2181/2176/2122; mean_g 1.0.
  k42 nets 15.58/1.81/43.54/47.50/35.01; DDs 13.79/21.48/8.15/10.62/8.00;
  fills 1921/2183/2183/2182/2153; mean_g 1.0.
  k6 nets 13.91/16.73/63.52/51.22/42.55 (= v115 primary); DDs 16.78/12.69/7.44/10.60/9.01;
  fills 1831/2180/2180/2177/2115; mean_g 1.0.
- Fee/exec-stress yearly cells also bit-exact (see `run.log` lines 1-9 vs replication).
- `v117/result_manifest.json` (track A, `rejected`, `live_approved:false`,
  "awaiting OpenCode blind audit") primary monthly 2.374 / fills 10514 / 60 months
  and yearly normal 14.04/6.38/60.66/46.61/43.05 match blind k12.

## B. Why blind matched

- Books: blind recomputes LO/LS weights + 20%-cap-2 scales from audited OOS CSVs
  with inline audited formulas, with `arange(len(W)) % k == 0` + ffill for
  v92 LO / v94 LS (k = 12/42/6) and k = 6 for v103; leader parameterises the same
  `weights_from`/`weights_ls` rebalance step as `lo_weights(df, k)`/`ls_weights(df, k)`
  and asserts k=6 equals the audited `v92.weights_from`/`v94.weights_ls` (:81-82).
  Vol scales computed on the k-rebalanced W (`W.shift(2)`, trailing 360/min-120,
  cap 2, NaN->1) in both; portfolio s (0.15) from combined k-books with the
  v99/v104 convention. Bit-exact match confirms identical phase alignment
  (position 0 = first OOS bar) and scale timing.
- Engine: blind sequential loop mirrors `v110.run/summarize` ungoverned
  (0.8 books + 0.6 carry, live [2021-09-24,2026-09-23), fee/slip per v92 SCEN,
  0.00005 long funding, 2*0.0004/1.2 carry cost). No hidden-year path per spec.

## C. Look-ahead audit (`v117/v117_slow_rebalance.py`)

- `lo_weights` (:39-50) / `ls_weights` (:53-64): signal from contemporaneous
  pred/vol42/rib only, gross + active-asset normalisation, then keep every k-th
  positional row + ffill. Forward-fill propagates only kept past/current rows.
  No future peek; annualisation constant cancels in normalisation. Pass.
- Training (:68-80): same v114 extended-panel `build` + per-anchor `train_predict`
  with v92/v94/v103 embargoes as audited v115; junction history only adds
  pre-2021 training rows. `W103` reuses audited daily `weights_ls`. Pass.
- Scales (:88-90): `vol_target_scale` on k-rebalanced W (trailing, shift-2);
  reindex to union `idx >= p103.t.min()` as in v115. Blind OOS-open recomputation
  matches panel-open computation bit-exactly on the OOS index. Pass.
- Engine (:94): `v110.run(p103, books, 0.15, False, fee, slip)` + `summarize`,
  ungoverned primary settings; governor timing untouched. Pass (see v110 audit).
- No normalisation/threshold fitting on locked test; costs/funding per AGENTS.md.

## D. Post-hoc corrections / protocol log

- Protocol note (disclosed): a repo-wide grep before Part A was saved surfaced the
  filename plus the usage-string line of `v117_slow_rebalance.py` (:9). No result
  numbers, weight logic, or scale/engine code were read before `replication.json`
  was saved; Part A imports no v117/v115/v114/v103/v110 leader module (all formulas
  inline from the assignment text + audited OOS CSVs). No spec reinterpretation
  after opening v117/.
- Two test fixes after Part A save (no `replication.json` edits): replaced two
  false monotone assumptions (fills and combined-book diff counts need not decrease
  with slower rebalance because per-book vol scales and portfolio s move every bar)
  with difference/range checks; k6-reference bit-exactness vs v115 unchanged.

## E. Manifest notes / verdict

- Blind replication is bit-exact on all yearly nets, DDs, sharpes, fills, mean_g,
  headlines, and full-path DDs across k = 12/42/6 and all three scenarios.
  Reference k=6 reproduces v115 primary exactly.
- No look-ahead found in k-rebalance step, scale timing, union restriction,
  or engine. Effect: slower v92/v94 books lower return vs k=6 in normal
  (k12 2.374, k42 2.042 vs 2.608 monthly) and raise full-path DD
  (20.62 / 22.64 vs 16.78). Audit complete; leader files untouched.
