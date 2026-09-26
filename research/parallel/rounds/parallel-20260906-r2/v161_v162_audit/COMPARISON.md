# v161 + v162 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v161_v162_audit/` +
`tests/test_v161_v162_audit.py` only. Base: v154 replication (members A, B, D
from frozen `v154_audit`, rebuilt inline here from the assignment text +
audited replication code). No leader files edited.

Blind protocol: `replication.json` (`replicate_v161_v162.py`,
`tests/test_v161_v162_audit.py` passing 4/4) was saved BEFORE any Part B
comparison. Pre-save reads were limited to the allowed base (`AGENTS.md`,
`OPENCODE_VF_COMMON.md`, `OPENCODE_V161_V162_AUDIT.md`, skill,
`v154_audit/replicate_v154.py` + `replication.json` + `COMPARISON.md`,
`v158_v160_audit` + `v151_v152_audit` COMPARISON/test patterns,
`v129_v131_audit` pvol rows, raw 4h/1d/funding/spot/Coinbase/Bitstamp panels,
carry, 1m intraday, Upbit `KRW-{BTC,ETH,XRP,SOL}_1h.parquet` + manifest,
spot `*_spot_4h[_2017].parquet` grids; directory listing showed `v161/`/`v162/`
names only, no file contents). `v161/` (`v161_ensemble_kimchi.py`,
`v161_result.json`, manifest, run.log) and `v162/` (`v162_monotone_trend.py`,
`v162_result.json`, manifest, run.log) were first opened after the Part A
save. Part A imports no
v161/v162/v154/v151/v150/v144/v142/v141/v111 leader module. No breach to log;
no change to `replication.json`, `replicate_v161_v162.py`, or
`tests/test_v161_v162_audit.py` after opening `v161/`/`v162/` for Part B.

Key maps: blind `v161.rows.{reference_t15_ungoverned,t20_governed,
primary_t25_governed}` <-> leader `v161_result.json` same keys; blind
`v162.rows.*` <-> leader `v162_result.json` same keys. Thresholds per
assignment: return diff > 1pp, DD diff > 0.5pp.

## A. Number comparison (blind vs leader) — bit-exact everywhere

| row (v161) | blind monthly / fullDD | leader monthly / fullDD | Δ monthly | Δ DD |
|---|---|---|---|---|
| reference_t15_ungoverned | 2.495 / 15.52 | 2.495 / 15.52 | 0 | 0.00pp |
| t20_governed | 3.081 / 17.83 | 3.081 / 17.83 | 0 | 0.00pp |
| primary_t25_governed | 3.434 / 19.28 | 3.434 / 19.28 | 0 | 0.00pp |

| row (v162) | blind monthly / fullDD | leader monthly / fullDD | Δ monthly | Δ DD |
|---|---|---|---|---|
| reference_t15_ungoverned | 2.095 / 14.96 | 2.095 / 14.96 | 0 | 0.00pp |
| t20_governed | 2.496 / 17.50 | 2.496 / 17.50 | 0 | 0.00pp |
| primary_t25_governed | 2.802 / 19.02 | 2.802 / 19.02 | 0 | 0.00pp |

(Δ = leader − blind.) No 1pp / 0.5pp threshold exceeded anywhere.

Yearly nets/DDs/fills blind = leader in all 6 rows x 5 years (max abs net
diff 0.00pp, DD diff 0.00pp, fills diff 0):

- v161 t15: 19.78/14.70/2139, 31.03/8.27/2190, 55.05/10.45/2190,
  37.02/9.22/2190, 31.53/7.95/2185.
- v161 t20: 17.90/17.83/2140, 41.93/11.01/2190, 76.52/13.34/2190,
  49.22/11.88/2190, 40.12/10.50/2185.
- v161 t25: 18.25/19.28/2141, 44.31/12.23/2190, 91.23/15.07/2190,
  55.22/12.80/2190, 49.71/10.98/2185.
- v162 t15: 12.47/13.79/2114, 29.18/8.53/2190, 53.59/10.44/2190,
  24.14/11.46/2190, 25.22/10.26/2185.
