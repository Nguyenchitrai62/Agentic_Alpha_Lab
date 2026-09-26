# v121 + v122 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v121_v122_audit/` +
`tests/test_v121_v122_audit.py` only. Base: audited v115 replication (books,
v110 engine, target 0.15 ungoverned). No leader files edited.

Blind protocol: `replication.json` (via `replicate_v121_v122.py`,
`tests/test_v121_v122_audit.py` passing) was saved BEFORE opening `v121/` or
`v122/`. Pre-save reads were limited to the allowed base (`v103/`,
`v114/`, `v92/`, `v94/`, `v110/`, `v115/`, `v115_audit/`, `v103_v105_audit/`,
`v113_v114_audit/`, audit/test files — not in the forbidden set). The parent
round listing exposed only `v121/`/`v122/` filenames (not contents).
`v121/v121_result.json`, `v121/v121_bagged_v103.py`, `result_manifest.json`,
`run.log` and the `v122/` counterparts were first opened after the Part A
save. Part A imports no v121/v122/v115/v114/v103/v110/v92/v94 leader module
(all formulas inline from the assignment text + audited OOS CSVs + raw data).
No post-save edits to `replication.json`.

## A. Number comparison (blind vs leader)

No IC (>0.01), return (>1pp), or DD (>0.5pp) threshold exceeded anywhere.

### v121 (bagged v103, track B)

ICs blind = leader (`ic_y6`/`ic_y18`):
2021: 0.0557/0.0702; 2022: 0.0246/0.055; 2023: 0.0552/0.0971;
2024: 0.0344/0.0556; 2025: 0.0848/0.1379. Max abs IC diff 0.0.

Secondary bagged LS book (own 20%-cap-2 scale), blind = leader on all
3 scenarios x 5 years: nets/DDs/fills/sharpes exact.
Normal yearly nets 17.55/0.96/54.70/46.10/61.86; DDs
19.93/23.48/9.86/14.15/10.59; fills 1736/2149/2154/2147/2025;
monthly 2.477/worst 23.48. Fee monthly 2.186/worst 24.53
(nets 14.15/-2.20/49.45/40.97/55.65). Exec monthly 1.824/worst 25.81
(nets 10.04/-6.02/43.13/34.81/48.21). Max abs net diff 0.00pp,
max abs DD diff 0.00pp.

Primary portfolio (0.25/0.25/0.5, v110 target 0.15 ungoverned), blind =
leader on all scenarios x years + monthlies/worst-year/full-path DDs:
normal monthly 2.447/worst 16.89/full 16.89 (yearly
10.38/15.97/54.97/47.06/46.24; DDs 16.89/12.01/7.96/10.07/7.76;
fills 1804/2179/2177/2181/2095); fee 2.235/17.44/18.38; exec
1.969/18.11/20.57. Max diffs 0.

### v122 (y168 monthly book, track C)

ICs + train rows blind = leader:
2021: 44655/0.173; 2022: 55605/-0.092; 2023: 66555/0.0785;
2024: 77535/0.171; 2025: 88485/0.0408. Max abs IC diff 0.0.

Secondary y168 LS book (own v94 20%-cap-2 scale on v114 panel), blind =
leader: normal yearly 14.58/12.63/34.48/23.28/51.46; DDs
23.96/11.43/20.61/16.30/15.04; fills 1424/2131/2159/2172/2107;
monthly 1.979/worst 23.96. Fee 1.776/24.53; exec 1.522/25.24. Exact.

Primary portfolio (0.2/0.2/0.4/0.2, v110 target 0.15 ungoverned), blind =
leader: normal monthly 2.546/worst 16.58/full 16.58 (yearly
14.50/16.81/55.51/48.59/46.22; DDs 16.58/9.14/8.23/10.67/6.94;
fills 1834/2183/2182/2187/2153); fee 2.345/17.04/17.04; exec
2.094/17.91/17.91. Max diffs 0.

Note: blind book sections additionally report `full_path_dd` (book-level
full-span DD over live span); leader secondaries report only
monthly/worst-year. Shared fields are bit-exact; the extra field triggers
no threshold.

## B. Why blind matched

- v103 panel: blind rebuilds the v92 base + spot prefix + 10 flow feats +
  BTC context exactly as the audited v103_v105 replication (train rows
  33388/33328 … 77218/77158 match v103). v114 panel: blind rebuilds the
  Coinbase + Bitstamp prepend + v92 features + BTC context exactly as the
  audited v113_v114 replication (y168 train rows 44655 … 88485 match v122).
- v121 bag: blind implements the spec literally — per (h,m) fresh
  `numpy default_rng(m).choice` over sorted unique UTC floor-D days of the
  per-horizon embargoed train set, `int(0.7*n_days)` without replacement,
  all rows of chosen days, HGB(v92 params + `max_features=0.7`,
  `random_state=m`), mean of 20 preds. Leader
  `train_predict_bag` (`v121_bagged_v103.py:38-54`) is the same
  (`cutoff=A-78*4h`, per-horizon `t+(h+1)*4h<cutoff`,
  `np.sort(tr.t.dt.floor("D").unique())`, `default_rng(m)`,
  `int(0.7*len(days))`, HGB params). ICs agree to 4dp, so the day samples,
  fits, and feature list (36) coincide.
