# v163 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v163_audit/` +
`tests/test_v163_audit.py` only. Base: v154 blind replication
(`v154_audit/replicate_v154.py` + `replication.json`, bit-exact vs leader
v154 3.515/19.15). No leader files edited.

Blind protocol: `replication.json` (`replicate_v163.py`,
`tests/test_v163_audit.py` passing 4/4 on the blind-only tests) was saved
BEFORE any Part B comparison. No `v163/` file was opened before the Part A
save; workspace mapping listed the parent directory only. `replicate_v163.py`
imports no leader module (no `spec_from_file_location`/`exec_module`, no
`import v163/v154/v144/v150/v111/v151`; enforced by
`test_no_leader_v163_imports_in_blind_script`), all formulas are inline from
the assignment text + audited v154 replication code + raw data + carry + 1m
intraday, and no Part A file was changed after the save.

Key maps: blind `v163.rows.{reference_t15_ungoverned,t20_governed,
primary_t25_governed}` <-> leader `v163_result.json` same keys.
Thresholds per assignment: return diff > 1pp, DD diff > 0.5pp.

## A. Number comparison (blind vs leader) — bit-exact everywhere

| row | blind monthly / fullDD | leader monthly / fullDD | Δ monthly | Δ DD |
|---|---|---|---|---|
| reference_t15_ungoverned | 2.472 / 15.69 | 2.472 / 15.69 | 0 | 0.00pp |
| t20_governed | 3.059 / 17.32 | 3.059 / 17.32 | 0 | 0.00pp |
| primary_t25_governed | 3.374 / 19.02 | 3.374 / 19.02 | 0 | 0.00pp |

(Δ = leader − blind.) No 1pp / 0.5pp threshold exceeded anywhere.

Yearly nets/DDs/fills blind = leader in all 3 rows x 5 years (max abs
net diff 0.00pp, DD diff 0.00pp, fills diff 0):

- t15: 14.09/13.61/2000, 30.02/8.17/2190, 58.74/11.02/2190,
  36.61/8.71/2190, 34.57/8.15/2185.
- t20: 9.90/17.32/2001, 41.18/10.82/2190, 82.23/13.16/2190,
  48.76/10.94/2190, 45.00/10.74/2185.
- t25: 8.20/19.02/2014, 42.70/12.32/2190, 96.71/15.06/2190,
  54.01/12.28/2190, 56.59/11.47/2185.

Mean_g blind (4dp) vs leader (3dp): max abs diff 0.0005 (rounding
only, e.g. t25 2021 0.8676 vs 0.868, 2022 0.9774 vs 0.977, 2023 0.9565
vs 0.956; ungoverned mean_g = 1.0 both sides).

Blind member legs (no leader counterpart; smoothed A/B/D):

- A (v144 + smooth): t15 2.360/16.39, t20 2.963/18.45, t25 3.367/19.96 —
  vs unsmoothed v154 A 2.361/16.89, 2.955/18.28, 3.374/19.63. Smoothing
  barely moves A.
- B (opt WITH xs + smooth): t15 2.354/15.05, t20 2.948/19.54, t25
  3.316/21.22 — vs unsmoothed v154 B 2.446/15.53, 3.039/17.44,
  3.465/19.15. Smoothing hurts B (-0.149pp monthly on t25, +2.07pp DD).
- D (coinbase + smooth): t15 2.372/14.59, t20 2.724/18.04, t25
  2.940/22.66 — vs unsmoothed v154 D 2.423/14.50, 2.798/17.70,
  3.061/22.60. Smoothing hurts D (-0.121pp on t25).
- Ensemble t25 3.374 sits above all three smoothed members (3.367,
  3.316, 2.940) with DD 19.02 below B/D — same diversification pattern
  as v154, now pulled down by the smoothed B/D legs. Leader reference
  `reference_v154.t25` (3.515, 19.15) matches the audited v154 values.
- Manifest fills 10769 / 60 months are consistent with blind yearly
  fills sums (t25: 2014+2190+2190+2190+2185 = 10769; blind `fills_live`
  10768 differs by 1 from the yearly sum, same turn>1e-6 vs fills
  convention as the v154 audit).