- v162 t20: 8.62/17.50/2118, 39.47/11.34/2190, 74.29/12.44/2190,
  28.69/16.40/2190, 29.15/13.24/2185.
- v162 t25: 7.48/18.94/2121, 40.80/12.78/2190, 89.79/14.26/2190,
  34.34/17.45/2190, 36.02/15.38/2185.

Mean_g blind (4dp) vs leader (3dp): max abs diff 0.0005 (rounding only, e.g.
v161 t20 2022 0.9985 vs 0.999, v162 t25 2024 0.9308 vs 0.931; ungoverned
mean_g = 1.0 both sides).

Blind member legs (no leader counterpart published for K / mono members):

- A (v144): t15 2.361/16.89, t20 2.955/18.28, t25 3.374/19.63 —
  bit-exact vs frozen `v154_audit` (ICs v92
  0.0662/-0.0539/0.1148/0.1029/0.1425 etc.; pvol spearmans = v129
  bit-exact, enforced in tests).
- B (opt WITH xs): t15 2.446/15.53, t20 3.039/17.44, t25 3.465/19.15 —
  bit-exact vs frozen `v154_audit` B.
- D (coinbase): t15 2.423/14.50, t20 2.798/17.70, t25 3.061/22.60 —
  bit-exact vs frozen `v154_audit` D.
- v154 baseline rebuilt inline: t15 2.528/16.27, t20 3.140/17.66, t25
  3.515/19.15 — bit-exact vs frozen `v154_audit` v154 and vs both leaders'
  `reference_v154.t25` (3.515, 19.15).
- K (upbit kimchi): t15 1.983/15.02, t20 2.337/20.29, t25 2.714/22.25.
  Weakest member on every row with the worst t25 DD of the v161 set
  (22.25); t25 years 14.34/50.87/64.64/51.18/16.14. Averaging K in gives
  v161 t25 3.434, below v154 (3.515) — the leader manifest note
  ("3.434/19.28 vs v154 3.515/19.15").
