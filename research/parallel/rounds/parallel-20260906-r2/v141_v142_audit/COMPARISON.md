# v141 + v142 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v141_v142_audit/` +
`tests/test_v141_v142_audit.py` only. Base: audited v133, v135 (1m bar
stats, 10 bps rule), v110 (governor) replications. No leader files edited.

Blind protocol: `replication.json` (`replicate_v141_v142.py`,
`tests/test_v141_v142_audit.py` passing 3/3) was saved BEFORE opening
`v141/` or `v142/`. Pre-save reads were limited to the allowed base
(`v132_v133_audit/`, `v135_audit/`, `v110_audit/` replications + COMPARISONs,
`v129_v131_audit/` pvol rows, `v113_v114_audit/` + `v103_v105_audit/` OOS
CSVs, raw 4h/1d/funding/spot/Coinbase/Bitstamp panels, carry, 1m intraday;
directory listing showed `v141/`/`v142/` filenames only, no file contents).
`v141/` (`v141_governed_realistic.py`, `v141_result.json`, manifest, logs)
and `v142/` (`v142_cross_sectional_features.py`, `v142_result.json`,
manifest, logs) were first opened after the Part A save. Part A imports no
v141/v142/v135/v133/v129/v125/v115/v114/v110/v104/v103/v92/v94 leader module
(all formulas inline from the assignment text + audited OOS CSVs + raw data
+ carry + audited panel code).

Key maps: blind `v141.rows.{gated_0.20,gated_0.25,ungoverned_0.15}` <->
leader `v141_result.json.{t20_governed,primary_t25_governed,reference_t15_ungoverned}`;
blind `v142.anchors_v92[].ic` <-> leader `ic[anchor].v92`;
blind `v142.anchors_v103[].ic_vs_y6` <-> leader `ic[anchor].v103_y6`;
blind `v142.rows` (governor+10bps, pre-open documented choice) vs leader
`primary_scenarios.{normal,fee_stress,execution_stress}` (v133 pipeline:
0.15 ungoverned, fee scenarios — see B).
Thresholds per assignment: IC diff > 0.01, return diff > 1pp, DD diff > 0.5pp.

## A. Number comparison (blind vs leader)

### v141 (governor + 10bps) — bit-exact

| row | blind monthly / fullDD | leader monthly / fullDD | diff |
|---|---|---|---|
| gated_0.20 (t20) | 2.695 / 18.90 | 2.695 / 18.90 | 0 / 0.00pp |
| gated_0.25 (primary) | 3.021 / 19.59 | 3.021 / 19.59 | 0 / 0.00pp |
| ungoverned_0.15 (ref) | 2.258 / 16.25 | 2.258 / 16.25 | 0 / 0.00pp |

Yearly nets/DDs/fills blind = leader in all 3 rows x 5 years (max abs net
diff 0.00pp, DD diff 0.00pp, fills diff 0):
t20: 16.08/17.36/2083, 16.94/14.31/2190, 66.21/10.60/2190,
54.53/13.27/2189, 41.45/12.88/2157;
t25: 15.16/18.17/2086, 18.54/15.44/2190, 80.95/12.76/2190,
63.45/14.54/2189, 47.74/17.10/2160;
ref: 20.99/14.52/2085, 14.06/11.09/2190, 46.54/8.03/2190,
43.13/10.03/2189, 31.94/9.69/2156.
Mean g blind (4dp) vs leader (3dp): max abs diff 0.0008
(e.g. t20 2022 0.9801 vs 0.98; t25 2021 0.8629 vs 0.863) — rounding only.
Ungoverned mean_g = 1.0 exactly both sides. Maker 0.639 all v141 rows
both sides (verified in blind; leader stores no maker field).
No 1pp / 0.5pp threshold exceeded anywhere in v141.

Note: v141 ref (20.99/14.06/46.54/43.13/31.94, monthly 2.258) differs from
the audited v135 10bps row (21.04/14.06/46.54/43.13/30.51, monthly 2.241)
by -0.05pp (2021) and +1.43pp (2025, fills 2156 vs 2161). Leader docstring
says the 0.15 reference is the v137 row, not v135 — the blind-vs-leader
comparison above is exact regardless.

### v142 ICs — bit-exact

| anchor | blind v92 | leader v92 | blind v103_y6 | leader v103_y6 |
|---|---|---|---|---|
| 2021-09-24 | 0.0662 | 0.0662 | 0.0665 | 0.0665 |
| 2022-09-24 | -0.0539 | -0.0539 | 0.0389 | 0.0389 |
| 2023-09-24 | 0.1148 | 0.1148 | 0.0661 | 0.0661 |
| 2024-09-24 | 0.1029 | 0.1029 | 0.0267 | 0.0267 |
| 2025-09-24 | 0.1425 | 0.1425 | 0.0563 | 0.0563 |

Max abs IC diff 0.0 (threshold 0.01). Blind extras `ic_vs_y18`
(0.0539/0.0726/0.1010/0.0473/0.1086) have no leader counterpart (leader
reports y6 only). No IC threshold exceeded.