- v122 y168: blind `y168=clip(log(o[t+169]/o[t+1])/(vol42*sqrt(168)),±4)`
  per asset, `cutoff=A-228*4h`, `t+169*4h<cutoff`, HGB(v92 params, seed 0)
  on the 26 v94 feats. Leader `add_y168` + train block
  (`v122_monthly_book.py:37-69`) is identical (`fwd[:n-1-168]=
  log(o[169:]/o[1:n-168])`, `EMB168=228`, `t+(168+1)*4h<cutoff`, same HGB,
  `f94` list). Train rows + ICs exact.
- Books/scales/engine: blind reuses audited OOS CSVs for the v115 legs
  (v92 LO, v94 LS, v103 LS) with inline audited `weights_lo`/`weights_ls`
  (ribbon gating, daily ffill) + 20%-cap-2 `vol_scale` (`W.shift(2)`,
  trailing 360/min-120, NaN→1); own scales for the bag/y168 legs on their
  panels. Portfolios use the v99/v104 convention
  (`realized=0.8*sum(books.shift(2)*ret1)+0.6*carry.shift(1)`,
  `s=min(0.15/vol,2)`) + v110 sequential engine (live [2021-09-24,
  2026-09-23), fee/slip per v92 SCEN, 0.00005 long funding,
  `|dc|*2*0.0004/1.2` carry cost), ungoverned. Leader calls the audited
  `weights_from`/`weights_ls`/`vol_target_scale`/`v110.run`/`summarize`
  directly on retrained panels. Bit-exact portfolios confirm identical
  books, scales, and wrapper timing (union `t>=first-v103-t`, opens = v103
  OOS, 10950 bars / 10944 live).

## C. Look-ahead audit

`v121/v121_bagged_v103.py` — no look-ahead found.
- Panel/embargo (`:40-45`): `p103.build()` (spot prefix before first USD-M
  bar only; flow features causal rolling on closed 4h bars) + per-horizon
  `t<cutoff` and `t+(h+1)*4h<cutoff` with `cutoff=A-78*4h`. Labels realized
  before the cutoff. Pass (see v103 audit).
- Bag (`:46-52`): day pool drawn only from the embargoed `tr`; subsample
  keeps whole days; same seed `m` across horizons only couples variance,
  not future info; HGB trains on `sub[feats]` (36 feats, no `y*`). Test
  rows `te` are the anchor year only. Pass.
- Books/scales/engine (`:76-87`): `weights_ls` (ribbon-gated, daily ffill),
  per-leg trailing 20%-cap-2 scales, union `>=p103.t.min()`, `v110`
  0.15-ungoverned with `p103` opens. Governor off (`mean_g=1`). Same lag
  as v110 audit. Pass.

`v122/v122_monthly_book.py` — no look-ahead found.
- Target (`:37-47`): `y168` uses `vol42[t]` (known at `t`) with future
  opens only in the label; clipped ±4 like other horizons. Pass.
- Train (`:62-69`): `cutoff=A-228*4h` (=168+60), rows need
  `t<cutoff`, `y168` not-NaN, and `t+169*4h<cutoff`, so
  `open[t+169]` is realized before the cutoff; `f94` excludes all `y*`.
  HGB seed 0, NaN-native. Pass.
- Books (`:73-86`): `weights_ls` LS + own `vol_target_scale(p92,W168)`
  (v114 panel); portfolio legs each own-scaled (`v92` scale for LO is the
  same formula as `v94` scale), union from first v103 `t`, opens = v103
  OOS, `v110` 0.15 ungoverned. No refit on test; costs/funding per
  AGENTS.md. Pass.
- No normalisation/threshold fitting on locked test; no forward-return
  peek outside embargoed training in either script.

## D. Manifest notes / verdict

- `v121/result_manifest.json`: track B, `rejected`, `live_approved:false`,
  audit pending. Primary monthly 2.447/worst 16.89/fills 10436/60mo and
  secondary 2.477/23.48 match blind; full-path DDs 16.89/18.38/20.57 match.
- `v122/result_manifest.json`: track C, `rejected`, `live_approved:false`,
  audit pending. Primary monthly 2.546/worst 16.58/fills 10539/60mo and
  secondary 1.979/23.96 match blind; full-path DDs 16.58/17.04/17.91 match.
- Blind replication is bit-exact on ICs, train rows, yearly nets/DDs/
  sharpes/fills, monthlies, worst-year and full-path DDs in all scenarios
  for both versions. No look-ahead in day-bag sampling, y168 labels/
  embargo, LS weights, vol targets, or v110 wrapper timing. Audit
  complete; leader files untouched.
