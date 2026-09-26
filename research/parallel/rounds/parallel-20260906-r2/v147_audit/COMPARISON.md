# v147 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v147_audit/` +
`tests/test_v147_audit.py` only. Base: v144 replication
(`v141_v142_audit` A2: v142 xs/xr books + v141 sequential governor + 10bps
1m execution). No leader files edited.

Blind protocol: `replication.json` (`replicate_v147.py`,
`tests/test_v147_audit.py` passing 3/3) was saved BEFORE opening `v147/`.
Pre-save reads were limited to the allowed base
(`v141_v142_audit/replicate_v141_v142.py` + `replication.json` +
`COMPARISON.md`, `v144/v144_deploy_v3.py` + `v144_result.json` for row
labels, `v103_v105_audit/` + `v113_v114_audit/` OOS CSVs, raw 4h/1d/
funding/spot/Coinbase/Bitstamp panels, carry, 1m intraday, `v103/`
target/embargo definition for the horizon formula; directory listing showed
`v147/` filenames only, no file contents). `v147/`
(`v147_v103_12h_horizon.py`, `v147_result.json`, manifest, logs) was first
opened after the Part A save. Part A imports no v147/v144/v142/v141/v135/
v133/v129/v125/v115/v114/v110/v104/v103/v92/v94 leader module (all formulas
inline from the assignment text + audited base replication + raw data +
carry).

Key maps: blind `rows.{gated_0.20,gated_0.25,ungoverned_0.15}` <->
leader `v147_result.json.{t20_governed,primary_t25_governed,reference_t15_ungoverned}`.
Thresholds per assignment: return diff > 1pp, DD diff > 0.5pp.

## A. Number comparison (blind vs leader)

### v147 rows — bit-exact

| row | blind monthly / fullDD | leader monthly / fullDD | diff |
|---|---|---|---|
| gated_0.20 (t20) | 2.908 / 18.40 | 2.908 / 18.40 | 0 / 0.00pp |
| gated_0.25 (primary) | 3.326 / 19.74 | 3.326 / 19.74 | 0 / 0.00pp |
| ungoverned_0.15 (ref) | 2.314 / 17.39 | 2.314 / 17.39 | 0 / 0.00pp |

Yearly nets/DDs/fills blind = leader in all 3 rows x 5 years (max abs net
diff 0.00pp, DD diff 0.00pp, fills diff 0):
t20: 15.04/18.40/2004, 32.96/10.76/2190, 73.77/12.71/2188,
51.41/11.30/2190, 38.77/12.04/2178;
t25: 15.52/19.74/2018, 36.76/11.79/2190, 91.64/14.67/2188,
60.44/12.40/2190, 46.60/14.34/2178;
ref: 15.38/15.66/2000, 23.57/8.36/2190, 52.10/10.04/2188,
39.23/9.03/2190, 30.67/9.14/2177.
Mean g blind (4dp) vs leader (3dp): max abs diff 0.0005
(e.g. t25 2021 0.8415 vs 0.842; t20 2022 0.9987 vs 0.999) — rounding only.
Ungoverned mean_g = 1.0 exactly both sides. Maker 0.635 all blind rows
(leader stores no maker field). No 1pp / 0.5pp threshold exceeded anywhere.

Reference check (leader-side): `reference_v144` t15/t20/t25
2.361/16.89, 2.955/18.28, 3.374/19.63 matches the audited `v144_result.json`
monthlies/fullDDs exactly. Blind v147 t25 3.326/19.74 vs v144 3.374/19.63:
-0.048pp/month at +0.11pp DD — the 12h-horizon delta is near-neutral,
consistent with the leader manifest note.

### v103 horizon extras (blind only, no leader counterpart)

Leader `v147_result.json` stores no ICs/train-rows. Blind reports the new
horizon diagnostics: `train_rows_h3/h6/h18` 33403/33388/33328 (2021) … 
77233/77218/77158 (2025); ordering h3 > h6 > h18 holds on all anchors
(shorter horizon keeps more rows under the `t+(h+1)*4h < cutoff` rule).
`ic_vs_y3/y6/y18`: 0.0508/0.0631/0.0463 (2021), 0.0256/0.0351/0.0670
(2022), 0.0393/0.0637/0.0896 (2023), 0.0237/0.0312/0.0537 (2024),
0.0400/0.0526/0.0986 (2025). v92/v94 ICs reproduce v144 bit-exact
(v92 0.0662/-0.0539/0.1148/0.1029/0.1425; v94 mean-vs-h42
0.1361/-0.0483/0.1157/0.1104/0.1552), confirming the only change is v103.
pvol anchors reproduce v129 bit-exact (v114 46120/…/89950 +
0.5275/…/0.6604; v103 33293/…/77123 + 0.5068/…/0.6650).
Feats 44/60, y3 excluded from all feature lists.

## B. Why blind matched

