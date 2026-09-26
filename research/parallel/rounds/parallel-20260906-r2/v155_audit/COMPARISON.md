# v155 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v155_audit/` +
`tests/test_v155_audit.py` only. Base: v154 replication
((A+B+D)/3: A = v144 books, B = v150 member WITH v142 xs/xr, D =
v144 builder with the five v111 Coinbase columns), rebuilt inline from
OPENCODE_V154_AUDIT.md because `v154_audit/replication.json` was not
yet saved. No leader files edited.

Blind protocol: `replication.json` (`replicate_v155.py`,
`tests/test_v155_audit.py` passing 4/4) was saved BEFORE any Part B
comparison. Protocol log, honestly: before the Part A save no file
inside `v155/` was opened (no read of `v155/v155_result.json` or
`v155/v155_ensemble_frontier.py`; workspace mapping listed the parent
`parallel-20260906-r2/` directory only, which revealed the `v155/`
name). Before the save we did read the base-engine files
`v144/v144_deploy_v3.py`, `v144/v144_result.json`, the own-base work
`v154_audit/replicate_v154.py`, and listed `v154/`/`v144/` directory
entries (filenames only, no `v154/v154_result.json` or
`v154/v154_ensemble_coinbase.py` contents). `v154/v154_result.json`,
`v154/v154_ensemble_coinbase.py`, `v151/v151_info_ensemble.py`, and
`v111/v111_coinbase_premium.py` were opened only AFTER the Part A save
for verification. Mitigation, verifiable in the artifacts:
`replicate_v155.py` imports no leader module (no
`spec_from_file_location`/`exec_module`, no `import v155/v154/v144/
v150/v111/v151`; enforced by
`test_no_leader_v155_imports_in_blind_script`), all formulas are
inline from the assignment text + audited replication code + raw data
+ carry + 1m intraday, and no Part A file was changed after the save.

Key maps: blind `v155.rows.{primary_t25_governed,t28_governed,
t30_governed}` (alias `v154_books.rows` identical) <->
leader `v155_result.json` `{t25_governed,primary_t28_governed,
t30_governed}`. Thresholds per assignment: return diff > 1pp, DD diff
> 0.5pp.

## A. Number comparison (blind vs leader) — bit-exact everywhere

| row (blind <-> leader) | blind monthly / fullDD | leader monthly / fullDD | Δ monthly | Δ DD |
|---|---|---|---|---|
| primary_t25_governed <-> t25_governed | 3.515 / 19.15 | 3.515 / 19.15 | 0 | 0.00pp |
| t28_governed <-> primary_t28_governed | 3.670 / 20.03 | 3.670 / 20.03 | 0 | 0.00pp |
| t30_governed <-> t30_governed | 3.771 / 20.81 | 3.771 / 20.81 | 0 | 0.00pp |

(Δ = leader − blind.) No 1pp / 0.5pp threshold exceeded anywhere.

Yearly nets/DDs/fills blind = leader in all 3 rows x 5 years (max abs
net diff 0.00pp, DD diff 0.00pp, fills diff 0):

- t25: 18.38/19.15/2117, 40.66/13.22/2190, 97.79/14.71/2190,
  54.30/12.77/2190, 56.34/11.49/2185.
- t28: 17.67/19.42/2116, 40.37/13.75/2190, 106.93/14.71/2190,
  54.72/13.11/2190, 64.40/11.49/2185.
- t30: 17.47/19.60/2116, 40.75/13.89/2190, 112.35/14.71/2190,
  55.92/13.32/2190, 68.33/11.49/2185.

Mean_g blind (4dp) vs leader (3dp): max abs diff 0.0005 (rounding
only, e.g. t25 2022 0.9738 vs 0.974, t28 2021 0.8272 vs 0.827);
all rows governed so no 1.0 row.

0.25 must equal the v154 primary row: blind t25 3.515/19.15 =
leader `v154/v154_result.json` `primary_t25_governed` 3.515/19.15
bit-exact, yearly bit-exact (18.38/19.15/2117, 40.66/13.22/2190,
97.79/14.71/2190, 54.30/12.77/2190, 56.34/11.49/2185). The v154
construction inside the blind script is therefore correct even though
`v154_audit/replication.json` was never saved separately.

Blind member legs at the same three targets (no leader counterpart
except via stated references):

- A (v144): t25 3.374/19.63, t28 3.534/19.87, t30 3.639/20.30 —
  t25 bit-exact vs the audited v144 values (ICs v92
  0.0662/-0.0539/0.1148/0.1029/0.1425 etc.; pvol spearmans match
  v129).
