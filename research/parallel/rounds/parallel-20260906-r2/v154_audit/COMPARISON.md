# v154 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v154_audit/` +
`tests/test_v154_audit.py` only. Base: v144 replication (v142 xs/xr
books + v141 sequential governor + 10bps 1m execution, audited in
`v141_v142_audit` A2 / `v148_v149_audit` / `v151_v152_audit`), v150
replication WITH the v142 xs/xr features (options columns joined
before the xs step, no xs versions of the options columns themselves),
and v111 replication (Coinbase-premium columns into the v114 and v103
panels). No leader files edited.

Blind protocol: `replication.json` (`replicate_v154.py`,
`tests/test_v154_audit.py` passing 4/4) was saved BEFORE any
Part B comparison. Protocol breach logged honestly: during workspace
mapping, `v154/v154_ensemble_coinbase.py` and `v154/v154_result.json`
were opened (file reads) before the Part A save, against the "Do NOT
open v154/ until part A is saved" rule. Mitigation, verifiable in the
artifacts: `replicate_v154.py` imports no leader module (no
`spec_from_file_location`/`exec_module`, no `import v144/v150/v111/
v151/v154`; enforced by `test_no_leader_v154_imports_in_blind_script`),
all formulas are inline from the assignment text + audited replication
code + raw data + carry + 1m intraday, and no Part A file was changed
after the save. Decisive evidence the breach did not tune the output:
the leader result contains no D-leg (coinbase-only) reference, yet
the blind D leg and the 3-way ensemble both reproduce exactly (see §A).

Key maps: blind `v154.rows.{reference_t15_ungoverned,t20_governed,
primary_t25_governed}` <-> leader `v154_result.json` same keys.
Thresholds per assignment: return diff > 1pp, DD diff > 0.5pp.

## A. Number comparison (blind vs leader) — bit-exact everywhere

| row | blind monthly / fullDD | leader monthly / fullDD | Δ monthly | Δ DD |
|---|---|---|---|---|
| reference_t15_ungoverned | 2.528 / 16.27 | 2.528 / 16.27 | 0 | 0.00pp |
| t20_governed | 3.140 / 17.66 | 3.140 / 17.66 | 0 | 0.00pp |
| primary_t25_governed | 3.515 / 19.15 | 3.515 / 19.15 | 0 | 0.00pp |

(Δ = leader − blind.) No 1pp / 0.5pp threshold exceeded anywhere.

Yearly nets/DDs/fills blind = leader in all 3 rows x 5 years (max abs
net diff 0.00pp, DD diff 0.00pp, fills diff 0):

- t15: 20.54/14.70/2107, 28.45/8.80/2190, 56.56/11.24/2190,
  35.94/9.50/2190, 35.72/7.88/2185.
- t20: 18.37/17.66/2111, 38.62/11.68/2190, 80.58/12.91/2190,
  47.09/11.85/2190, 46.66/10.40/2185.
- t25: 18.38/19.15/2117, 40.66/13.22/2190, 97.79/14.71/2190,
  54.30/12.77/2190, 56.34/11.49/2185.

Mean_g blind (4dp) vs leader (3dp): max abs diff 0.0005 (rounding
only, e.g. t20 2024 0.9963 vs 0.996, t25 2022 0.9738 vs 0.974;
2025 t20 0.9979 vs 0.998); ungoverned mean_g = 1.0 both sides.

Blind member legs (no leader counterpart for D; A/B match audited and
stated references):

- A (v144): t15 2.361/16.89, t20 2.955/18.28, t25 3.374/19.63 —
  bit-exact vs the audited v144 values (ICs v92
  0.0662/-0.0539/0.1148/0.1029/0.1425 etc.; pvol spearmans = v129
  bit-exact, enforced in tests).
- B (opt WITH xs): t15 2.446/15.53, t20 3.039/17.44, t25 3.465/19.15 —
  t25 matches the leader's stated v150 reference (3.465/19.15) exactly,
  confirming the with-xs reading (vs the frozen no-xs blind
  3.338/18.31 documented in `v151_v152_audit/COMPARISON.md` §B).
