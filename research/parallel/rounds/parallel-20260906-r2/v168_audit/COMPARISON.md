# v168 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v168_audit/` +
`tests/test_v168_audit.py` only. Base: v154 replication (members A = v144
books, B = + v150 options features, D = + v111 Coinbase premium features;
leader modules imported, not copied). No leader files edited.

Blind protocol: `replication.json` (`replicate_v168.py`,
`tests/test_v168_audit.py` passing 3/3) was saved BEFORE any Part B
comparison. No `v168/` file was opened before the Part A save (workspace
mapping listed the parent directory only; the v168 file list was globbed
without reading contents). No Part A file was changed after the save.

Key maps: blind `v168_quant.{reference_t15_ungoverned,t20_governed,
primary_t25_governed}` <-> leader `v168_result.json` same keys.
Thresholds per assignment: return diff > 1pp, DD diff > 0.5pp must be
explained.

## A. Number comparison (blind vs leader) — bit-exact everywhere

| row | blind monthly / fullDD | leader monthly / fullDD | Δ monthly | Δ DD |
|---|---|---|---|---|
| reference_t15_ungoverned | 2.035 / 16.88 | 2.035 / 16.88 | 0 | 0.00pp |
| t20_governed | 2.402 / 17.71 | 2.402 / 17.71 | 0 | 0.00pp |
| primary_t25_governed | 2.668 / 19.59 | 2.668 / 19.59 | 0 | 0.00pp |

(Δ = leader − blind.) No 1pp / 0.5pp threshold exceeded anywhere.

Yearly nets/DDs/fills/mean_g blind = leader in all 3 rows x 5 years:

- t15: 14.61/14.19/2118, 25.22/10.28/2190, 35.05/12.72/2190,
  33.03/8.64/2190, 29.88/6.83/2185 (mean_g 1.0 all years both sides).
- t20: 11.15/17.40/2120, 29.04/13.66/2190, 43.87/14.73/2190,
  45.79/11.42/2190, 38.13/9.03/2185.
- t25: 9.38/19.59/2123, 27.32/14.65/2190, 56.94/15.90/2190,
  54.03/13.88/2190, 44.19/10.77/2185.

Blind train_rows per anchor (all members): h6/h18 =
33388/33328, 44338/44278, 55288/55228, 66268/66208, 77218/77158 —
identical to the audited v103 filters in `v154_audit/replication.json`,
confirming the cutoff (anchor − 4h×78) and per-horizon row filter
(t + 4h×(h+1) < cutoff, y{h} not NaN) were kept.

Blind diagnostic (k = 1, median only — no leader counterpart):

- t15 2.004/17.22, t20 2.387/18.40, t25 2.659/20.02.
- Multiplier effect (quant×k minus median): t25 +0.009pp monthly,
  DD 19.59 vs 20.02 (−0.43pp); t20 +0.015pp, DD −0.69pp;
  t15 +0.031pp, DD −0.34pp. The multiplier is real but tiny.
- Median effect (v154 → median-only): t25 3.515 → 2.659 (−0.856pp),
  DD 19.15 → 20.02 (+0.87pp). Almost the entire loss comes from
  replacing the MSE regressor mean with the quantile median, not from
  the confidence multiplier.

Blind Spearman IC per anchor (m vs y6 | audited v103 baseline vs y6):

- A: 0.0630|0.0665, 0.0416|0.0389, 0.0553|0.0661, 0.0633|0.0267,
  0.0405|0.0563.
- B: 0.0640|0.0700, 0.0562|0.0525, 0.0406|0.0670, 0.0785|0.0526,
  0.0437|0.0508.
- D: 0.0653|0.0583, 0.0573|0.0367, 0.0747|0.0776, 0.0315|0.0052,
  0.1219|0.1332.
- Rank signal is roughly preserved (median sometimes wins, e.g. A-2024,
  B-2024, D-2022); the portfolio loss is magnitude/sizing, consistent
  with the manifest note "the MSE regressor is better".

Leader `reference_v154.t25` (3.515, 19.15) matches the audited v154
values. Manifest fills 10878 / 60 months are consistent with blind
t25 fills sums (2123+2190+2190+2190+2185 = 10878).

## B. Why it matches — construction verified

- Quantile spec: blind `loss="quantile"`, q ∈ (0.25, 0.5, 0.75),
  max_depth 4, lr 0.03, max_iter 400, min_samples_leaf 300,
  l2 1.0, random_state 0 ≡ leader `:48-49`. HS = (6, 18),
  EMBARGO = 78 from `v103.HS/EMBARGO` (not hardcoded).
- Cutoff/row filter/test window: blind cutoff = anchor − 4h×EMBARGO,
  tr = t < cutoff & y{h} notNaN & t+4h×(h+1) < cutoff, te =
  [anchor, anchor+365d) ≡ leader `:39-40,:44-45`.
