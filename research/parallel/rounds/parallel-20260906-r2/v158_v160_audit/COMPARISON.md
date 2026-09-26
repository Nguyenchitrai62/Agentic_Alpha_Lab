# v158 + v159 + v160 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v158_v160_audit/` +
`tests/test_v158_v160_audit.py` only. Base: v154 replication (members A, B, D
from `v154_audit`, rebuilt inline here from the assignment text + audited
replication code). No leader files edited.

Blind protocol: `replication.json` (`replicate_v158_v160.py`,
`tests/test_v158_v160_audit.py` passing 4/4) was saved BEFORE any Part B
comparison. Pre-save reads were limited to the allowed base (`AGENTS.md`,
`OPENCODE_VF_COMMON.md`, `OPENCODE_V158_V160_AUDIT.md`, skill,
`v154_audit/replicate_v154.py` + `replication.json` + `COMPARISON.md`,
`v150_audit/replicate_v150.py`, `v129_v131_audit` pvol rows, raw 4h/1d/funding/
spot/Coinbase/Bitstamp panels, carry, 1m intraday, Deribit BTC+ETH options
parquets, FNG daily + manifest, COT TFF + manifest; directory listing showed
`v158/`/`v159/`/`v160/` names only, no file contents). `v158/`
(`v158_eth_options_member.py`, `v158_result.json`, manifest),
`v159/` (`v159_ensemble_fng.py`, `v159_result.json`, manifest), and `v160/`
(`v160_ensemble_cot.py`, `v160_result.json`, manifest) were first opened after
the Part A save. Part A imports no
v158/v159/v160/v154/v151/v150/v144/v142/v141/v111 leader module. One
post-save, pre-comparison test-only fix is logged in §E (assertion wording in
`test_no_leader_v158_imports_in_blind_script`; `replication.json` and
`replicate_v158_v160.py` untouched after the save). No breach to log.

Key maps: blind `v158.rows.{reference_t15_ungoverned,t20_governed,
primary_t25_governed}` <-> leader `v158_result.json` same keys; blind
`v159.rows.*` <-> leader `v159_result.json` same keys; blind `v160.rows.*`
<-> leader `v160_result.json` same keys. Thresholds per assignment: return
diff > 1pp, DD diff > 0.5pp.

## A. Number comparison (blind vs leader) — bit-exact everywhere

| row (v158) | blind monthly / fullDD | leader monthly / fullDD | Δ monthly | Δ DD |
|---|---|---|---|---|
| reference_t15_ungoverned | 2.496 / 16.81 | 2.496 / 16.81 | 0 | 0.00pp |
| t20_governed | 3.079 / 17.60 | 3.079 / 17.60 | 0 | 0.00pp |
| primary_t25_governed | 3.437 / 19.00 | 3.437 / 19.00 | 0 | 0.00pp |

| row (v159) | blind monthly / fullDD | leader monthly / fullDD | Δ monthly | Δ DD |
|---|---|---|---|---|
| reference_t15_ungoverned | 2.417 / 16.11 | 2.417 / 16.11 | 0 | 0.00pp |
| t20_governed | 2.986 / 17.68 | 2.986 / 17.68 | 0 | 0.00pp |
| primary_t25_governed | 3.336 / 18.75 | 3.336 / 18.75 | 0 | 0.00pp |

| row (v160) | blind monthly / fullDD | leader monthly / fullDD | Δ monthly | Δ DD |
|---|---|---|---|---|
| reference_t15_ungoverned | 2.075 / 14.20 | 2.075 / 14.20 | 0 | 0.00pp |
| t20_governed | 2.456 / 17.76 | 2.456 / 17.76 | 0 | 0.00pp |
| primary_t25_governed | 2.681 / 19.13 | 2.681 / 19.13 | 0 | 0.00pp |

(Δ = leader − blind.) No 1pp / 0.5pp threshold exceeded anywhere.

Yearly nets/DDs/fills blind = leader in all 9 rows x 5 years (max abs net
diff 0.00pp, DD diff 0.00pp, fills diff 0):

- v158 t15: 21.67/14.76/2092, 26.95/8.72/2190, 57.36/11.53/2190,
  33.87/9.78/2190, 34.91/7.91/2185.
- v158 t20: 19.22/17.60/2095, 36.47/11.58/2190, 82.84/12.48/2190,
  42.39/12.79/2190, 45.63/10.44/2185.
- v158 t25: 19.20/19.00/2099, 37.41/13.17/2190, 100.18/14.44/2190,
  50.07/13.54/2190, 54.33/11.55/2185.
