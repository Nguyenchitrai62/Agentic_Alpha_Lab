# v146 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v146_audit/` +
`tests/test_v146_audit.py` only. Base: audited v141_v142 replication
(its A2 = v144: v142 books + v141 engine) and v138_v139 (positioning
features). No leader files edited.

Blind protocol: `replication.json` (`replicate_v146.py`,
`tests/test_v146_audit.py` passing 3/3) was saved BEFORE opening `v146/`.
Pre-save reads were limited to the allowed base (`v141_v142_audit/` +
`v138_v139_audit/` replications + COMPARISONs, `v129_v131_audit/` pvol rows,
`v113_v114_audit/` + `v103_v105_audit/` OOS CSVs, raw 4h/1d/funding/spot/
Coinbase/Bitstamp panels, carry, 1m intraday, `um_metrics_20260926/`;
directory listing showed `v146/` filenames only, no file contents).
`v146/` (`v146_relative_positioning.py`, `v146_result.json`, manifest, logs)
was first opened after the Part A save. Part A imports no
v146/v144/v142/v141/v139/v138/v133/v129/v125/v115/v114/v110/v104/v103/v92/v94
leader module (all formulas inline from the assignment text + audited
replication code + raw data + carry + metrics + 1m intraday).

Key maps: blind `rows.{gated_0.20,gated_0.25,ungoverned_0.15}` <->
leader `v146_result.json.{t20_governed,primary_t25_governed,reference_t15_ungoverned}`;
blind `positioning.relative_columns` <-> leader `added_columns`;
blind `anchors_v92[].ic` runs the same v114 leg as v144/v142.
Thresholds per assignment: return diff > 1pp, DD diff > 0.5pp.

## A. Number comparison (blind vs leader)

Bit-exact on every row, yearly, monthly, DD, fills, and mean_g bucket:

| row | blind monthly / fullDD | leader monthly / fullDD | diff |
|---|---|---|---|
| gated_0.20 (t20) | 2.200 / 23.24 | 2.200 / 23.24 | 0 / 0.00pp |
| gated_0.25 (primary) | 2.516 / 25.25 | 2.516 / 25.25 | 0 / 0.00pp |
| ungoverned_0.15 (ref) | 1.905 / 20.08 | 1.905 / 20.08 | 0 / 0.00pp |

Yearly nets/DDs/fills blind = leader in all 3 rows x 5 years
(max abs net diff 0.00pp, DD diff 0.00pp, fills diff 0):
t15: 19.11/15.80/2013, 5.73/15.22/2190, 50.03/10.57/2189,
40.59/9.86/2190, 16.77/15.96/2166;
t20: 19.33/18.28/2014, 6.37/16.91/2190, 66.18/13.09/2188,
50.53/13.45/2190, 16.21/22.63/2169;
t25: 20.13/19.63/2034, 5.91/18.26/2189, 79.29/14.98/2188,
59.20/15.39/2190, 22.32/25.25/2170.
Mean g blind (4dp) vs leader (3dp): max abs diff 0.0005
(e.g. t20 2022 0.9675 vs 0.968; t25 2025 0.9088 vs 0.909) — rounding only.
Ungoverned mean_g = 1.0 exactly both sides. Maker 0.636 all rows
(verified blind; leader stores no maker field).
No 1pp / 0.5pp threshold exceeded anywhere.

Context (not a blind error): v146 underperforms its v144 reference on
every row — t15 1.905/20.08 vs 2.361/16.89, t20 2.200/23.24 vs
2.955/18.28, t25 2.516/25.25 vs 3.374/19.63. The 2022 year collapses
(t25 5.91 vs v144 t25 42.05) and the hidden 2025 year drops
(22.32 vs 41.27) while full-path DD widens to 25.25. Matches the manifest
note ("relative positioning features hurt 2022 and the hidden year").

## B. Why blind matched