- Blind rebuilds v144 exactly as audited A2 (v114 extended panel
  Bitstamp>=2013-01-01 + Coinbase BTC, Coinbase ETH, spot_2017 prefix +
  v103 base + flow, 26/36 feats, pvol v129 method cutoff-102*4h t+44*4h
  < cutoff exp(pred) left-join replace; LO/LS weights N=5 rib gating,
  tranche mean/6, own 0.20-cap-2 scales, books 0.25/0.25/0.5) then the v141
  wrapper (sequential governor j=i-2, 540-bar peak incl pre-start 1,
  clip((0.20-DD)/0.10,0,1), scenario/row-specific sequential equity,
  g=1 i<2 + ungoverned; v135 10bps execution T=t+4h, p0 minute-0, lo/hi
  min/max offsets 2..14, p15 minute-15, strict </>, maker 0.0002 rel
  -/+0.0010 else taker 0.0005 rel p15/p0-1 +/-0.0002, missing p0 taker
  +/-0.0002; cost=|dW|*fee+dW*rel, net=w*r_next-cost-0.00005*long+c*carry-
  carrycost, E*=1+net, live [2021-09-24,+1825d)).
- v103 delta exactly per assignment: generic `y{h}` loop extended to
  (3,6,18,42,84) so `y3 = clip(log(o[i+4]/o[i+1])/(vol42*sqrt(3)),-4,4)`
  = `clip(log(open[t+4]/open[t+1])/(vol42*sqrt(3)),-4,4)`; per-horizon row
  filter `t+(h+1)*4h < cutoff` gives `t+4*4h < cutoff` for h=3;
  prediction = mean of the three HGBs; embargo 78 unchanged
  (= max(18)+60, still covers the longest horizon); y3 excluded from all
  feature lists (pvol + direction). v92/v94 code, xs/xr sets
  (v114 9 cols, v103 9+3 cols, groupby-t mean + rank(pct=True)), HGB
  params, tranching, scales, governor timing, and 1m grouping all
  unchanged. Bit-exact monthlies/yearlies/DDs/fills/mean-g confirm
  identical panels, embargoes, feature sets, books, vol/s per target,
  governor timing, limit/fee/rel, and cost accounting.

## C. Look-ahead audit

### `v147/v147_v103_12h_horizon.py` — no look-ahead found

- Wrapper only (37 lines): sets `v144.v103.HS = (3, 6, 18)`, asserts
  `v144.v103.EMBARGO == 78`, then calls audited `v144.books_v142()` +
  `v144.simulate()`. No data touched, no threshold fitting. Pass.
- Target definition (inherited `v103/v103_flow_short_horizon.py`
  :77-80, :92-94): `y{h} = clip(log(o[1+h:]/o[1:n-h])/(vol42*sqrt(h)),-4,4)`
  uses only open[t+1+h]/open[t+1] and trailing vol42 at t; h=3 uses no new
  data beyond what h=6/18 already use. Train filter
  `t+(h+1)*4h < cutoff` drops rows whose forward window crosses the
  embargo cutoff; test year never fit. `EMBARGO = max(HS)+10*PD` = 78
  before and after (max HS stays 18), so the unchanged 78 still satisfies
  the longest horizon + 60-bar buffer. Pass (see v103 + v141_v142 audits).
- Features/embargoes: FEATS exclude `y*`/t/open/sym/bar (blind excludes
  y3 explicitly; leader `build()` excludes `not c.startswith("y")` which
  covers y3 automatically once HS adds it). xs/xr groupby-t over majors
  present at the same bar t (already-causal values, simultaneous closes).
  pvol on original sets, swap fillna causal. Pass.
- Execution/governor/net: unchanged audited v141 path (execution-bar T
  data onto decision t strictly post-decision; governor j=i-2 540-bar
  peak with the same 2-bar lag as v110; costs/funding/carry per
  AGENTS.md). Pass.
- Selection caveat (not look-ahead): 0.25 target remains the ex-post
  frontier pick (rule 5: once inspected, interval is research data); costs/
  funding per AGENTS.md. Manifest marks `rejected`, `live_approved:false`.

## D. Post-hoc corrections / protocol log

- No spec reinterpretation after opening `v147/`. Part A script and
  `replication.json` frozen pre-open; tests pass 3/3 pre- and post-open.
- No post-open code fix: blind monthlies/yearlies/DDs/fills already match
  the leader bit-exact; mean-g diffs are rounding only (blind 4dp vs
  leader 3dp, max 0.0005).
- Blind extras with no numeric impact: v103 `ic_vs_y3/y6/y18`,
  `train_rows_h3/h6/h18`, `feats114x/feats103x` lists, `n_replaced`, pvol
  anchors, monthly/maker/orders/fills per row.

## E. Manifest notes / verdict

- `v147/result_manifest.json`: track A, `rejected`, `live_approved:false`,
  audit pending. Single realistic 1m scenario repeated in 3 slots;
  primary t25 3.326/19.74, t20 2.908/18.40, ref 2.314/17.39 matches blind
  bit-exact. Note "12h horizon neutral: 3.326/19.74 vs v144 3.374/19.63"
  matches the numbers (t25 -0.048pp/month at +0.11pp DD; t20 -0.047pp at
  +0.12pp; ref -0.047pp at +0.50pp).
- Blind replication is bit-exact on all rows/yearlies/mean-g/fills/DDs.
  No look-ahead in the y3 target timing, per-horizon embargo filter,
  unchanged 78-bar embargo, xs/xr timing, pvol exclusion, tranching,
  scales, governor timing, or 1m fill/cost paths. Audit complete; leader
  files untouched.

## Files

- `replication.json` (Part A, blind), `replicate_v147.py`,
  `tests/test_v147_audit.py` pass 3/3.