- v159 t15: 18.78/14.11/2120, 27.03/8.79/2190, 54.40/10.42/2190,
  35.32/8.59/2190, 32.92/7.72/2185.
- v159 t20: 17.00/17.68/2120, 35.91/11.68/2190, 74.36/13.26/2190,
  47.38/10.89/2190, 43.00/10.20/2185.
- v159 t25: 17.51/18.75/2124, 35.83/13.15/2190, 92.12/14.45/2190,
  54.17/12.09/2190, 51.48/10.77/2185.
- v160 t15: 8.09/14.20/2136, 32.44/8.68/2190, 53.52/10.44/2190,
  23.19/11.14/2190, 26.67/10.13/2185.
- v160 t20: 5.00/17.76/2139, 39.53/11.53/2190, 69.41/13.33/2190,
  29.78/13.33/2190, 33.11/12.64/2185.
- v160 t25: 4.03/19.13/2139, 39.78/12.48/2190, 77.18/14.93/2190,
  33.02/13.87/2190, 42.75/12.64/2185.

Mean_g blind (4dp) vs leader (3dp): max abs diff 0.0005 (rounding only, e.g.
v158 t20 2022 0.9980 vs 0.998, v160 t25 2022 0.9850 vs 0.985); ungoverned
mean_g = 1.0 both sides.

Blind member legs (no leader counterpart published for Bp/G/H):

- A (v144): t15 2.361/16.89, t20 2.955/18.28, t25 3.374/19.63 —
  bit-exact vs the frozen `v154_audit` values.
- B (BTC opt WITH xs): t15 2.446/15.53, t20 3.039/17.44, t25 3.465/19.15 —
  bit-exact vs frozen `v154_audit` B.
- D (coinbase): t15 2.423/14.50, t20 2.798/17.70, t25 3.061/22.60 —
  bit-exact vs frozen `v154_audit` D.
- Bp (BTC+ETH opt): t15 2.322/17.25, t20 2.808/17.17, t25 3.120/18.74.
  Weaker than BTC-only B on every row (t25 3.120 vs 3.465). v92 ICs
  0.0827/-0.0340/0.1298/0.1005/0.1131 (vs B
  0.0877/-0.0182/0.1200/0.1169/0.1113). Averaging Bp in gives v158 t25
  3.437, below v154 (3.515) — the leader manifest note
  ("3.437/19.0 vs v154 3.515/19.15").