### v142 scenarios — DIVERGE by documented wrapper mismatch (explained)

Blind pre-open choice (frozen in `replication.json` meta): A2 uses the same
governor + 10bps execution rows as A1. Leader v142 docstring/code uses the
v133 pipeline: 0.15 ungoverned, three fee scenarios, NO governor, NO 1m
execution (`v110.run(p103, books, 0.15, False, fee, slip)`).
Leader: normal 2.551/16.26, fee 2.330/17.15, exec 2.055/18.26
(yearlys e.g. normal 21.08/15.53/2013, 28.88/7.71/2190, 53.59/10.16/2188,
44.18/8.33/2190, 31.18/9.01/2177; reference_v133 2.44/2.222/1.95 matches
the audited v133 numbers).
Blind (governor+10bps): gated_0.20 2.955/18.28, gated_0.25 3.374/19.63,
ungoverned_0.15 2.361/16.89.
Return/DD diffs vs leader exceed 1pp/0.5pp on every row/scenario pair —
this is the wrapper difference, NOT a feature error: ICs match bit-exact
(panels/features/embargoes correct), pvol reuses the original sets on both
sides, and v141 bit-exact confirms the books/governor/10bps engine. The
leader's v133-pipeline choice is literal per "v133 pipeline otherwise";
the blind A2 applied the A1 wrapper instead. See B/C.

## B. Why blind matched / diverged

- v141: blind rebuilds v133 books exactly as v135 (v114 extended panel
  Bitstamp>=2013-01-01 + Coinbase BTC, Coinbase ETH, spot_2017 prefix +
  v103 base + flow, 26/36 feats, pvol v129 method cutoff-102*4h t+44*4h
  < cutoff exp(pred) left-join replace — train rows/spearmans match v129
  bit-exact 46120/../89950 + 0.5275/../0.6604 and 33293/../77123 +
  0.5068/../0.6650 — LO/LS weights N=5 rib != -1/!= 1, tranche mean/6,
  own 0.20-cap-2 scales, books 0.25/0.25/0.5) then the v110 governor
  (j=i-2, 540-bar peak incl pre-start 1, clip((0.20-DD)/0.10,0,1),
  scenario/row-specific sequential equity, g=1 i<2 + ungoverned) with the
  v135 10bps execution (T=t+4h, p0 minute-0, lo/hi min/max offsets 2..14,
  p15 minute-15, strict </>, maker fee 0.0002 rel -/+0.0010 else taker
  0.0005 rel p15/p0-1 +/-0.0002, missing p0 taker +/-0.0002,
  cost=|dW|*fee+dW*rel, net=w*r_next-cost-0.00005*long+c*carry-carrycost,
  E*=1+net, live [2021-09-24,+1825d)). Bit-exact monthlies/yearlies/DDs/
  fills/mean-g confirm identical books, vol/s per target, governor timing,
  1m grouping, limit/fee/rel, and cost accounting.
- v142 features: blind `xs_c=c-mean_t(c)`, `xr_c=rank(pct=True)` per t over
  5 majors for the exact 9 v114 cols + 9+3 v103 cols matches leader
  `add_xs` line-for-line (same col tuples incl `tbr_6/flow_42/tbr_z`, same
  groupby-t mean + `rank(pct=True)` default average method). v92/v94 models
  on all columns (v114 26+18=44 feats), v103 on all columns (36+24=60),
  same HGB params/embargoes (v92 h42/102, v94 h18/42/84/144, v103 h6/h18/
  78), pvol on original sets both sides. Bit-exact v92/v103_y6 ICs confirm
  identical panels, xs/xr timing, embargoes, and feature sets.
- v142 wrapper divergence root cause: assignment A2 text ends "v133
  pipeline otherwise". Leader implements v133's own pipeline (0.15
  ungoverned `v110.run/summarize` x3 fee scenarios). Blind implemented A1's
  wrapper (governor rows + 10bps) for A2 as documented pre-open. Hence ICs
  exact but scenario returns/DDs incomparable by construction.

## C. Look-ahead audit

### `v141/v141_governed_realistic.py` — no look-ahead found

- Chain (:24-28): reuses audited `v135` module chain
  (`v129/v125/v115/v103/v110/v104/v99`); no data touched. Pass.
- Panels/training (:34-45): v114-extended + v103-base builds with audited
  `train_predict` per anchor; FEATS exclude y/t/open/sym/bar (v92) and
  y* (v94/v103); test year never fit. Pass (see v113/v114 + v103 audits).
- pvol (:46-52): `vol_predict` on base panels with `EMBARGO_BARS`, `swap`
  pvol.fillna(vol42) on (t,sym) — audited causal sizing. Pass.
- Tranching/books (:54-62): `v125.phased(raw, 0..5)` past-only schedules;
  causal `vol_target_scale`; books 0.25/0.25/0.5; `idx>=p103.t.min()`. Pass.
- Vol/s (:65-66, :85): books.shift(2), carry.shift(1), trailing 360/min-120,
  NaN->1, cap 2, per-target s. Pass.