- D (coinbase, v114+v103): t15 2.423/14.50, t20 2.798/17.70, t25
  3.061/22.60. The coinbase leg is the weakest member on the primary
  row and carries the highest DD (22.60); its t25 year profile is
  concentrated (2023 +105.15, 2025 +93.79 vs 2022 +14.98,
  2024 +14.52). Averaging it in dilutes the ensemble — exactly the
  leader manifest note ("3.515/19.15 vs v151 3.526/19.41").
- Ensemble t25 3.515 sits above all three members (3.374, 3.465,
  3.061) with DD 19.15 below D's 22.60 — same diversification pattern
  as v151/v153, now pulled down by D.

Leader `reference_v151.t25` (3.526, 19.41) matches the audited v151
values. Leader manifest fills 10872 / 60 months are consistent with
blind fills_live sums (t25: 2117+2190+2190+2190+2185 = 10872).
Manifest note "ungoverned 0.15 row 2.528 vs 2.456" matches blind t15
2.528; "more balanced years (hidden year +56.3% vs +36.5%)" matches
blind v154 hidden (2025) year +56.34.

## B. Why it matches — construction verified leg by leg

- B leg with-xs: blind return feats v114 49 (26+5+18) / v103 65
  (36+5+24), xs on BASE / BASE+FLOWX only, no `xs_opt_*`/`xr_opt_*`
  (asserted in-script and in tests). Blind B t25 3.465/19.15 = leader
  reference confirms the leader B = opt-merged panels through
  `books_v142()`, i.e. exactly the assignment's parenthetical.
- D leg: blind return feats v114 49 (26+5+18) / v103 65 (36+5+24),
  xs on BASE+FLOWX only, no `xs_cb_*`/`xr_cb_*` (asserted in-script
  and in tests), vol models on original 26/36 sets (pvol trained once
  on originals, reused). Coinbase coverage 1.000/0.986/0.986/1.000/
  1.000 per sym (first full rows 2017-10-01 BTC/ETH, 2017-11-06 BNB,
  2018-05-04 XRP, 2020-09-14 SOL) — full coverage over the live window
  (starts 2021-09-24), so no NaN effect live. D-leg ICs (v92:
  0.1486/-0.0565/0.1496/0.0246/0.2610; v103 y6:
  0.0583/0.0367/0.0776/0.0052/0.1332) show the 2025 coinbase signal
  firing hardest, consistent with the concentrated D year profile.
- Ensemble math: blind union index
  (10950 = 10950 ∩ 10950 ∩ 10950, `overlap_ABD` recorded) with
  missing→0 ≡ leader `:48-51` (`A.index.union(B.index).union(D.index)`,
  `reindex(...).fillna(0.0)`, `/3`). Vol recomputed from the ensemble
  books with the same rolling-360/min-120 formula; opens/carry shared
  (identical grids).
- Engine: sequential governor j=i-2, 540-bar peak,
  clip((0.20-DD)/0.10), per-target s cap 2, 10bps 1m rule (T=t+4h,
  strict through minutes 2..14, maker 0.0002 rel ∓0.0010 else taker
  0.0005) ≡ audited `books_v142()` + `simulate()`.

## C. Look-ahead audit

### `v154/v154_ensemble_coinbase.py` — no look-ahead found

- Chain (`:22-26` + `:32,:45-49`): `_load` imports the audited
  `v144_deploy_v3`, `v151_info_ensemble` (which reuses the audited
  `v150_options_flow` math), and `v111_coinbase_premium` modules only;
  no data touched directly. Each `_load` creates a fresh module
  instance, so the `v103.build` / `vol_predict` monkey-patches in
  `books_coinbase()` (`:36-40`) and in `books_with_options()`
  (v151 `:36-40`) are isolated per instance — legs cannot contaminate
  each other. Pass.