- G (FNG): t15 1.745/15.77, t20 2.055/21.60, t25 2.319/25.66. The FNG leg
  is weak with the worst t25 DD of the set (25.66); v92 ICs
  0.0253/-0.0629/0.0769/0.1007/0.0289. v159 t25 3.336 sits above G but
  below A/B/D — dilution, matching the manifest note ("3.336/18.75 vs
  v154 3.515/19.15 (return/DD slightly worse)").
- H (COT): t15 -0.405/38.14, t20 -0.371/25.50, t25 -0.371/26.77. The COT
  leg never trades profitably: t25 yearly fills collapse
  (1968/2178/2065/1794/86; 2025 has 86 fills and -0.00% net), v92 ICs
  -0.0680/-0.0149/0.0638/0.0226/0.1801. v160 t25 2.681 is far below
  A/B/D with DD 19.13 — the manifest note ("COT member hurts:
  2.681/19.13 vs v154 3.515/19.15 (2021 +4%)"; blind 2021 t25 year is
  +4.03).

Leader `reference_v154.t25` (3.515, 19.15) in all three result JSONs matches
the audited v154 values. Leader manifest fills equal the blind yearly-fill
sums (v158 t25: 2099+2190+2190+2190+2185 = 10854; v159 t25:
2124+2190+2190+2190+2185 = 10879; v160 t25: 2139+2190+2190+2190+2185 =
10894).

## B. Why it matches — construction verified leg by leg

- A/B/D legs: blind A/B/D monthlies, fullDDs, and ICs are bit-exact vs the
  frozen `v154_audit/replication.json` values (asserted in-script and in
  tests), so the shared 3/4 of each ensemble is exact by inheritance.
- Bp leg ETH: blind ETH math is the identical five-feature computation run
  on `ETH_options_4h.parquet` (reindex to complete 4h grid first→last,
  flows→0, IVs NaN, net/tot/rolling6 min6, pcr log clip 1, skew, z
  roll180 min90 ddof1, skew6 roll6 min3), columns renamed `eth_opt_*`,
  outer-joined with the BTC five on t (union grid 16952 bars,
  2019-01-01 → 2026-09-26 04:00; NaN counts BTC 5/89/2/89/89, ETH
  490/574/499/708/574 — the ETH lead-in before 2019-03-21 plus IV gaps).
  One row per t merged on t into v114+v103 BEFORE xs; xs on
  BASE/BASE+FLOWX only, no `xs_opt_*`/`xr_opt_*`/`xs_eth_*`/`xr_eth_*`;
  return feats 54/70; vol on original 26/36. ≡ leader
  `v158_eth_options_member.py` `:33-39` (same `opt_features` code object
  with the filename replaced, same rename, same `merge(how="outer")`) and
  `:44-48` (same vol-wrapper exclusion of all 10 cols, same left merges
  before `books_v142()`). Bit-exact ensemble output confirms the reading,
  including the outer (not inner) join.
- G leg FNG: blind daily math (fng; fng7 = rolling-7 mean min7; chg7 =
  fng − shift(7); z = (fng − rolling90 mean min60)/rolling90 std min60
  ddof1, pandas default; avail = date + 1h per the manifest; asof = last
  avail ≤ t+4h via merge_asof backward; merged on t BEFORE xs; xs on
  BASE/BASE+FLOWX only, no `xs_fng*`; return feats 48/64; vol original)
  ≡ leader `v159_ensemble_fng.py` `:33-43` (same `rolling(7).mean()`
  default min7, same `rolling(90, min_periods=60)` mean/std default
  ddof1, same `avail = date + 1h`, same `merge_asof(close_at=t+4h, avail,
  backward)`). FNG daily grid 3156 rows (2018-02-01 → 2026-09-26); asof
  grid 30070 rows over the panel union; live full-row coverage is complete
  (history from 2018, live from 2021-09-24). Leader builds feats over
  v114-only times, blind over the v114∪v103 union — equivalent live
  (v103 times ⊆ v114 live grid; opens/carry shared), confirmed bit-exact.
- H leg COT: blind weekly math (dedup report dates keep-last, sorted;
  OI = Open_Interest_All float with 0→NaN guard; lev = (Lev long−short)/OI,
  am = (Mgr long−short)/OI; chg4 = x − shift(4); z = (x − rolling52 mean
  min26)/rolling52 std min26 ddof1; avail = report date + 4 days per the
  assignment/manifest Saturday rule; asof = last avail ≤ t+4h backward;
  merged on t BEFORE xs; xs on BASE/BASE+FLOWX only, no `xs_cot_*`;
  return feats 50/66; vol original) ≡ leader `v160_ensemble_cot.py`
  `:34-47` (same columns, same shift(4), same `rolling(52,
  min_periods=26)` default ddof1, same `avail = date + 4 days`, same
  `merge_asof(close_at=t+4h, avail, backward)`). Dedup keep-first vs
  keep-last is a no-op (442 rows, 442 unique report dates); the OI 0→NaN
  guard is a no-op (OI never 0). Weekly grid 442 rows (2018-04-10 →
  2026-09-22); asof 30070 rows; live coverage complete. Bit-exact output
  confirms equivalence.
- Ensemble math: blind union index with missing→0, /3 (v158) and /4
  (v159/v160) averages of already-scaled causal book series at the same t
  ≡ leaders (`:58-59` / `:68-69` / `:72-73`: `union`,
  `reindex(...).fillna(0.0)`, `/3` or `/4`). Missing→0 applies to no bars
  here (all member grids 10950). Vol recomputed from each ensemble's books
  with the same rolling-360/min-120 formula; opens/carry shared.
- Engine: sequential governor j=i-2, 540-bar peak, clip((0.20−DD)/0.10),
  per-target s cap 2, 10bps 1m rule (T=t+4h, strict through minutes 2..14,
  maker 0.0002 rel ∓0.0010 else taker 0.0005) ≡ audited `books_v142()` +
  `simulate()`. The vol wrappers drop exactly the 10/4/6 extra cols before
  the audited `vol_predict` — embargoes, causal fv target, left-join
  replace unchanged.

## C. Look-ahead audit

### `v158/v158_eth_options_member.py` — no look-ahead found

- Chain (`:23-27` + `:31-32`): loads the audited `v150_options_flow`
  (which carries the audited `v144_deploy_v3`) only; no data touched
  directly. The `exec` (`:35-37`) reuses the audited `opt_features` source
  with only the filename swapped — the ETH math is therefore the audited
  v150 math by construction. Pass.
- Bp leg (`:33-48`): `opt_features()` is the audited v150 math (reindex +
  fill present/past-only; trailing rolling 6/180 windows; `merge(feats,
  on="t", how="left")` = bar T to panel row t=T, same timing as the row's
  own OHLCV; 2-bar execution lag downstream). The ETH copy inherits all of
  this; the `outer` join (`:39`) is contemporaneous (union of two causal
  series at the same t, no future-t row enters). Vol wrapper (`:44`) drops
  exactly the 10 OPT/ETH cols before the audited `vol_predict`.
  `books_v142()` then adds xs/xr on the merged panels with the audited
  groupby-t mean + `rank(pct=True)` over majors present at the same bar t
  (contemporaneous only). Docstring "merged on t before the v142 xs step
  (no xs versions; vol models exclude them)" matches the executed code and
  the assignment (BTC five + same five ETH prefixed `eth_`, outer join on
  t). Pass.
- Ensemble (`:58-59`): union index, `fillna(0.0)`, /3 average of three
  already-scaled causal book series at the same t — contemporaneous only.
  Pass.
- Simulate (`:60`): audited `v144.simulate(p103, books)` unchanged —
  trailing vol, per-target s cap 2, governor j=i-2, 10bps 1m fills,
  carry/funding per AGENTS.md. Pass.
- Costs/funding per AGENTS.md; target choice ex post (0.25 primary) is the
  disclosed v144 frontier, unchanged by v158.

### `v159/v159_ensemble_fng.py` — no look-ahead found

- Chain (`:26-30` + `:61-66`): imports the audited `v144_deploy_v3`,
  `v151_info_ensemble` (audited v150-options path), and
  `v154_ensemble_coinbase` (audited) modules only; no data touched
  directly. Pass.
- G leg (`:33-57`): daily FNG indicators are strictly trailing rollings on
  the daily series (rolling-7/90, shift(7) — causal); availability is
  `avail = date + 1h` per the manifest (`:35`), and the join is
  `merge_asof(close_at=t+4h, avail, backward)` (`:42`), so a panel row t
  sees only dailies available by its bar close (t+4h is 1ms after
  close_time = t+4h−1ms). Matches the assignment's "value for date D
  available at D + 1h; for panel row t use the last value available at
  t + 4h". Merge is on t into both builds before `books_v142()` adds xs
  on the fixed BASE/BASE+FLOWX lists (no xs of FNG cols); the vol wrapper
  (`:54`) drops exactly the 4 FNG cols. `cb_bars`/`load_asset` patches
  (`:49-50`) are the audited v114 extension. Pass.
- Ensemble (`:68-69`) and simulate (`:70`): same contemporaneous-only
  averaging and audited engine as v158. Pass.
- Costs/funding per AGENTS.md; target choice ex post (0.25 primary) is the
  disclosed v144 frontier, unchanged by v159.

### `v160/v160_ensemble_cot.py` — no look-ahead found

- Chain (`:27-31` + `:65-71`): imports the audited `v144_deploy_v3`,
  `v151_info_ensemble`, and `v154_ensemble_coinbase` modules only; no data
  touched directly. Pass.
- H leg (`:34-61`): weekly COT ratios use the report's own OI/positions at
  the same report date (contemporaneous); chg4/z are strictly trailing
  shift/rollings on the weekly series (causal); availability is
  `avail = report date + 4 days` (`:43`) per the assignment/manifest
  Saturday rule, and the join is `merge_asof(close_at=t+4h, avail,
  backward)` (`:46`), so a panel row t sees only reports usable by its bar
  close. Matches the assignment's "report date D usable from D + 4 days".
  Merge is on t into both builds before the fixed-list xs step (no xs of
  COT cols); the vol wrapper (`:58`) drops exactly the 6 COT cols.
  `cb_bars`/`load_asset` patches (`:53-54`) are the audited v114
  extension. Pass.
- Ensemble (`:72-73`) and simulate (`:74`): same contemporaneous-only
  averaging and audited engine. Pass.
- Costs/funding per AGENTS.md; target choice ex post (0.25 primary) is the
  disclosed v144 frontier, unchanged by v160.

## D. Aggregation alignment

Covered by `v154_audit` §D (Deribit bar = `ts.floor(4h)`, trades in
[T,T+4h) → bar T; join on t is bar-close timing with 2-bar execution lag;
Coinbase 1h candle opening at T+3h closes at the 4h bar close) with three
new paths, all verified above: ETH options reuse the audited BTC bar
definition (same `opt_features` code, filename swapped; outer join on t
preserves bar-close timing); FNG UTC date D available at D+1h, joined
backward to bar-close time t+4h with 2-bar lag downstream; COT Tuesday
report D usable from Saturday D+4d 00:00 UTC, joined backward to t+4h with
the same 2-bar lag. No new data path beyond these asof joins. Two
observations: blind BTC opt grid is 16952 bars (last 2026-09-26 04:00) vs
16951 at the v154 audit — the Deribit file gained 1 bar since; the live
window (ends 2026-09-23) and all results are unaffected. Blind ETH opt grid
is 16467 bars (2019-03-21 → 2026-09-24); the outer join covers the full live
window. FNG/COT asof NaN counts (FNG ~11k, COT ~11-12k of 30070) are all
pre-history panel rows (panels start 2013/2017, FNG from 2018-02, COT from
2018-04); live-window coverage is complete.

## E. Post-hoc corrections / protocol log

- No breach: no `v158/`, `v159/`, or `v160/` file was opened before the Part
  A save (`replication.json` + 4/4 tests). No change to `replication.json`
  or `replicate_v158_v160.py` after opening `v158/`/`v159/`/`v160/` for
  Part B.
- One test-only fix logged here (before Part B, after the save): the first
  pytest run passed 3/4 with `test_no_leader_v158_imports_in_blind_script`
  failing on the literal `"/ 4"` assertion — the blind script factors the
  /3 and /4 ensemble divisions through the shared `ensemble_ctx(ctxs,
  divisor)` helper (`acc / divisor` + `, 3)`/`, 4)` call sites) instead of
  inline `/ 3`/`/ 4` literals. Fixed the test wording to assert
  `ensemble_ctx` + `, 3)`/`, 4)`; reran 4/4. No replication code or numbers
  changed.
- Implicit-spec gambles logged here (all resolved bit-exact): FNG
  `fng7` min_periods (assignment silent — blind fixed 7 before running;
  leader `:37` uses the `rolling(7)` default = 7); FNG/COT rolling-std ddof
  (silent — blind fixed pandas-default ddof=1; leaders use the same
  default); COT dedup keep-last vs keep-first (no-op: 442 rows, 442 unique
  dates); COT OI 0→NaN guard (no-op: OI never 0); FNG/COT feat grids over
  the v114∪v103 union vs leader v114-only times (equivalent over live).
- Blind extras with no leader counterpart: full A/B/Bp/D/G/H legs + ICs,
  pvol spearmans, `feats*` lists, maker rates, orders/fills,
  `overlap_ABpD`/`overlap_ABDG`/`overlap_ABDH`, opt10/FNG-daily/COT-weekly
  grids + asof coverage, full `meta`. Leader extras: `reference_v154`
  (matches audited v154), rounded `mean_g` (3dp vs blind 4dp), manifest
  scenario triplication + notes.

## F. Manifest notes / verdict

- `v158/result_manifest.json`: track A, `rejected`, `live_approved:false`,
  audit pending. Single realistic 1m scenario repeated in 3 slots
  (3.437/19.0, fills 10854, 60 months); note matches the numbers (BTC+ETH
  options member 3.437/19.0 vs v154 3.515/19.15 — blind Bp leg 3.120/18.74
  confirms the mechanism). Blind reproduces every row/year/fill/DD
  bit-exact.
- `v159/result_manifest.json`: track B, `rejected`, `live_approved:false`,
  audit pending. Single realistic 1m scenario repeated in 3 slots
  (3.336/18.75, fills 10879, 60 months); note matches the numbers (Fear &
  Greed member 3.336/18.75 vs v154 — blind G leg 2.319/25.66 confirms the
  dilution). Blind reproduces every row/year/fill/DD bit-exact.
- `v160/result_manifest.json`: track C, `rejected`, `live_approved:false`,
  audit pending. Single realistic 1m scenario repeated in 3 slots
  (2.681/19.13, fills 10894, 60 months); note matches the numbers (COT
  member hurts 2.681/19.13 vs v154 — blind H leg −0.371/26.77 with the
  2021 +4.03 year confirms the mechanism). Blind reproduces every
  row/year/fill/DD bit-exact.
- No look-ahead in the ETH-options outer join, the FNG D+1h asof, the COT
  D+4d asof, the pre-xs merges, the vol wrappers, xs timing, embargoes,
  tranching, scales, governor timing, or the 1m fill/cost paths. All three
  primary-row DDs (19.00 / 18.75 / 19.13) sit inside the 20% acceptance
  gate, but no row clears the monthly≥5% gate on this engine — consistent
  with `rejected`. Audit complete; leader files untouched.

## Files

- `replication.json` (Part A, blind, frozen), `replicate_v158_v160.py`,
  `tests/test_v158_v160_audit.py` pass 4/4.