- Execution (:71-81): `bar_stats(s).reindex(idx+4h).set_axis(idx)` puts
  execution-bar T data onto decision t; window [T+2m,T+14m] + fallback
  T+15m strictly post-decision/post-T-open, affects only fill cost at t.
  Strict </>, p15:=p0, missing->taker +/-0.0002 match spec; D=0.0010. Pass.
- Governor (:90-93): j=i-2, peak=max(eq[j-539..j]) (90*PD=540), DD from
  eq[j] which embeds net[j] with forward leg o[j+2]/o[j+1]-1 =
  o[i]/o[i-1]-1 known at open of bar i, before the close-i decision. Same
  2-bar lag as v110 audit. Peak uses only eq[..j]. Pass.
- Net/E/live (:94-101): w/c contemporaneous, costs/funding/carry
  current+previous only, calendar live mask, E*=1+net. Pass.
- Selection caveat (not look-ahead): docstring "Reporting frontier: target
  choice is ex post" + manifest note — the 0.25 target is picked on seen
  OOS years (rule 5: once inspected, interval is research data). Only the
  hidden-year direction (+47.74% t25 vs +31.94% ref in 2025) is prospective.
  No normalisation/threshold fitting on locked test beyond this disclosed
  frontier. Costs/funding per AGENTS.md.

### `v142/v142_cross_sectional_features.py` — no look-ahead found

- `add_xs` (:33-39): groupby-t mean + rank(pct=True) over majors present at
  the same bar t. All inputs are already-causal feature values at t (bars
  close simultaneously); no future-t row enters. Rank default average
  method; NaNs propagate (no fill). Pass.
- Panels/models (:43-66): v114-extended + v103-base, xs/xr appended,
  FEATS = all non-target cols (v92 excludes y/t/open/sym/bar; v94/v103
  also exclude y*), same anchors/embargoes/targets as v133; test rows
  reporting only (ICs). Pass.
- pvol (:67-68): `vol_predict` on `p92/f92_base` + `p103/f103_base`
  (original sets, xs excluded) per spec. `swap` fillna causal. Pass.
- Books/portfolio (:70-87): same tranched/books/scales as v133;
  `v110.run(p103, books, 0.15, False, fee, slip)` target 0.15 ungoverned
  2-bar lag x3 scenarios; forward return is execution accounting. Pass.
- Differs from v102 (market-neutral book) per docstring — here relative
  features inform directional models only; no LS construction change. No
  threshold tuning on locked test; costs/funding per AGENTS.md. Pass.

## D. Post-hoc corrections / protocol log

- No spec reinterpretation after opening `v141/`/`v142/`. Part A script and
  `replication.json` frozen pre-open; tests pass 3/3 pre- and post-open.
- One documented pre-open blind choice (not a post-open fix): A2 applied
  the A1 governor+10bps wrapper ("same governor+10bps rows as A1" in
  `replication.json` meta) while the leader implements the literal v133
  pipeline for v142 (0.15 ungoverned fee scenarios). ICs still match
  bit-exact; scenario diffs are wrapper-only (see A/B).
- Blind extras with no numeric impact: v142 `ic_vs_y18`, `feats114x/
  feats103x` lists, `n_replaced`, pvol anchors, monthly/maker/orders/fills
  per row; leader rounds mean_g to 3dp (blind 4dp, max diff 0.0008).
- Leader v141 `reference_t15_ungoverned` yearly 2021 net 20.99 (vs v135
  10bps 21.04) and 2025 net 31.94 / fills 2156 (vs 30.51 / 2161) — blind
  reproduces the leader exactly; the v135 gap is leader-side (docstring:
  reference = v137 row), not a blind error.

## E. Manifest notes / verdict

- `v141/result_manifest.json`: track B, `rejected`, `live_approved:false`,
  audit pending. Single realistic 1m scenario repeated in 3 slots;
  primary t25 3.021/19.59, t20 2.695/18.90, ref 2.258/16.25 matches blind
  bit-exact. Ex-post-target note matches the numbers (t25 > t20 > ref on
  monthly; full-path DD 19.59 > 18.90 > 16.25).
- `v142/result_manifest.json`: track C, `rejected`, `live_approved:false`,
  audit pending. primary_scenarios 2.551/15.53, 2.330/16.02, 2.055/16.64
  (full-path 16.26/17.15/18.26) vs reference_v133 2.44/2.222/1.95 — xs/xr
  lifts normal +0.111pp/month at DD 16.26 vs 15.18 (v133 audited) with
  yearly mix 21.08/28.88/53.59/44.18/31.18. Blind ICs match bit-exact;
  blind scenario rows are the documented alternate wrapper, not the
  leader's v133 pipeline.
- Blind replication is bit-exact on all v141 rows/yearlies/mean-g/fills/DDs
  and all v142 ICs. No look-ahead in xs/xr timing, pvol exclusion,
  tranching, scales, governor timing, or 1m fill/cost paths. Audit complete;
  leader files untouched.

## Files

- `replication.json` (Part A, blind), `replicate_v141_v142.py`,
  `tests/test_v141_v142_audit.py` pass 3/3.