- v144 base: blind copies the audited v141_v142 A2 pipeline line-for-line
  (v114-extended panel Bitstamp>=2013-01-01 + Coinbase BTC/ETH +
  spot_2017 prefix + v103 base + flow; pvol v129 method cutoff-102*4h
  t+44*4h<cutoff exp(pred) left-join replace — train rows/spearmans match
  v129 bit-exact 46120/../89950 + 0.5275/../0.6604 and 33293/../77123 +
  0.5068/../0.6650; LO/LS weights N=5 rib rules, tranche mean/6, own
  0.20-cap-2 scales, books 0.25/0.25/0.5; v110 governor j=i-2, 540-bar peak,
  clip((0.20-DD)/0.10,0,1), sequential scenario/row-specific equity; v135
  10bps execution T=t+4h p0/lo/hi/p15, strict </>, maker 0.0002 rel
  -/+0.0010 else taker 0.0005 rel p15/p0-1 +/-0.0002, missing p0 taker).
  v92/v94 ICs reproduce v142/v144 exactly
  (0.0662/-0.0539/0.1148/0.1029/0.1425 and
  0.1361/-0.0483/0.1157/0.1104/0.1552), confirming the v114 leg is untouched.
- Positioning: blind rebuilds the 5-column v139 subset with the audited
  formula (`target = t+4h-5min`, merge_asof backward tolerance 4h per asset,
  log-where->0, diff(6/42), z=(s-roll180mean_min90)/roll180std_min90 ddof=1,
  taker roll6mean_min3, per-asset time order) — identical to leader
  `v139.pos_features` (`v139_positioning.py:37-52`, key `t+4h-5min`, same
  logs/diffs/rollings). Blind bare names (`oi_chg6`, `oi_chg42`,
  `top_ls_z`, `crowd_ls_z`, `taker_ls6`) equal leader `REL` tuple verbatim;
  the `pos_` prefix of the v138_v139 audit replication is cosmetic only.
  Blind 5-col full coverage 44440/88818 vs audited 8-col 44430/88818
  (+10 rows, expected: fewer simultaneous-NaN constraints).
- Relative step: blind `xs_c=c-mean_t(c)`, `xr_c=rank(pct=True)` per t over
  5 majors for the five positioning cols matches leader `books()` lines
  56-59 (`q[c]-g.transform("mean")`, `g.rank(pct=True)`, default average
  method) — per-column independence makes the blind single-pass
  `add_xs_xr(panel103p, BASE+FLOWX+POS_RAW)` identical to the leader's
  two-pass order (REL first, then `v142.add_xs(q, BASE+FLOWX)`).
  The five raw columns are dropped before the model on both sides
  (blind `drop(columns=POS_RAW)`, leader `q.drop(columns=list(REL))`), so
  only the 10 relative columns enter: blind `feats103x_n=70`
  (36+24+10) and leader `added_columns` lists exactly those 10
  (`xs_/xr_` for the five). v103 pvol uses the original 36 v103 features
  on both sides (`f103_base` / `feats103`).
- Engine: leader `v144.simulate` (governor + 10bps rows 0.15/0.20/0.25) is
  the audited v141 wrapper; blind `run_rows` is the same code path that
  reproduced v144 bit-exact in the v141_v142 audit. Bit-exact
  monthlies/yearlies/DDs/fills/mean-g confirm identical panels, xs/xr
  timing, embargoes, feature sets (v114 44, v103 70), pvol exclusion,
  tranching, scales, governor timing, and 1m grouping/cost accounting.

## C. Look-ahead audit

### `v146/v146_relative_positioning.py` — no look-ahead found

- Positioning source (:54): `v139.pos_features(g.sort_values("t"), s)`
  per sym — the audited causal join (key = `t+4h-5min` = bar close − 5min;
  metrics are 5-min rows so the joined row, e.g. 03:55 for a 04:00 close,
  is available before the close; backward-only, tolerance 4h → gaps NaN,
  no forward fill). Pass (see v138_v139 audit §C).
