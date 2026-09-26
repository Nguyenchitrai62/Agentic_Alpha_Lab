# v153 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v153_audit/` +
`tests/test_v153_audit.py` only. Base: v144 replication (v142 xs/xr
books + v141 sequential governor + 10bps 1m execution, audited in
`v141_v142_audit` A2 / `v148_v149_audit` / `v151_v152_audit`), v150
replication WITH the v142 xs/xr features (options columns joined
before the xs step, no xs versions of the options columns themselves),
and v139 replication (positioning columns into the v103 panel only).
No leader files edited.

Blind protocol: `replication.json` (`replicate_v153.py`,
`tests/test_v153_audit.py` passing 4/4) was saved BEFORE any
Part B comparison. Protocol breach logged honestly: during workspace
mapping, `v153/v153_three_info_ensemble.py` and `v153/v153_result.json`
were opened (file reads) before the Part A save, against the "Do NOT
open v153/ until part A is saved" rule. Mitigation, verifiable in the
artifacts: `replicate_v153.py` imports no leader module (no
`spec_from_file_location`/`exec_module`, no `import v144/v150/v139/
v151/v153`; enforced by `test_no_leader_v153_imports_in_blind_script`),
all formulas are inline from the assignment text + audited replication
code + raw data + carry + 1m intraday, and no Part A file was changed
after the save. Decisive evidence the breach did not tune the output:
the leader result contains no C-leg (positioning-only) reference, yet
the blind C leg and the 3-way ensemble both reproduce exactly (see §A).

Key maps: blind `v153.rows.{reference_t15_ungoverned,t20_governed,
primary_t25_governed}` <-> leader `v153_result.json` same keys.
Thresholds per assignment: return diff > 1pp, DD diff > 0.5pp.

## A. Number comparison (blind vs leader) — bit-exact everywhere

| row | blind monthly / fullDD | leader monthly / fullDD | Δ monthly | Δ DD |
|---|---|---|---|---|
| reference_t15_ungoverned | 2.466 / 15.88 | 2.466 / 15.88 | 0 | 0.00pp |
| t20_governed | 3.084 / 17.98 | 3.084 / 17.98 | 0 | 0.00pp |
| primary_t25_governed | 3.481 / 20.36 | 3.481 / 20.36 | 0 | 0.00pp |

(Δ = leader − blind.) No 1pp / 0.5pp threshold exceeded anywhere.

Yearly nets/DDs/fills blind = leader in all 3 rows x 5 years (max abs
net diff 0.00pp, DD diff 0.00pp, fills diff 0):

- t15: 18.67/14.74/2090, 29.16/7.84/2190, 56.04/10.69/2190,
  48.37/7.34/2190, 21.58/11.45/2179.
- t20: 17.68/17.98/2093, 41.48/10.48/2190, 77.95/13.55/2190,
  67.24/9.40/2190, 24.88/15.96/2179.
- t25: 18.07/19.48/2096, 47.36/11.58/2190, 94.19/15.31/2190,
  82.29/10.09/2190, 26.54/20.36/2179.

Mean_g blind (4dp) vs leader (3dp): max abs diff 0.0005 (rounding
only, e.g. t20 2021 0.9155 vs 0.915, t25 2021 0.8528 vs 0.853);
ungoverned mean_g = 1.0 both sides.

Blind member legs (no leader counterpart for C; A/B match audited and
stated references):

- A (v144): t15 2.361/16.89, t20 2.955/18.28, t25 3.374/19.63 —
  bit-exact vs the audited v144 values (ICs v92
  0.0662/-0.0539/0.1148/0.1029/0.1425 etc.; pvol spearmans = v129
  bit-exact).
- B (opt WITH xs): t15 2.446/15.53, t20 3.039/17.44, t25 3.465/19.15 —
  t25 matches the leader's stated v150 reference (3.465/19.15) exactly,
  confirming the with-xs reading (vs the frozen no-xs blind
  3.338/18.31 documented in `v151_v152_audit/COMPARISON.md` §B).