- B (opt WITH xs): t25 3.465/19.15, t28 3.631/19.45, t30
  3.720/19.67 — t25 matches the leader's stated v150 reference
  (3.465/19.15) exactly, confirming the with-xs reading.
- D (coinbase, v103+v114): t25 3.061/22.60, t28 3.215/24.63, t30
  3.304/25.54. The coinbase leg is the weakest member and carries
  the highest DD; averaging it in dilutes the ensemble.
- Ensemble t25 3.515 sits above all three members (3.374, 3.465,
  3.061) with DD 19.15 below D's 22.60 — same diversification
  pattern as v151/v153/v154, now with the frontier pushed out by
  higher vol targets.

Leader manifest fills 10871 / 60 months are consistent with blind
yearly fill sums (t28: 2116+2190+2190+2190+2185 = 10871; t25 sum
10872; t30 sum 10871). Blind `fills_live` (full live-window
turn>1e-6 count) is 10871/10870/10870, i.e. 1 below the yearly sums
— a window-definition difference (yearly windows cover 5x365d from
anchors; the live window ends 2026-09-23 exclusive), not a mismatch:
blind yearly sums equal leader yearly sums exactly.

## B. Why it matches — construction verified leg by leg

- A leg: blind return feats v114 44 (26+18) / v103 60 (36+24), xs
  on BASE / BASE+FLOWX only with per-t mean + `rank(pct=True)` over
  the 5 majors present at the same bar t (contemporaneous only).
  Blind A t25 3.374/19.63 = audited v144 = leader `books_v142()`
  output. Pass.
- B leg with-xs: blind return feats v114 49 (26+5+18) / v103 65
  (36+5+24), xs on BASE / BASE+FLOWX only, no `xs_opt_*`/`xr_opt_*`
  (asserted in-script and in tests). Blind B t25 3.465/19.15 =
  leader v150/v151 reference confirms the leader B = opt-merged
  panels through `books_v142()`, i.e. exactly the assignment's
  parenthetical. Pass.
- D leg: blind return feats v114 49 / v103 65, xs on BASE/BASE+FLOWX
  only, no `xs_cb_*`/`xr_cb_*` (asserted in-script and in tests),
  vol models on original 26/36 sets (asserted in-script). Coinbase
  coverage 0.986–1.0 per sym (BTC/ETH first-full 2017-10-01, BNB
  2017-11-06, XRP 2018-05-04, SOL 2020-09-14) matches the v111
  data start. Pass.
- Ensemble math: blind union index
  (10950 = 10950 ∩ 10950 ∩ 10950, `overlap_ABD` recorded) with
  missing→0 ≡ leader `:34-35` (`A.index.union(B.index).union(D.index)`,
  `reindex(...).fillna(0.0)`, `/3`). Vol recomputed from the ensemble
  books with the same rolling-360/min-120 formula; opens/carry shared
  (identical grids). Pass.
- Engine: sequential governor j=i-2, 540-bar peak,
  clip((0.20-DD)/0.10), per-target s cap 2, 10bps 1m rule (T=t+4h,
  strict through minutes 2..14, maker 0.0002 rel ∓0.0010 else taker
  0.0005) ≡ audited `books_v142()` + `simulate()`. The only v155
  change is `v144.ROWS` overridden to
  (0.25, 0.28, 0.30 all governed) — vol-target scalars only, governor
  unchanged 20%. Pass.

## C. Look-ahead audit

### `v155/v155_ensemble_frontier.py` — no look-ahead found

- Chain (`:28-30`): `_load` imports the audited `v144_deploy_v3`,
  `v151_info_ensemble` (which reuses the audited `v150_options_flow`
  math), and `v154_ensemble_coinbase` (which reuses the audited
  `v111_coinbase_premium` math) only; no data touched directly. Each
  `_load` creates a fresh module instance, so the `vol_predict` /
  `build` monkey-patches in `books_with_options()` (v151 `:36-40`)
  and in `books_coinbase()` (v154 `:36-40`) are isolated per
  instance — legs cannot contaminate each other. Pass.