- Logs/diffs/rollings: inside `pos_features` — `log(where>0)` else NaN,
  `diff(6/42)`, `rolling(180,min90)` z, `rolling(6,min3)` mean, all in
  `t` order per asset. Only past/current rows of the joined series. Pass.
- Relative step (:56-60): groupby-`t` mean + `rank(pct=True)` over majors
  present at the same bar `t`, on already-causal values; no future-`t` row
  enters (same as the v142 `add_xs` audit). Rank default average; NaNs
  propagate. Raw `REL` dropped (:60) before `f103` (:62) is built, so no
  absolute positioning leaks into the model. Pass.
- Panels/models (:44-64): v114 leg = v142 verbatim (`BASE`, `add_xs`,
  `FEATS` excl y/t/open/sym/bar; v94 also excl `y*`); v103 `f103` = all
  non-target cols after the drop (base + 24 xs/xr + 10 relative = 70);
  same anchors/embargoes/targets/HGB params as v144; test rows reporting
  only. Pass.
- pvol (:65-66): `vol_predict` on `f92_base` / `f103_base` (original sets,
  positioning and xs excluded) with `swap` fillna — audited causal sizing.
  Pass.
- Books/portfolio (:73-80, via `v144.simulate`): same tranched books
  (past-only `phased`, causal `vol_target_scale`, 0.25/0.25/0.5,
  `idx>=p103.t.min()`), 2-bar-lag returns, trailing 360/min-120 vol,
  per-target s cap 2, governor j=i-2 on scenario equity, 10bps 1m fill/cost
  on execution bar T=t+4h strictly post-decision. Pass (see v141_v142
  audit §C).
- `rel_cols.extend(c for c in f103 if c.endswith(REL))` (:63) runs after
  features are fixed and only collects the 10 `xs_/xr_` names for the
  result manifest — no data effect. Pass.
- No normalisation/threshold fitting on locked test beyond the disclosed
  ex-post target frontier (0.25 primary); costs/funding per AGENTS.md.

## D. Post-hoc corrections / protocol log

- No spec reinterpretation after opening `v146/`. Part A script and
  `replication.json` frozen pre-open; tests pass 3/3 pre- and post-open.
- One pre-open blind choice logged here (not a post-open fix): raw
  positioning columns use the assignment's bare names
  (`oi_chg6/oi_chg42/top_ls_z/crowd_ls_z/taker_ls6`); leader `REL` uses the
  identical bare tuple (the `pos_` prefix exists only in the v138_v139
  audit replication). `xs_/xr_` names, drop-before-model, and pvol
  exclusion are identical on both sides — confirmed bit-exact.
- Blind extras with no numeric impact: pvol anchors, maker rate,
  orders/fills, `ic_vs_y18`, per-asset positioning coverage, full
  `feats114x/feats103x` lists; leader rounds mean_g to 3dp (blind 4dp,
  max diff 0.0005).

## E. Manifest notes / verdict

- `v146/result_manifest.json`: track B, `rejected`, `live_approved:false`,
  audit pending. Single realistic 1m scenario repeated in 3 slots;
  primary t25 2.516/25.25, t20 2.200/23.24, ref 1.905/20.08 matches blind
  bit-exact. Rejection rationale matches the numbers (relative positioning
  degrades return and widens DD vs v144 3.374/19.63 on every row).
- Blind replication is bit-exact on all rows/yearlies/mean-g/fills/DDs and
  on the v114 ICs; v103 ICs move with the new features as expected
  (e.g. 2023 y6 0.0800 vs v142 0.0661, y18 0.1253 vs 0.1010; 2025 y6
  0.0494 vs 0.0563). No look-ahead in the metrics join, POS warmup, xs/xr
  timing, raw-drop, pvol exclusion, tranching, scales, governor, or 1m
  fill/cost paths. Audit complete; leader files untouched.

## Files

- `replication.json` (Part A, blind), `replicate_v146.py`,
  `tests/test_v146_audit.py` pass 3/3.