- Training unchanged by construction: blind return-model `train_rows`
  match `v154_audit/replication.json` exactly in all 9 leg/model blocks
  (enforced in tests); blind ICs = v154 ICs (v92 A
  0.0662/-0.0539/0.1148/0.1029/0.1425 etc.); pvol spearmans = v129
  bit-exact (enforced in tests).

## B. Why it matches — construction verified leg by leg

- Smoothing scope: blind `smooth_pred_frame` sorts each OOS frame by
  (sym, t), applies `pred.ewm(span=6, adjust=False).mean()` per sym,
  returns sorted by (t, sym) — applied to all 9 frames (v92 LO, v94 LS,
  v103 LS × legs A/B/D) inside `build_books_from_oos` BEFORE the pvol
  left-join replace and BEFORE `weights_lo/ls_from_oos`. `vol42` itself
  is untouched (pvol replace only). Leader `:31-34` does the identical
  op (`sort_values(["sym","t"])`, `groupby("sym")`, `ewm(span=6,
  adjust=False)`); the weight stages (`raw_lo/raw_ls`) sort by t
  internally, so the leader's (sym,t) vs blind's (t,sym) return order is
  immaterial. Bit-exact yearly/monthly/DD equality confirms the scopes
  coincide (including cross-anchor carry: both smooth the full
  concatenated 5-year frame per sym, which is causal — past preds of the
  same frame only).
- A/B/D legs otherwise v154-exact: return feats v114 44 / v103 60 (A),
  49/65 (B with 5 opt cols, no `xs_opt_*`/`xr_opt_*`), 49/65 (D with 5
  cb cols, no `xs_cb_*`/`xr_cb_*`); xs = groupby-t mean + `rank(pct=True)`
  over majors at same bar t; vol models on original 26/36 sets (pvol
  trained once, reused); 0.25/0.25/0.5 tranch mean/6 own 0.20-cap-2;
  2-bar-lag returns.
- Ensemble math: blind union index (10950 = 10950 ∩ 10950 ∩ 10950,
  `overlap_ABD` recorded) with missing→0 ≡ leader `:65-66`
  (`A.index.union(B.index).union(D.index)`, `reindex(...).fillna(0.0)`,
  `/3`). Vol recomputed from the ensemble books with the same
  rolling-360/min-120 formula; opens/carry shared (identical grids).
- Engine: sequential governor j=i-2, 540-bar peak,
  clip((0.20-DD)/0.10), per-target s cap 2, 10bps 1m rule (T=t+4h,
  strict through minutes 2..14, maker 0.0002 rel ∓0.0010 else taker
  0.0005) ≡ audited `books_v142()` + `simulate()`.

## C. Look-ahead audit

### `v163/v163_prediction_smoothing.py` — no look-ahead found

- Smoothing (`:31-34`): `d.sort_values(["sym","t"])` then per-sym
  `ewm(span=6, adjust=False).mean()` uses the current and past preds of
  the same asset only — no future-t pred enters. The smoothed pred at t
  then flows into the unchanged v125/v129 weight pipeline with its
  2-bar execution lag downstream. Preds themselves are embargoed OOS
  outputs (v92 EMB 102, v94 144, v103 78 + t+h+1 filters, verified in
  the v154 audit). Pass.
- Patch isolation (`:37-44`): `_load` creates a fresh module instance
  per leg (`v144_A/B/D`), so the `raw_lo/raw_ls` monkey-patches
  (`:40-41`) are isolated per instance — legs cannot contaminate each
  other. The `cb_bars`/`load_asset` patches (`:42-43`) are the audited
  v114 extension. Same isolation pattern as the audited v154 script.
  Pass.
- A leg (`:58-59`): audited `books_v142()` unchanged apart from the
  causal smooth wrapper. Pass.
- B leg (`:60-61` via `with_extra` `:47-54`): `opt_features()` is the
  audited v150 math (reindex + fill present/past-only; trailing rolling
  6/180 windows; `merge(feats,on="t",how="left")` = bar T to panel row
  t=T, same timing as the row's own OHLCV; 2-bar execution lag
  downstream). Vol wrapper (`:51`) drops exactly the 5 OPT cols before
  the audited `vol_predict` — embargoes, causal fv target, left-join
  replace unchanged. `books_v142()` then adds xs/xr on the merged panels
  with the audited groupby-t mean + `rank(pct=True)` over majors present
  at the same bar t (contemporaneous only). Pass.