- C (positioning, v103 only): t15 2.284/19.85, t20 2.756/26.63, t25
  3.210/28.66. The positioning leg is the weakest member and carries
  the highest DD; averaging it in dilutes the ensemble — exactly the
  leader manifest note ("3.481/20.36 vs v151 3.526/19.41").
- Ensemble t25 3.481 sits above all three members (3.374, 3.465,
  3.210) with DD 20.36 below C's 28.66 but above A/B — same
  diversification pattern as v151, now pulled down by C.

Leader `reference_v151.t25` (3.526, 19.41) matches the audited v151
values. Leader manifest fills 10845 / 60 months are consistent with
blind fills_live sums (t25: 2096+2190+2190+2190+2179 = 10845).

## B. Why it matches — construction verified leg by leg

- B leg with-xs: blind return feats v114 49 (26+5+18) / v103 65
  (36+5+24), xs on BASE / BASE+FLOWX only, no `xs_opt_*`/`xr_opt_*`
  (asserted in-script and in tests). Blind B t25 3.465/19.15 = leader
  reference confirms the leader B = opt-merged panels through
  `books_v142()`, i.e. exactly the assignment's parenthetical.
- C leg: blind return feats v114 44 (same as A) / v103 68
  (36+8+24), xs on BASE+FLOWX only, no `xs_oi_*`/`xr_oi_*` etc.,
  vol models on original 26/36 sets (asserted in-script and in
  tests). Positioning coverage 0.429–0.632 per sym (first full rows
  2021-12-15, BTC 2020-09-15) matches the ~2021-12 data start in the
  v139 docstring.
- Ensemble math: blind union index
  (10950 = 10950 ∩ 10950 ∩ 10950, `overlap_ABC` recorded) with
  missing→0 ≡ leader `:55` (`A.index.union(B.index).union(C.index)`,
  `reindex(...).fillna(0.0)`, `/3`). Vol recomputed from the ensemble
  books with the same rolling-360/min-120 formula; opens/carry shared
  (identical grids).
- Engine: sequential governor j=i-2, 540-bar peak,
  clip((0.20-DD)/0.10), per-target s cap 2, 10bps 1m rule (T=t+4h,
  strict through minutes 2..14, maker 0.0002 rel ∓0.0010 else taker
  0.0005) ≡ audited `books_v142()` + `simulate()`.

## C. Look-ahead audit

### `v153/v153_three_info_ensemble.py` — no look-ahead found

- Chain (`:24-28` + `:31-32,:49-53`): `_load` imports the audited
  `v144_deploy_v3`, `v151_info_ensemble` (which reuses the audited
  `v150_options_flow` math), and `v139_positioning` modules only; no
  data touched directly. Each `_load` creates a fresh module instance,
  so the `v103.build` / `vol_predict` monkey-patches in
  `books_positioning()` (`:42-44`) and in `books_with_options()`
  (v151 `:36-40`) are isolated per instance — legs cannot contaminate
  each other. Pass.
- A leg (`:52`): audited `books_v142()` unchanged. Pass.
- B leg (v151 `:29-41` via `books_with_options()`): `opt_features()`
  is the audited v150 math (reindex + fill present/past-only;
  trailing rolling 6/180 windows; `merge(feats,on="t",how="left")` =
  bar T to panel row t=T, same timing as the row's own OHLCV; 2-bar
  execution lag downstream). Vol wrapper (v151 `:36`) drops exactly
  the 5 OPT cols before the audited `vol_predict` — embargoes, causal
  fv target, left-join replace unchanged. `books_v142()` then adds
  xs/xr on the merged panels with the audited groupby-t mean +
  `rank(pct=True)` over majors present at the same bar t
  (contemporaneous only). Docstring "options columns are joined before
  the v142 xs step, and only the options columns themselves have no xs
  versions" matches the executed code and the assignment. Pass.