- Am/Bm/Dm (monotone v92/v94, v103 unchanged): t25 2.639/23.20,
  2.891/24.86, 2.592/24.74 — all far below their unconstrained parents
  (3.374/3.465/3.061) with DDs 23-25. v92 ICs collapse under the +1
  constraint (Am 0.0180/-0.0379/0.0866/0.0485/0.0919 vs A
  0.0662/-0.0539/0.1148/0.1029/0.1425; Dm 2025 0.1884 vs D 0.2610).
  v162 t25 2.802 sits above Dm but below Am/Bm unconstrained parents —
  the manifest note ("Monotone trend constraints hurt: 2.802/19.02 vs
  v154 3.515/19.15").

Leader manifest fills equal the blind yearly-fill sums (v161 t25:
2141+2190+2190+2190+2185 = 10896; v162 t25: 2121+2190+2190+2190+2185 =
10876).

## B. Why it matches — construction verified leg by leg

- A/B/D legs: blind A/B/D monthlies, fullDDs, ICs, and the rebuilt v154
  ensemble are bit-exact vs frozen `v154_audit/replication.json` (asserted
  in-script and in tests), so the shared 3/4 (v161) and the v162 base grids
  are exact by inheritance.
- K leg kimchi: blind math (Binance spot = concat 2017-if-exists + spot,
  dedup sorted; Upbit 1h close of the 1h candle with open_time <= t+3h via
  `merge_asof(key=t+3h, backward, tolerance 2h)`; `kp = 1e4*log(up/binance)`
  on each coin's own spot-bar grid; trailing `p6 min4 / p42 min30 /
  m540-sd540 min270 ddof1` smooth; market = smooth(kp_btc) on t; asset
  `rp = kp_a - kp_btc` outer-aligned on t (BTC rp = 0 where kp_btc defined
  else NaN; BNB all-NaN) then the same trailing smooth; market merged on t,
  asset on (t,sym) into v114+v103 BEFORE xs; xs on BASE/BASE+FLOWX only, no
  `xs_kp_*`/`xr_kp_*`; return feats 50/66; vol on original 26/36) ≡ leader
  `v161_ensemble_kimchi.py` `:39-67` + `:70-82` (same `key = t+3h`, same
  `merge_asof(..., backward, tolerance 2h)`, same `1e4*log(krw/close)`, same
  `rolling(6/42/540, min_periods=4/30/270)` default ddof1, same market/asset
  split, same `merge(market, on="t")` + `merge(asset, on=["t","sym"])`
  before `books_v142()`, same vol-wrapper exclusion of all 6 cols).
  Name mapping only: blind `kp_rp_dev/z/chg` <-> leader `rp_dev/z/chg`
  (values identical; names never enter the HGB except as distinct columns).
  Alignment note: blind smooths `rp` on the outer union grid while the
  leader smooths on each coin's own grid (`kp[c] - kp[BTC].reindex(...)`,
  BTC `kp*0.0`); over the live window (all coin grids start ≥2020-08 with
  ≥270-bar warmup before 2021-09-24; BTC/ETH grids identical 19947 bars)
  the trailing windows coincide — confirmed by bit-exact ensembles.
  BNB: leader asset table has no BNB row while blind writes explicit NaN
  rows; after the `(t,sym)` left merge both give NaN — equivalent.
  Raw grids: BTC/ETH 19947, XRP 18388, SOL 13418; market 19947 bars
  (2017-08-17 → 2026-09-26, NaNs 503/503/263); live coverage complete.
- v162 monotone: blind `mono_cst_for(feats)` list (`+1` where feat name in
  the 19-name MONO set, else 0; xs/xr/opt/cb all 0) ≡ leader `MonoHGB`
  (`monotonic_cst = {c: 1 for c in TREND if c in X.columns}`, `:27-30`,
  patched into `ext.v92`/`ext.v94` only, `:43-44`). List-vs-dict is the
  same constraint in sklearn 1.5.2 (verified bit-exact); v103 and
  `v129.vol_predict` are untouched on both sides; same embargoes/targets/
  splits (inside the audited v144 code). Leader D `cbf` built from
  `A_mod.v103.build()` times (`:66`) matches the audited v154 D path and
  the blind `build_coinbase_features()` over live (same bar-close timing).
- Ensemble math: blind `ensemble_ctx(ctxs, divisor)` (union index,
  `reindex(...).fillna(0.0)`, `/4` v161, `/3` v154/v162; vol recomputed
  from each ensemble's books with the same rolling-360/min-120 formula;
  opens/carry shared) ≡ leaders (`:93-94` / `:68-69`: `union`,
  `reindex(...).fillna(0.0)`, `/4` or `/3`). Missing→0 applies to no bars
  here (all member grids 10950; `overlap_ABDK` / `overlap_AmBmDm` recorded).
- Engine: sequential governor j=i-2, 540-bar peak, clip((0.20-DD)/0.10),
  per-target s cap 2, 10bps 1m rule (T=t+4h, strict through minutes 2..14,
  maker 0.0002 rel ∓0.0010 else taker 0.0005) ≡ audited `books_v142()` +
  `simulate()`. Bit-exact v152/v154 inheritance confirms the engine path.

## C. Look-ahead audit

### `v161/v161_ensemble_kimchi.py` — no look-ahead found

- Chain (`:32-36` + `:86-92`): imports the audited `v144_deploy_v3`,
  `v151_info_ensemble` (audited v150-options path), and
  `v154_ensemble_coinbase` (audited coinbase path) modules only; `premium()`
  touches raw Upbit/spot parquets directly with the causal asof below. Each
  `_load` creates a fresh module instance, so the `cb_bars`/`load_asset`/
  `build`/`vol_predict` monkey-patches in `books_kimchi()` (`:74-81`) are
  isolated per instance. Pass.
- `premium()` (`:39-49`): per 4h bar T the Upbit 1h candle with open_time
  <= T+3h (`key = open_time + 3h`, `merge_asof` backward, tolerance 2h)
  closes at T+4h at the latest — known at the bar close (close_time =
  T+4h−1ms); tolerance gaps give NaN, not forward fill. Matches the
  assignment's "1h candle with open_time <= t+3h (asof backward, tolerance
  2h)". Spot concat (`2017 prefix + spot file if exists`, dedup sorted)
  handles the SOL-no-2017 case (`:43`). Pass.
- `smooth()` (`:52-55`): strictly trailing rollings (6/42/540, min
  4/30/270, pandas-default ddof1) — causal. Pass.
- `kimchi_tables()` (`:58-67`): `kp` per coin on its own spot-bar grid;
  market = smooth(kp_BTC) per t; asset `rp = kp_a - kp_BTC` reindexed
  contemporaneously (`reindex(kp[c].index)`), BTC `kp*0.0` (0 where defined)
  — no future-t row enters; then trailing smooth per series. Docstring
  min-periods "4/30/270 as v111" matches the executed code and the
  assignment. Pass.
- K leg (`:70-82`): `market` merged on t and `asset` on (t,sym) into BOTH
  builds before `books_v142()` adds xs/xr on the fixed BASE/BASE+FLOWX
  lists, so the 6 kimchi cols get no xs/xr versions; vol wrapper (`:79`)
  drops exactly the 6 cols before the audited `vol_predict` — embargoes,
  causal fv target, left-join replace unchanged. `cb_bars`/`load_asset`
  patches (`:74-75`) are the audited v114 extension. BNB absent → NaN via
  the missing asset row. Matches the assignment's "market merged on t and
  asset merged on (t, sym) before the v142 xs step (no xs of them; vol
  models exclude them)". Pass.
- Ensemble (`:93-94`) and simulate (`:95`): contemporaneous-only averaging
  of four already-scaled causal book series at the same t; audited
  `simulate(p103, books)` unchanged — trailing vol, per-target s cap 2,
  governor j=i-2, 10bps 1m fills, carry/funding per AGENTS.md. `p103` from
  the A leg shares the grid with B/D/K (merges add columns, not rows).
  Pass.
- Costs/funding per AGENTS.md; target choice ex post (0.25 primary) is the
  disclosed v144 frontier, unchanged by v161.

### `v162/v162_monotone_trend.py` — no look-ahead found

- Chain (`:33-47` + `:61-67`): fresh `v144` instances per member
  (`fresh_v144("A"/"B"/"D")`), so MonoHGB patches do not leak across legs;
  `v150.opt_features()` / `v111.add_cb()` reuse audited math only. Pass.
- Mono constraint (`:23-30`, `:43-44`): `TREND` is exactly the assignment's
  19 names; `MonoHGB.fit` sets `monotonic_cst = {c: 1, ...}` for columns
  present (all other features 0/None) and only `ext.v92`/`ext.v94` are
  patched — v103 short-horizon models and `v129.vol_predict` stay
  unconstrained, matching "(v103 models unconstrained)". Constraint is a
  shape prior on the fitted function, not a data peep: same chronological
  splits/embargoes/targets as the audited v144 code (inside the loaded
  module). Pass.
- B/D legs (`:50-57`, `:64-67`): `with_extra` merges opt/cb feats on t into
  both builds before `books_v142()` (same bar-close timing as the row's own
  OHLCV); vol wrapper drops exactly the extra cols. Same as audited
  v151/v154 legs except the HGB class. Pass.
- Ensemble (`:68-69`) and simulate (`:70`): same contemporaneous-only
  averaging (union, fillna 0, /3) and audited engine as v161. Pass.
- Costs/funding per AGENTS.md; target choice ex post (0.25 primary) is the
  disclosed v144 frontier, unchanged by v162.

## D. Aggregation alignment

Covered by `v154_audit` §D (Deribit bar = `ts.floor(4h)`; Coinbase 1h candle
opening at T+3h closes at the 4h bar close; joins on t are bar-close timing
with 2-bar execution lag) with one new path: Upbit 1h candle with open_time
<= t+3h closes by t+4h at the latest (asof-backward tol 2h), joined on
t / (t,sym) at bar-close timing with the same 2-bar lag downstream. No new
data path beyond these asof joins. Observations: blind opt grid is 16952
bars (last 2026-09-26 04:00) vs 16951 at the v154 audit — the Deribit file
gained 1 bar since; blind coinbase grid is 19947 bars (2017-08-17 →
2026-09-26, last 2026-09-26 04:00 vs 2026-09-25 08:00 at v154 — file
extended); blind kp market is 19947 bars on the BTC spot grid with the same
span. The live window (ends 2026-09-23) and all results are unaffected.
FNG/COT-style availability logs do not apply here.

## E. Post-hoc corrections / protocol log

- No breach: no `v161/` or `v162/` file was opened before the Part A save
  (`replication.json` + 4/4 tests). No change to `replication.json`,
  `replicate_v161_v162.py`, or `tests/test_v161_v162_audit.py` after opening
  `v161/`/`v162/` for Part B. Tests pass 4/4 pre- and post-open.
- Implicit-spec gambles logged here (all resolved bit-exact): K asset
  column names (assignment gives market `kp_btc_*` but no literal asset
  names — blind fixed `kp_rp_dev/z/chg` before running; leader `:29`
  uses `rp_dev/z/chg`; values identical); K `rp` grid (assignment says
  "aligned on t" — blind fixed outer-union align + trailing smooth; leader
  `:64` smooths on each coin's own grid; equivalent over live, confirmed
  bit-exact); BTC `rp_z` (constant-0 series gives NaN z on both sides —
  left as NaN, HGB-native); BNB (leader omits the row, blind writes NaN
  rows — same post-merge NaNs); monotone list-vs-dict (assignment says
  "dict by feature name" — blind fixed aligned `+1/0` list; leader passes a
  `{name: 1}` dict; same constraint in sklearn 1.5.2, confirmed bit-exact).
- Blind extras with no leader counterpart: full A/B/D/K/Am/Bm/Dm legs + ICs,
  pvol spearmans, `feats*` lists, `mono_cst_114x`, maker rates, orders/fills,
  `overlap_ABDK`/`overlap_AmBmDm`, kp raw/market grids + coverages, full
  `meta`. Leader extras: `reference_v154` (matches audited v154), rounded
  `mean_g` (3dp vs blind 4dp), manifest scenario triplication + notes.

## F. Manifest notes / verdict

- `v161/result_manifest.json`: track A, `rejected`, `live_approved:false`,
  audit pending. Single realistic 1m scenario repeated in 3 slots
  (3.434/19.28, fills 10896, 60 months); note matches the numbers (Korean
  premium member 3.434/19.28 vs v154 3.515/19.15 — blind K leg 2.714/22.25
  confirms the dilution). Blind reproduces every row/year/fill/DD
  bit-exact.
- `v162/result_manifest.json`: track B, `rejected`, `live_approved:false`,
  audit pending. Single realistic 1m scenario repeated in 3 slots
  (2.802/19.02, fills 10876, 60 months); note matches the numbers
  (monotone constraints hurt 2.802/19.02 vs v154 — blind Am/Bm/Dm legs
  2.639/2.891/2.592 with DDs 23-25 confirm the mechanism). Blind reproduces
  every row/year/fill/DD bit-exact.
- No look-ahead in the Upbit T+3h asof, the kp/rp trailing smooths, the
  pre-xs merges, the vol wrappers, the monotone HGB patch scope, xs timing,
  embargoes, tranching, scales, governor timing, or the 1m fill/cost paths.
  Both primary-row DDs (19.28 / 19.02) sit inside the 20% acceptance gate,
  but no row clears the monthly>=5% gate on this engine — consistent with
  `rejected`. Audit complete; leader files untouched.

## Files

- `replication.json` (Part A, blind, frozen), `replicate_v161_v162.py`,
  `tests/test_v161_v162_audit.py` pass 4/4.