- m/s: blind m = mean_h q50, s = mean_h max(q75−q25, 1e-3) ≡ leader
  `:51,:54`. Floor 1e-3 both sides.
- c_ref: blind common = t < cutoff & y6&y18 notNaN &
  t+4h×(maxH+1) < cutoff, predict with fitted models, c_tr =
  |m_tr|/s_tr, c_ref = median ≡ leader `:55-57` (per-h tr predictions
  intersected). Since h=18 is stricter, blind common mask =
  leader index intersection; bit-exact results prove equivalence.
- k/pred: blind clip((|m|/s)/c_ref, 0.5, 1.5), pred = m×k ≡ leader
  `:58-59`. Blind finite guards (c_ref fallback 1.0, NaN k→1.0) never
  triggered (blind c_ref 0.074–0.123 across members/anchors).
- Members: blind A = `v144.books_v142` patched; B = `v150.opt_features`
  + v151 glue (vol excludes OPT); D = `v111.add_cb` + v154 glue (vol
  excludes CB) ≡ leader `fresh_v144`/`with_extra` (`:64-79`).
  v92/v94 untouched both sides.
- Ensemble/simulate: blind union index missing→0, (A+B+D)/3, p103 grid
  from A leg, `v144.simulate` ≡ leader `:90-92`. Shapes 10950 each leg,
  union 10950 both sides.

## C. Look-ahead audit

### `v168/v168_quantile_confidence.py` — no look-ahead found

- Training scope (`:43-50`): per-h tr uses only t < cutoff with the
  audited label-realization filter; models fit on tr[feats] → tr[y{h}].
  Feats at row t use only bars closed at t (audited panels). Pass.
- c_ref (`:50-57`): `P_tr` predicted from `tr[feats]` (in-sample
  training rows only); `common` = intersection of the two per-h tr
  indexes (training rows common to both horizons); `c_ref` = median —
  a per-anchor training constant known at training time. No test row
  (`te`) enters. The in-sample use is disclosed ("in-sample, known at
  training time") and causal. Pass — this is the exact check the
  assignment asked for.
- Test scaling (`:54,:58`): m_te/s_te from te[feats] (current bar t
  only); k = clip(c/c_ref) rescales the contemporaneous prediction by
  the training constant. No future-t row enters. Pass.
- Isolation (`:64-69,:82-89`): fresh `v144` instance per member; only
  `v103.train_predict` patched (v92/v94 never touched); B/D
  `with_extra` merges market features on t with vol wrappers excluding
  OPT/CB — same audited glue as v151/v154. D `cbf` built from the
  unpatched `build()` grid (`:[88]`), so no quantile output leaks into
  features. Pass.
- Ensemble/simulate (`:90-92`): union index, fillna(0.0), /3 of three
  already-scaled causal book series at the same t; audited
  `simulate` (trailing vol, governor j=i−2, 10bps 1m, carry/funding).
  Pass.
- Costs/funding per AGENTS.md; target choice ex post (0.25 primary) is
  the disclosed v144 frontier, unchanged by v168.

## D. Aggregation alignment

No new data path in v168 (opt/cb joins unchanged from v150/v111 via
the audited v151/v154 glue; bar-T to panel-row-t timing with 2-bar
execution lag downstream). No new timing claim to verify.

## E. Post-hoc corrections / protocol log

- No v168/ file opened before `replication.json` was saved.
- No change to `replication.json`, `replicate_v168.py`, or
  `tests/test_v168_audit.py` after opening `v168/` for Part B.
- Blind extras with no leader counterpart: median-only (k=1) rows,
  per-anchor c_ref/mean_k/clip shares/train_rows/n_common, IC
  m-vs-y6 and baseline-vs-y6, member OPT/CB meta. Leader extras:
  `reference_v154` (matches audited v154), per-year sharpe/monthly
  breakdowns (blind stores net/DD/fills/mean_g).

## F. Manifest notes / verdict

- `v168/result_manifest.json`: track A, `rejected`,
  `live_approved:false`, audit pending. Single realistic 1m scenario
  repeated in 3 slots (2.668/19.59, fills 10878, 60 months); note
  matches the numbers (quantile median loses short-horizon signal vs
  v154 3.515/19.15; IQR multiplier does not compensate — blind
  diagnostic confirms: median-only 2.659/20.02, multiplier only
  +0.009pp/−0.43pp DD). Blind reproduces every row/year/fill/DD
  bit-exact.
- No look-ahead in the quantile fits, c_ref, k timing, xs timing,
  embargoes, tranching, scales, governor timing, or the 1m fill/cost
  paths. Primary-row DD 19.59 is inside the 20% acceptance gate, but no
  row clears the monthly>=5% gate on this engine — consistent with
  `rejected`. Audit complete; leader files untouched.

## Files

- `replication.json` (Part A, blind, frozen), `replicate_v168.py`,
  `tests/test_v168_audit.py` pass 3/3, `COMPARISON.md` (this file).