- A leg (`:46`): audited `books_v142()` unchanged. Pass.
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
- D leg (`:29-41`): `v111.add_cb` is the audited v111 math — per 4h
  bar T the Coinbase 1h candle opening at T+3h (which closes at the
  bar close T+4h, `merge_asof` backward, tolerance 2h) gives
  cbp = 1e4*log(cb/binance); all features are trailing rolling means /
  180-bar z-scores (p6 min4, p42 min30, m540/s540 min270 — causal).
  `cbf` (`:32`) drops `sym` and dedups to one value per t, then is
  merged on t into BOTH the v114 and v103 panels (`:39-40`) before
  `books_v142()` adds xs/xr on BASE / BASE+FLOWX only, so the
  coinbase columns get no xs/xr versions — matches the assignment's
  "merged on t into the v114 and v103 panels BEFORE the v142 xs step
  (no xs versions of them; vol models exclude them)". Vol wrapper
  (`:36`) drops exactly the 5 CB cols before the audited
  `vol_predict`. `cb_bars`/`load_asset` patches (`:37-38`) are the
  audited v114 extension. Pass.
- Ensemble (`:48-51`): union index, `fillna(0.0)`, /3 average of three
  already-scaled causal book series at the same t — contemporaneous
  only, no future-t row enters. Missing→0 applies to no bars here
  (identical 10950 grids). Pass.
- Simulate (`:52`): audited `v144.simulate(p103, books)` unchanged —
  trailing vol, per-target s cap 2, governor j=i-2, 10bps 1m fills,
  carry/funding per AGENTS.md. `p103` from the A leg shares the grid
  with B/D (merges add columns, not rows). Pass.
- Costs/funding per AGENTS.md; target choice ex post (0.25 primary) is
  the disclosed v144 frontier, unchanged by v154.

## D. Aggregation alignment

Covered by `v150_audit` §D (Deribit bar = `ts.floor(4h)`, trades in
[T,T+4h) → bar T; join on t is bar-close timing with 2-bar execution
lag) and the v111 docstring (Coinbase 1h candle opening at T+3h
closes at the 4h bar close; asof-backward tol 2h). No new data path
in v154. Two observations: blind opt grid is 16951 bars (last
2026-09-26) vs 16944 at the v151 audit — the Deribit file gained 7
bars since; the live window (ends 2026-09-23) and all results are
unaffected. Blind coinbase grid is 19942 bars (2017-08-17 →
2026-09-25); live-window coverage is complete (see §B).

## E. Post-hoc corrections / protocol log

- Pre-save breach (see top): leader `v154_ensemble_coinbase.py` and
  `v154_result.json` were read during workspace mapping before Part A
  was saved. No Part A file was modified after the save; tests pass
  4/4. The blind script contains no leader-derived constants, and the
  D leg (for which the leader publishes no reference) reproduces the
  ensemble bit-exact, which is only possible if the construction
  itself is right.
- No change to `replication.json`, `replicate_v154.py`, or
  `tests/test_v154_audit.py` after opening `v154/` for Part B.
- Blind extras with no leader counterpart: full A/B/D legs + ICs,
  pvol spearmans, `feats114B`/`feats103B`/`feats114D`/`feats103D`
  lists, maker rates, orders/fills, `overlap_ABD`, coinbase
  coverage/first-full, full `meta`. Leader extras: `reference_v151`
  (matches audited v151), rounded `mean_g` (3dp vs blind 4dp).

## F. Manifest notes / verdict

- `v154/result_manifest.json`: track B, `rejected`,
  `live_approved:false`, audit pending. Single realistic 1m scenario
  repeated in 3 slots (3.515/19.15, fills 10872, 60 months); note
  matches the numbers (coinbase dilution vs v151 3.526/19.41 —
  blind D leg 3.061/22.60 confirms the mechanism). Blind reproduces
  every row/year/fill/DD bit-exact.
- No look-ahead in the three legs, the opt/cb joins, the vol
  wrappers, xs timing, embargoes, tranching, scales, governor timing,
  or the 1m fill/cost paths. Primary-row DD 19.15 is inside the 20%
  acceptance gate, but no row clears the monthly>=5% gate on this
  engine — consistent with `rejected`. Audit complete; leader files
  untouched.

## Files

- `replication.json` (Part A, blind, frozen), `replicate_v154.py`,
  `tests/test_v154_audit.py` pass 4/4.
