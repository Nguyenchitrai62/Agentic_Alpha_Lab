# v156 + v157 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v156_v157_audit/` +
`tests/test_v156_v157_audit.py` only. Base: v154 replication (members A, B, D
from `v154_audit`, rebuilt inline here from the assignment text + audited
replication code). No leader files edited.

Blind protocol: `replication.json` (`replicate_v156_v157.py`,
`tests/test_v156_v157_audit.py` passing 4/4) was saved BEFORE any Part B
comparison. Pre-save reads were limited to the allowed base (`AGENTS.md`,
`OPENCODE_VF_COMMON.md`, `OPENCODE_V156_V157_AUDIT.md`, skill,
`v154_audit/replicate_v154.py` + `replication.json` + `COMPARISON.md`,
`v151_v152_audit` replication + COMPARISON, `v129_v131_audit` pvol rows,
`src/agentic_alpha_lab/patterns/macro.py` + `implied_vol.py` (read as data
contracts for the inline E/F math, never imported), raw 4h/1d/funding/spot/
Coinbase/Bitstamp panels, carry, 1m intraday, Deribit options/DVOL parquets,
macro daily CSVs; directory listing showed `v156/`/`v157/` filenames only, no
file contents). `v156/` (`v156_ensemble_dvol.py`, `v156_result.json`,
manifest, logs) and `v157/` (`v157_ensemble_macro.py`, `v157_result.json`,
manifest, logs) were first opened after the Part A save. Part A imports no
v156/v157/v154/v151/v150/v144/v142/v141/v111 leader module and does not import
`agentic_alpha_lab.patterns.macro` (F-leg math is an inline copy, verified
bit-identical to `macro.compute`, see §B). No breach to log.

Key maps: blind `v156.rows.{reference_t15_ungoverned,t20_governed,
primary_t25_governed}` <-> leader `v156_result.json` same keys; blind
`v157.rows.*` <-> leader `v157_result.json` same keys. Thresholds per
assignment: return diff > 1pp, DD diff > 0.5pp.

## A. Number comparison (blind vs leader) — bit-exact everywhere

| row (v156) | blind monthly / fullDD | leader monthly / fullDD | Δ monthly | Δ DD |
|---|---|---|---|---|
| reference_t15_ungoverned | 2.233 / 16.11 | 2.233 / 16.11 | 0 | 0.00pp |
| t20_governed | 2.642 / 18.13 | 2.642 / 18.13 | 0 | 0.00pp |
| primary_t25_governed | 2.979 / 19.44 | 2.979 / 19.44 | 0 | 0.00pp |

| row (v157) | blind monthly / fullDD | leader monthly / fullDD | Δ monthly | Δ DD |
|---|---|---|---|---|
| reference_t15_ungoverned | 2.187 / 14.16 | 2.187 / 14.16 | 0 | 0.00pp |
| t20_governed | 2.568 / 17.44 | 2.568 / 17.44 | 0 | 0.00pp |
| primary_t25_governed | 2.937 / 18.80 | 2.937 / 18.80 | 0 | 0.00pp |

(Δ = leader − blind.) No 1pp / 0.5pp threshold exceeded anywhere.

Yearly nets/DDs/fills blind = leader in all 6 rows x 5 years (max abs net
diff 0.00pp, DD diff 0.00pp, fills diff 0):

- v156 t15: 19.21/14.38/2151, 19.44/8.33/2190, 52.94/11.39/2190,
  38.23/7.93/2190, 25.02/8.54/2185.
- v156 t20: 15.86/17.68/2155, 25.26/10.47/2190, 67.86/14.18/2190,
  50.98/9.82/2190, 30.01/11.53/2185.
- v156 t25: 15.18/18.91/2159, 24.18/11.32/2190, 82.86/15.19/2190,
  60.19/10.51/2190, 38.95/12.56/2185.
- v157 t15: 21.27/13.76/2116, 23.03/8.54/2190, 51.73/11.49/2190,
  33.10/9.73/2190, 21.55/9.71/2185.
- v157 t20: 16.44/17.44/2119, 31.09/11.27/2190, 66.30/14.26/2190,
  44.26/11.54/2190, 25.03/13.26/2185.
- v157 t25: 15.41/18.78/2120, 33.41/12.27/2190, 82.59/14.45/2190,
  49.38/12.31/2190, 35.23/13.73/2185.