- D leg (`:62-64` via `with_extra`): `v111.add_cb` is the audited v111
  math — per 4h bar T the Coinbase 1h candle opening at T+3h (which
  closes at the bar close T+4h, `merge_asof` backward, tolerance 2h)
  gives cbp = 1e4*log(cb/binance); all features are trailing rolling
  means / 180-bar z-scores (p6 min4, p42 min30, m540/s540 min270 —
  causal). `cbf` (`:63`) drops `sym` and dedups to one value per t, then
  is merged on t into BOTH the v114 and v103 panels (`:53`) before
  `books_v142()` adds xs/xr on BASE / BASE+FLOWX only, so the coinbase
  columns get no xs/xr versions — matches the assignment. Vol wrapper
  drops exactly the 5 CB cols. Pass.
- Ensemble (`:65-66`): union index, `fillna(0.0)`, /3 average of three
  already-scaled causal book series at the same t — contemporaneous
  only, no future-t row enters. Pass.
- Simulate (`:67`): audited `v144.simulate(p103, books)` unchanged —
  trailing vol, per-target s cap 2, governor j=i-2, 10bps 1m fills,
  carry/funding per AGENTS.md. `p103` from the A leg shares the grid
  with B/D (merges add columns, not rows). Pass.
- Costs/funding per AGENTS.md; target choice ex post (0.25 primary) is
  the disclosed v144 frontier, unchanged by v163. `ema_span: 6` logged
  in both the result JSON and the blind `meta.smoothing`.

## D. Aggregation alignment

Covered by `v154_audit` §D (Deribit bar = `ts.floor(4h)`, trades in
[T,T+4h) → bar T; join on t is bar-close timing with 2-bar execution
lag) and the v111 docstring (Coinbase 1h candle opening at T+3h closes
at the 4h bar close; asof-backward tol 2h). No new data path in v163 —
smoothing touches only OOS preds, not bars, funding, carry, or 1m
intraday. Two observations: blind opt grid is 16952 bars (last
2026-09-26 04:00) vs 16951 at the v154 audit — the Deribit file gained
1 bar since; blind coinbase grid is 19947 bars (last 2026-09-26 04:00)
vs 19942 at v154 — the Coinbase files gained 5 bars since; the live
window (ends 2026-09-23) and all results are unaffected (live-window
coinbase coverage still complete: 1.000/0.986/0.986/1.000/1.000).

## E. Post-hoc corrections / protocol log

- No breach: no `v163/` file was opened before the Part A save.
- No change to `replication.json`, `replicate_v163.py`, or
  `tests/test_v163_audit.py` after opening `v163/` for Part B.
- Blind extras with no leader counterpart: full smoothed A/B/D legs +
  ICs, pvol spearmans, `feats114B`/`feats103B`/`feats114D`/`feats103D`
  lists, maker rates, orders/fills, `overlap_ABD`, coinbase
  coverage/first-full, full `meta` + `smoothing`. Leader extras:
  `ema_span`, `reference_v154` (matches audited v154), rounded `mean_g`
  (3dp vs blind 4dp), sha256 log in `run.log`.

## F. Manifest notes / verdict

- `v163/result_manifest.json`: track C, `rejected`,
  `live_approved:false`, audit pending. Single realistic 1m scenario
  repeated in 3 slots (3.374/19.02, fills 10769, 60 months); note matches
  the numbers (EMA(6) smoothing: 3.374/19.02 vs v154 3.515/19.15, 2021
  weaker — blind confirms: smoothed t25 2021 +8.20 vs v154 +18.38, while
  2025 holds +56.59 vs +56.34). Blind reproduces every row/year/fill/DD
  bit-exact.
- No look-ahead in the smoothing, the three legs, the opt/cb joins, the
  vol wrappers, xs timing, embargoes, tranching, scales, governor timing,
  or the 1m fill/cost paths. Primary-row DD 19.02 is inside the 20%
  acceptance gate, but no row clears the monthly>=5% gate on this
  engine — consistent with `rejected`. Audit complete; leader files
  untouched.

## Files

- `replication.json` (Part A, blind, frozen), `replicate_v163.py`,
  `tests/test_v163_audit.py` pass 4/4.