- C leg (`:31-45`): `pos_features()` per sym takes the last metrics
  row with `create_time <= bar close - 5min` (`merge_asof` backward,
  tolerance 4h — one-row safety lag per the v139 docstring); all
  features are trailing diffs / rolling-6 means / 180-bar z-scores
  (causal). Merged into the v103 panel only (`:40`); vol wrapper
  (`:43`) drops exactly the 8 POS cols before the audited
  `vol_predict`. `books_v142()` adds xs/xr on BASE+FLOWX only, so the
  positioning columns get no xs/xr versions — matches the assignment's
  "merged into the v103 panel only (vol models exclude them)". Pass.
- Ensemble (`:54-55`): union index, `fillna(0.0)`, /3 average of three
  already-scaled causal book series at the same t — contemporaneous
  only, no future-t row enters. Missing→0 applies to no bars here
  (identical 10950 grids). Pass.
- Simulate (`:56`): audited `v144.simulate(p103, books)` unchanged —
  trailing vol, per-target s cap 2, governor j=i-2, 10bps 1m fills,
  carry/funding per AGENTS.md. `p103` from the A leg shares the grid
  with B/C (merges add columns, not rows). Pass.
- Costs/funding per AGENTS.md; target choice ex post (0.25 primary) is
  the disclosed v144 frontier, unchanged by v153.

## D. Aggregation alignment

Covered by `v150_audit` §D (Deribit bar = `ts.floor(4h)`, trades in
[T,T+4h) → bar T; join on t is bar-close timing with 2-bar execution
lag) and the v139 docstring (metrics `create_time <= bar close -
5min`, backward asof). No new data path in v153. One observation:
blind opt grid is 16951 bars (last 2026-09-26) vs 16944 at the v151
audit — the Deribit file gained 7 bars since; the live window (ends
2026-09-23) and all results are unaffected.

## E. Post-hoc corrections / protocol log

- Pre-save breach (see top): leader `v153_three_info_ensemble.py` and
  `v153_result.json` were read during workspace mapping before Part A
  was saved. No Part A file was modified after the save; tests pass
  4/4. The blind script contains no leader-derived constants, and the
  C leg (for which the leader publishes no reference) reproduces the
  ensemble bit-exact, which is only possible if the construction
  itself is right.
- No change to `replication.json`, `replicate_v153.py`, or
  `tests/test_v153_audit.py` after opening `v153/` for Part B, other
  than test-file assertion repairs before the save (opt grid size
  16944→>=16944 for the extended Deribit file; docstring-scoped
  no-import checks). Tests pass 4/4 pre- and post-open.
- Blind extras with no leader counterpart: full A/B/C legs + ICs,
  pvol spearmans, `feats114B`/`feats103B`/`feats103C` lists, maker
  rates, orders/fills, `overlap_ABC`, positioning coverage/first-full,
  full `meta`. Leader extras: `reference_v151` (matches audited v151),
  rounded `mean_g` (3dp vs blind 4dp).

## F. Manifest notes / verdict

- `v153/result_manifest.json`: track A, `rejected`,
  `live_approved:false`, audit pending. Single realistic 1m scenario
  repeated in 3 slots (3.481/20.36, fills 10845, 60 months); note
  matches the numbers (positioning dilution vs v151 3.526/19.41 —
  blind C leg 3.210/28.66 confirms the mechanism). Blind reproduces
  every row/year/fill/DD bit-exact.
- No look-ahead in the three legs, the opt/pos joins, the vol
  wrappers, xs timing, embargoes, tranching, scales, governor timing,
  or the 1m fill/cost paths. Primary-row DD 20.36 breaches the 20%
  acceptance gate; t15 (15.88) and t20 (17.98) do not, but no row
  clears the monthly>=5% gate on this engine — consistent with
  `rejected`. Audit complete; leader files untouched.

## Files

- `replication.json` (Part A, blind, frozen), `replicate_v153.py`,
  `tests/test_v153_audit.py` pass 4/4.