- A leg (`:31`): audited `books_v142()` unchanged. Pass.
- B leg (v151 `:29-41` via `books_with_options()`): `opt_features()`
  is the audited v150 math (reindex to complete 4h grid + fill
  present/past-only; trailing rolling 6/180 windows;
  `merge(feats,on="t",how="left")` = bar T to panel row t=T, same
  timing as the row's own OHLCV; 2-bar execution lag downstream).
  Vol wrapper (v151 `:36`) drops exactly the 5 OPT cols before the
  audited `vol_predict` — embargoes, causal fv target, left-join
  replace unchanged. `books_v142()` then adds xs/xr on the merged
  panels with the audited groupby-t mean + `rank(pct=True)` over
  majors present at the same bar t (contemporaneous only). Pass.
- D leg (v154 `:29-41` via `books_coinbase()`): `v111.add_cb()` is
  the v111 docstring math (Binance spot 4h + Coinbase 1h close of
  the candle opening at T+3h, asof-backward tolerance 2h, else NaN;
  all features trailing p6/p42/m540/s540 — causal; one value per t
  merged on t into v114+v103). Vol wrapper (v154 `:36`) drops
  exactly the 5 CB cols before the audited `vol_predict`.
  `books_v142()` adds xs/xr on BASE/BASE+FLOWX only, so the coinbase
  columns get no xs/xr versions — matches the assignment's "merged
  on t ... BEFORE the v142 xs step (no xs versions of them; vol
  models exclude them)". Pass.
- Ensemble (`:34-35`): union index, `fillna(0.0)`, /3 average of
  three already-scaled causal book series at the same t —
  contemporaneous only, no future-t row enters. Missing→0 applies to
  no bars here (identical 10950 grids). Pass.
- Simulate (`:36-37`): audited `v144.simulate(p103, books)` with only
  `ROWS` overridden to the 0.25/0.28/0.30 governed frontier —
  trailing vol, per-target s cap 2, governor j=i-2, 10bps 1m fills,
  carry/funding per AGENTS.md. `p103` from the A leg shares the grid
  with B/D (merges add columns, not rows). Pass.
- Costs/funding per AGENTS.md; target choice ex post (frontier,
  primary t28) is the disclosed reporting frontier, unchanged
  governor. Docstring states "any target choice is ex post" upfront.
  Pass.

## D. Aggregation alignment

Covered by `v150_audit` §D (Deribit bar = `ts.floor(4h)`, trades in
[T,T+4h) → bar T; join on t is bar-close timing with 2-bar execution
lag) and the v111 docstring (Coinbase close of the 1h candle opening
at T+3h, asof-backward tol 2h; Binance spot 4h close at T). No new
data path in v155. One observation: blind opt grid is 16951 bars
(last 2026-09-26) vs 16944 at the v151 audit — the Deribit file
gained 7 bars since; the live window (ends 2026-09-23) and all
results are unaffected. Blind cb grid is 19942 bars
(2017-08-17 → 2026-09-25).

## E. Post-hoc corrections / protocol log

- No Part A file was modified after the save; tests pass 4/4 pre-
  and post-open. The blind script contains no leader-derived
  constants; the D leg (for which v155 publishes no separate member
  reference) reproduces the ensemble bit-exact together with A/B,
  which is only possible if the construction itself is right.
- Pre-save reads logged honestly at the top. No
  `v155_ensemble_frontier.py` / `v155_result.json` content entered
  Part A.
- Blind extras with no leader counterpart: full A/B/D legs at all
  three targets + ICs, pvol spearmans, `feats114B`/`feats103B`/
  `feats114D`/`feats103D` lists, maker rates (0.636 all rows),
  orders/fills, `overlap_ABD`, coinbase coverage/first-full, full
  `meta`. Leader extras: `t25` vs `primary_t25` naming (blind uses
  `primary_t25_governed` for the 0.25 row; mapping in §A), rounded
  `mean_g` (3dp vs blind 4dp).

## F. Manifest notes / verdict

- `v155/result_manifest.json`: track C, `rejected`,
  `live_approved:false`, audit pending. Single realistic 1m scenario
  repeated in 3 slots (3.67/20.03, fills 10871, 60 months); note
  matches the numbers (frontier 0.25 → 3.515/19.15, 0.28 →
  3.67/20.03, 0.30 → 3.771/20.81 — blind confirms every row/year/
  fill/DD bit-exact). Blind reproduces every row/year/fill/DD
  bit-exact.
- No look-ahead in the three legs, the opt/cb joins, the vol
  wrappers, xs timing, embargoes, tranching, scales, governor timing,
  or the 1m fill/cost paths. Primary-row (t28) DD 20.03 breaches the
  20% acceptance gate; t25 (19.15) does not, but no row clears the
  monthly>=5% gate on this engine — consistent with `rejected`.
  Audit complete; leader files untouched.

## Files

- `replication.json` (Part A, blind, frozen), `replicate_v155.py`,
  `tests/test_v155_audit.py` pass 4/4.