Mean_g blind (4dp) vs leader (3dp): max abs diff 0.0005 (rounding only, e.g.
v156 t20 2022 0.9998 vs 1.0, v157 t20 2024 0.9965 vs 0.997); ungoverned
mean_g = 1.0 both sides.

Blind member legs (no leader counterpart published for E/F):

- A (v144): t15 2.361/16.89, t20 2.955/18.28, t25 3.374/19.63 —
  bit-exact vs the frozen `v154_audit` values (and the audited v144 values).
- B (opt WITH xs): t15 2.446/15.53, t20 3.039/17.44, t25 3.465/19.15 —
  bit-exact vs frozen `v154_audit` B.
- D (coinbase): t15 2.423/14.50, t20 2.798/17.70, t25 3.061/22.60 —
  bit-exact vs frozen `v154_audit` D.
- E (dvol): t15 0.565/28.84, t20 0.845/34.48, t25 0.891/39.32. The DVOL
  leg is by far the weakest member: v92 ICs
  0.0173/-0.0066/0.1175/0.1434/0.0151 (vs A
  0.0662/-0.0539/0.1148/0.1029/0.1425) and the engine rows never clear
  1%/month with DDs 29-39%. Averaging it in dilutes the ensemble —
  exactly the leader manifest note ("Adding a DVOL member hurts:
  2.979/19.44 vs v154 3.515/19.15").
- F (macro): t15 0.491/31.23, t20 0.385/32.34, t25 0.438/34.39. The macro
  leg is the weakest member on every row (v92 ICs
  0.0851/-0.0459/0.0749/0.0540/0.1273); DDs 31-34%. Same dilution pattern —
  leader note ("Adding a macro member hurts: 2.937/18.8 vs v154
  3.515/19.15").
- v156 t25 2.979 sits below every one of A/B/D (3.374, 3.465, 3.061) and
  far above E (0.891) with DD 19.44; v157 t25 2.937 likewise below A/B/D
  and above F (0.438) with DD 18.80. Both ensembles underperform v154
  (3.515/19.15) on the primary row while staying inside the 20% DD gate.

Leader `reference_v154.t25` (3.515, 19.15) matches the audited v154 values
in both result JSONs. Leader manifest fills (v156 10914, v157 10875) equal
the blind yearly-fill sums (v156 t25: 2159+2190+2190+2190+2185 = 10914;
v157 t25: 2120+2190+2190+2190+2185 = 10875); blind `fills_live`
(turn-based, 10913 / 10874) differs by the known 1-bar year-boundary quirk,
same as the `v154_audit` §A note. Maker rates blind 0.634-0.635 both
ensembles; leader publishes no maker counterpart.

## B. Why it matches — construction verified leg by leg

- A/B/D legs: blind A/B/D monthlies, fullDDs, and ICs are bit-exact vs the
  frozen `v154_audit/replication.json` values (asserted in-script and in
  tests), so the shared 3/4 of each ensemble is exact by inheritance.
- E leg DVOL: blind hourly math (c = close where >0 else NaN; chg24/168 =
  log(c/c.shift(24/168)); z = (c − rolling2160 mean(min720)) / rolling2160
  std(min720, ddof=1, pandas default); asof per panel t = last candle with
  avail_utc ≤ t+4h via merge_asof backward; rvspread =
  lvl − 100·vol180_BTC(t)·√2190 with the v114-panel BTC vol180 at t; one
  value per t merged on t into v114+v103 BEFORE xs; xs on BASE/BASE+FLOWX
  only, no `xs_dvol_*`/`xr_dvol_*`; return feats 49/65; vol on original
  26/36) ≡ leader `dvol_features()` (`:35-48`: same avail_utc sort,
  same `where(>0)`, same shifts, same `rolling(2160, min_periods=720)` with
  default ddof=1, same `merge_asof(close_at=t+4h, avail, backward)`, same
  `100*vol180*sqrt(2190)` off the v114 BTC rows). Order-of-sort is
  equivalent (avail_utc = ts_utc+1h monotone). DVOL live full-row coverage
  is 1.000 both sides (hourly history from 2021-03-24, live from
  2021-09-24). Bit-exact ensemble output confirms the reading, including
  the ddof=1 choice the assignment leaves implicit.
- F leg macro: blind F math is a line-for-line inline copy of
  `macro.compute` (NOT imported): same 6-asset CSVs, same per-asset ffill,
  SMA50/200, dist/ret20/rv20(ddof=0), risk score, dxy_chg_20d, btc-qqq
  corr60, same date+22h availability with searchsorted-right-1 asof on
  bars (t, close_time = t+4h−1ms) over the unique panel times, merged on t
  BEFORE xs; xs on BASE/BASE+FLOWX only, no `xs_mac_*`/`xr_mac_*`; return
  feats 71/87 (26+27+18 / 36+27+24); vol on original 26/36. Verified
  pre-save: inline output − `macro.compute` output = 0.0 on every column
  over a sampled bar window. Faithfully replicated quirk (documented, not
  fixed): `mac_btc_qqq_corr_60d` is all-NaN (QQQ reindexed to the daily
  union without ffill, so every 60-day window contains weekend NaNs and
  never reaches min_periods=60) — identical in `macro.compute` (0/1839
  non-NaN on the daily grid) and in the blind asof (live full-row
  coverage 0.0 on the 27-col set, all other 26 cols fully covered live).
  HGB routes NaN natively, so the dead column rides along harmlessly on
  both sides. Leader's `books_macro()` (`:32-50`) calls `macro.compute`
  on exactly these bars and merges on t with the same vol-wrapper
  exclusion — bit-exact ensemble output confirms equivalence (blind union
  of v114+v103 times ≡ leader's v114-only times: v103 times ⊆ v114 times,
  same 10950 live bars).
- Ensemble math: blind 4-way union index with missing→0, /4 average of
  four already-scaled causal book series at the same t ≡ leader `:73-74`
  (v156) / `:61-62` (v157) (`union`, `reindex().fillna(0.0)`, `/4`).
  Missing→0 applies to no bars here (all four grids 10950). Vol
  recomputed from each ensemble's books with the same rolling-360/min-120
  formula; opens/carry shared (identical grids).
- Engine: sequential governor j=i-2, 540-bar peak, clip((0.20−DD)/0.10),
  per-target s cap 2, 10bps 1m rule (T=t+4h, strict through minutes 2..14,
  maker 0.0002 rel ∓0.0010 else taker 0.0005) ≡ audited `books_v142()` +
  `simulate()`. `books_v142()` adds xs via `v142.add_xs(panel, BASE[/+FLOWX])`
  on fixed base lists, so merged DV/macro cols get no xs versions on both
  sides; the vol wrappers (`v156 :59`, `v157 :46`) drop exactly the 5 DV /
  27 macro cols before the audited `vol_predict` — embargoes, causal fv
  target, left-join replace unchanged.

## C. Look-ahead audit

### `v156/v156_ensemble_dvol.py` — no look-ahead found

- Chain (`:28-32` + `:66-71`): imports the audited `v144_deploy_v3`,
  `v151_info_ensemble` (audited v150-options path), and
  `v154_ensemble_coinbase` (audited §B of `v154_audit`) modules only; no
  data touched directly. Pass.
- E leg (`:35-62`): `dvol_features(p92)` builds strictly trailing
  hourly indicators (shifts/rollings on the hourly DVOL series — causal);
  availability is `avail_utc` (the file's own availability stamp =
  ts+1h) and the join is `merge_asof(close_at=t+4h, avail, backward)`, so
  a panel row t sees only candles available by its bar close (t+4h is 1ms
  after close_time = t+4h−1ms). `c>0` mask, log-change NaN propagation,
  and z denominator handling are past-only. `dvol_rvspread` uses the BTC
  row's own trailing-180 4h vol at the same bar t (contemporaneous only).
  Merge is on t into both builds before `books_v142()` adds xs on the
  fixed BASE/BASE+FLOWX lists (no xs of DVOL cols); the vol wrapper
  (`:59`) drops exactly the 5 DV cols. `cb_bars`/`load_asset` patches
  (`:54-55`) are the audited v114 extension. Pass — matches the
  assignment's DVOL-availability rule.
- Ensemble (`:73-74`): union index, `fillna(0.0)`, /4 average of four
  already-scaled causal book series at the same t — contemporaneous only.
  Pass.
- Simulate (`:75`): audited `v144.simulate(p103, books)` unchanged —
  trailing vol, per-target s cap 2, governor j=i-2, 10bps 1m fills,
  carry/funding per AGENTS.md. `p103` from the A leg shares the grid with
  B/D/E (merges add columns, not rows). Pass.
- Costs/funding per AGENTS.md; target choice ex post (0.25 primary) is the
  disclosed v144 frontier, unchanged by v156.

### `v157/v157_ensemble_macro.py` — no look-ahead found

- Chain (`:25-29` + `:54-59`): imports the audited `v144_deploy_v3`,
  `v151_info_ensemble`, and `v154_ensemble_coinbase` modules plus the
  audited `agentic_alpha_lab.patterns.macro` worker module only; no data
  touched directly. Pass.
- F leg (`:32-50`): `macro.compute(bars)` with bars =
  (t, close_time = t+4h−1ms) over the unique v114 panel times implements
  the audited 22:00 UTC rule (daily D known after date+22h; asof = latest
  date with date+22h ≤ close_time; weekends/holidays ffill) — all daily
  indicators are trailing rollings with full-window min_periods (causal);
  BTC-QQQ corr60 and risk-score edge cases are past-only (the all-NaN
  corr column, §B, is a dead feature on both sides, not a leak). Merge is
  on t into both builds before the fixed-list xs step (no xs of macro
  cols); the vol wrapper (`:46`) drops exactly the 27 macro cols.
  `cb_bars`/`load_asset` patches (`:36-37`) are the audited v114
  extension. Pass — matches the assignment's macro-22:00-UTC rule.
- Ensemble (`:61-62`) and simulate (`:63`): same contemporaneous-only
  averaging and audited engine as v156. Pass.
- Costs/funding per AGENTS.md; target choice ex post (0.25 primary) is the
  disclosed v144 frontier, unchanged by v157.

## D. Aggregation alignment

Covered by `v154_audit` §D (Deribit bar = `ts.floor(4h)`; Coinbase 1h
candle opening at T+3h closes at the 4h bar close) with two new paths, both
verified above: DVOL hourly candle timestamped `ts_utc`, available at
`avail_utc` (= ts+1h), joined backward to bar-close time t+4h with 2-bar
execution lag downstream; macro US daily close for day D available at
D+22h UTC, joined backward to bar close_time = t+4h−1ms with the same
2-bar lag. No new data path beyond these two asof joins.

## E. Post-hoc corrections / protocol log

- No breach: no `v156/` or `v157/` file was opened before the Part A save
  (`replication.json` + 4/4 tests). No change to `replication.json`,
  `replicate_v156_v157.py`, or `tests/test_v156_v157_audit.py` after
  opening `v156/`/`v157/` for Part B.
- One implicit-spec gamble logged here (resolved bit-exact): the
  assignment's `dvol_z` leaves the rolling-std ddof implicit — blind fixed
  pandas-default ddof=1 before running; leader `:43` uses the same default.
  The all-NaN `mac_btc_qqq_corr_60d` quirk (§B) was found pre-save via the
  inline-vs-`macro.compute` equality check and frozen as-is; fixing it
  would have diverged from the leader.
- Blind extras with no leader counterpart: full A/B/D/E/F legs + ICs,
  pvol spearmans, `feats*` lists, maker rates, orders/fills,
  `overlap_ABDE`/`overlap_ABDF`, DVOL hourly/asof grids + live coverage,
  macro daily/asof grids + live coverage, full `meta`. Leader extras:
  `reference_v154` (matches audited v154), rounded `mean_g` (3dp vs blind
  4dp), manifest scenario triplication + yearly arrays + notes.

## F. Manifest notes / verdict

- `v156/result_manifest.json`: track A, `rejected`, `live_approved:false`,
  audit pending. Single realistic 1m scenario repeated in 3 slots
  (2.979/19.44, fills 10914, 60 months); note matches the numbers (DVOL
  dilution vs v154 3.515/19.15 — blind E leg 0.891/39.32 confirms the
  mechanism). Blind reproduces every row/year/fill/DD bit-exact.
- `v157/result_manifest.json`: track B, `rejected`, `live_approved:false`,
  audit pending. Single realistic 1m scenario repeated in 3 slots
  (2.937/18.8, fills 10875, 60 months); note matches the numbers (macro
  dilution vs v154 — blind F leg 0.438/34.39 confirms the mechanism).
  Blind reproduces every row/year/fill/DD bit-exact.
- No look-ahead in the DVOL availability join, the macro 22:00 UTC asof,
  the pre-xs merges, the vol wrappers, xs timing, embargoes, tranching,
  scales, governor timing, or the 1m fill/cost paths. Both primary-row DDs
  (19.44 / 18.80) sit inside the 20% acceptance gate, but no row clears
  the monthly≥5% gate on this engine — consistent with `rejected`. Audit
  complete; leader files untouched.

## Files

- `replication.json` (Part A, blind, frozen), `replicate_v156_v157.py`,
  `tests/test_v156_v157_audit.py` pass 4/4.
