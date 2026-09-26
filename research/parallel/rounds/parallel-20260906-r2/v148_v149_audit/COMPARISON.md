# v148 + v149 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v148_v149_audit/` +
`tests/test_v148_v149_audit.py` only. Base: your v144 replication
(`v141_v142_audit` A2: v142 xs/xr books + v141 sequential governor + 10bps
1m execution; `v146_audit` / `v147_audit` replications + COMPARISONs as
cross-checks). No leader files edited.

Blind protocol: `replication.json` (`replicate_v148_v149.py`,
`tests/test_v148_v149_audit.py` passing 3/3) was saved BEFORE opening
`v148/` or `v149/`. Pre-save reads were limited to the allowed base
(`v141_v142_audit/`, `v146_audit/`, `v147_audit/` replications +
COMPARISONs, `v129_v131_audit/` pvol rows, `v113_v114_audit/` +
`v103_v105_audit/` OOS CSVs, raw 4h/1d/funding/spot/Coinbase/Bitstamp
panels, carry, 1m intraday; directory listing showed `v148/`/`v149/`
filenames only, no file contents). `v148/`
(`v148_robustness_bootstrap.py`, `v148_result.json`, manifest, logs) and
`v149/` (`v149_xs_vol_forecast.py`, `v149_result.json`, manifest, logs)
were first opened after the Part A save. Part A imports no
v148/v149/v144/v142/v141/v135/v133/v129/v125/v115/v114/v110/v104/v103/v92/v94
leader module (all formulas inline from the assignment text + audited
replication code + raw data + carry + 1m intraday).

Key maps: blind `v144.rows.{gated_0.20,gated_0.25,ungoverned_0.15}` <->
leader `reference_v144.{t20,t25,t15}` (= `v148_result.json` realised legs);
blind `v148.{row}.bootstrap` <-> leader
`v148_result.json.rows.{t20_governed,primary_t25_governed,reference_t15_ungoverned}.bootstrap`
(`return_pct_quantiles` <-> `ret_quantiles_pct_5_25_50_75_95`,
`maxdd_pct_quantiles` <-> `dd_quantiles_pct_5_25_50_75_95`,
`p_dd_gt_20`/`p_loss`/`p_monthly_ge_5` <->
`p_maxdd_gt_20`/`p_return_lt_0`/`p_monthly_ge_5pct`);
blind `v149.rows.{gated_0.20,gated_0.25,ungoverned_0.15}` <->
leader `v149_result.json.{t20_governed,primary_t25_governed,reference_t15_ungoverned}`.
Thresholds per assignment: return diff > 1pp, DD diff > 0.5pp,
probability diff > 0.02.

## A. Number comparison (blind vs leader)

### v148 bootstrap — bit-exact quantiles, rounding-only probs

| row | blind ret q5/25/50/75/95 | leader ret q | blind DD q | leader DD q |
|---|---|---|---|---|
| gated_0.20 (t20) | -5.08/17.39/38.76/65.71/122.63 | same, diff 0 | 7.80/10.92/13.28/16.80/23.98 | same, diff 0 |
| gated_0.25 (primary) | -6.33/19.23/45.09/78.41/151.45 | same, diff 0 | 9.26/12.61/15.04/18.72/26.37 | same, diff 0 |
| ungoverned_0.15 (ref) | -4.10/13.96/30.26/50.01/88.50 | same, diff 0 | 6.14/8.77/10.64/14.30/20.27 | same, diff 0 |

Probs blind (4dp) vs leader (3dp) — rounding only, max abs diff 0.0004
(threshold 0.02):
t20: pDD 0.1166 vs 0.117, pNeg 0.0802 vs 0.080, pM5 0.1700 vs 0.170;
t25: pDD 0.1918 vs 0.192, pNeg 0.0850 vs 0.085, pM5 0.2448 vs 0.245;
ref: pDD 0.0540 vs 0.054, pNeg 0.0838 vs 0.084, pM5 0.0722 vs 0.072.
Realised legs blind = leader on all 3 rows (t20 2.955/18.28,
t25 3.374/19.63, ref 2.361/16.89 — the v144 reference values).
No 1pp / 0.5pp / 0.02 threshold exceeded anywhere in v148.

### v149 rows — bit-exact

| row | blind monthly / fullDD | leader monthly / fullDD | diff |
|---|---|---|---|
| gated_0.20 (t20) | 2.955 / 18.31 | 2.955 / 18.31 | 0 / 0.00pp |
| gated_0.25 (primary) | 3.365 / 19.65 | 3.365 / 19.65 | 0 / 0.00pp |
| ungoverned_0.15 (ref) | 2.369 / 16.79 | 2.369 / 16.79 | 0 / 0.00pp |

Yearly nets/DDs/fills blind = leader in all 3 rows x 5 years (max abs
net diff 0.00pp, DD diff 0.00pp, fills diff 0):
t20: 19.51/18.31/2014, 38.84/10.76/2190, 69.91/13.21/2188,
51.20/11.90/2190, 34.60/11.88/2178;
t25: 20.36/19.65/2034, 43.71/11.87/2190, 87.78/15.13/2188,
59.00/12.92/2190, 41.02/14.49/2178;
ref: 19.21/15.84/2014, 27.74/8.06/2190, 50.19/10.60/2188,
39.45/9.39/2190, 27.78/9.02/2177.
Mean g blind (4dp) vs leader (3dp): max abs diff 0.0004
(e.g. t20 2022 0.9991 vs 0.999; t25 2021 0.8416 vs 0.842) — rounding
only. Ungoverned mean_g = 1.0 exactly both sides. Maker ~0.634-0.635
all blind rows (leader stores no maker field).
Leader `reference_v144` t15/t20/t25 2.361/16.89, 2.955/18.28,
3.374/19.63 matches the blind v144 base exactly (see below).
No 1pp / 0.5pp threshold exceeded anywhere in v149.

### v144 base check (blind, pre-open)

Blind v144 reproduces the audited `v141_v142_audit` A2 reference
bit-exact: gated_0.20 2.955/18.28, gated_0.25 3.374/19.63,
ungoverned_0.15 2.361/16.89 (monthlies/fullDDs, ICs
v92 0.0662/-0.0539/0.1148/0.1029/0.1425,
v94 mean-vs-h42 0.1361/-0.0483/0.1157/0.1104/0.1552,
v103_y6 0.0665/0.0389/0.0661/0.0267/0.0563, pvol anchors = v129
bit-exact). v149 delta vs v144 is near-neutral on the primary:
t25 3.365/19.65 vs 3.374/19.63 (-0.009pp/month at +0.02pp DD),
consistent with the leader manifest note ("Neutral vs v144").

## B. Why blind matched

- v144 base: blind replays the audited v141_v142 A2 pipeline line-for-line
  (v114-extended panel Bitstamp>=2013-01-01 + Coinbase BTC/ETH +
  spot_2017 prefix + v103 base + flow, 26/36 feats, pvol v129 method
  cutoff-102*4h t+44*4h<cutoff exp(pred) left-join replace; LO/LS weights
  N=5 rib rules, tranche mean/6, own 0.20-cap-2 scales, books
  0.25/0.25/0.5; v110 governor j=i-2, 540-bar peak, clip((0.20-DD)/0.10,
  0,1), sequential scenario/row-specific equity; v135 10bps execution
  T=t+4h p0/lo/hi/p15, strict </>, maker 0.0002 rel -/+0.0010 else taker
  0.0005 rel p15/p0-1 +/-0.0002, missing p0 taker). Direction xs/xr sets
  unchanged (v114 9 cols, v103 9+3 cols, groupby-t mean + rank(pct=True)).
- v148: blind daily = prod(1+4h nets of the UTC day)-1 grouped by
  floor('D') of bar open_time over live bars only (n=1824 full groups;
  the 6 union bars on 2026-09-23 are on/after END — see D). Blind RNG
  loop calls `integers(n)` then `geometric(1/30)` per block with wrap
  `(start+k) % n`, seeded `default_rng(0)`, 5000x365 — the same call
  order as leader `bootstrap` (`rng.integers(n)`,
  `rng.geometric(1/mean_block)`, `(start+arange(L)) % n`, seed 0).
  Bit-exact return AND drawdown quantiles on all 3 rows confirm identical
  daily pools, RNG sequence, compounding, and DD accounting
  (max(1-eq/cummax)).
- v149: blind vol feature sets = original + xs/xr for exactly
  vol42/vol180/vol_ratio/volz (v114: 26+8=34) and additionally
  rng6/ntr_z (v103: 36+12=48) matches leader `vol_predict_xs`
  line-for-line (`cols = VOL103 if "rng6" in panel.columns else VOL92`,
  `v142.add_xs(panel, cols)`, `feats + extra`, same `orig` = audited
  `vol_predict`). Direction OOS reused from v144 on both sides (leader
  monkey-patches only `vol_predict`, then calls audited
  `books_v142()` + `simulate()`; blind reuses `oos92x/oos94x/oos103x`
  and swaps only the pvol left-join replacement). Bit-exact
  monthlies/yearlies/DDs/fills confirm identical vol xs/xr timing,
  embargoes, pvol exclusion of direction xs, tranching, scales,
  governor timing, and 1m cost accounting. Blind xs-vol pvol spearmans
  (v114 0.5086/0.5253/0.6248/0.6885/0.6625; v103 0.5202/0.5199/0.6058/
  0.6922/0.6615, train rows unchanged) have no leader counterpart
  (leader stores no ICs) — direction ICs reproduce v144 bit-exact.

## C. Look-ahead audit

### `v148/v148_robustness_bootstrap.py` — no look-ahead found

- Chain (:23-25): imports the audited `v144_deploy_v3` module only; no
  data touched. Pass.
- Capture/simulate (:52-60): monkey-patches `v110.summarize` to capture
  per-bar 4h net series, then runs audited `books_v142()` +
  `simulate()` — no data or engine change. Pass.
- Daily (:63-64): `net[live]` with the audited calendar mask
  (`v110.START/END`), `groupby(floor("D")).apply(prod(1+r)-1)` — the
  product uses only the 6 realised 4h nets of the same UTC day, all
  known after that day's close. Pass.
- Bootstrap (:29-48): `default_rng(0)`, `integers(n)` starts,
  `geometric(1/30)` lengths, wrap `% n`, 5000x365 — resamples realised
  daily values only; no future information enters (resampled paths reuse
  realised governed returns; the governor is not re-simulated — disclosed
  in the docstring as conservative DD tails, not look-ahead). Quantile /
  P(DD>0.20) / P(ret<0) / P(monthly>=5%) are pure functions of the
  resampled paths. Pass.
- Wording slip (no numeric effect): docstring says "sum of the six 4h
  nets" but the code compounds with `prod(1+r)-1`, matching the
  assignment text; blind used the product. Pass.

### `v149/v149_xs_vol_forecast.py` — no look-ahead found

- Chain (:19-21): imports the audited `v144_deploy_v3` module only. Pass.
- Column switch (:22-23, :31): `VOL92` (vol42/vol180/vol_ratio/volz) vs
  `VOL103 = VOL92 + (rng6, ntr_z)`, selected by `"rng6" in
  panel.columns` — v114 panels lack rng6 (no flow) so they get the 4-col
  set, v103 panels get the 6-col set, exactly per spec. Pass.
- xs/xr timing (:32-33): `v142.add_xs(panel, cols)` = the audited
  groupby-t mean + `rank(pct=True)` over majors present at the same bar
  t, applied to already-causal vol values (bars close simultaneously);
  no future-t row enters (see v141_v142 audit §C). Rank default average
  method; NaNs propagate. Pass.
- pvol call (:34): delegates to the audited `v129.vol_predict` with
  `feats + extra` and the unchanged anchors/embargo — same cutoff,
  forward-window filter, and causal fv target as v144; test year never
  fit. Direction models untouched (the wrapper only patches
  `vol_predict`, then calls `books_v142()` + `simulate()`). Pass.
- Books/engine (:37-38): audited tranched books, 2-bar-lag returns,
  trailing vol, per-target s cap 2, governor j=i-2, 10bps 1m fills —
  unchanged. `reference_v144` stores the realised reference only. Pass.
- No normalisation/threshold fitting on locked test beyond the disclosed
  ex-post target frontier (0.25 primary); costs/funding per AGENTS.md.

## D. Post-hoc corrections / protocol log

- No spec reinterpretation after opening `v148/`/`v149/`. Part A script
  and `replication.json` frozen pre-open; tests pass 3/3 pre- and
  post-open.
- One pre-open runtime correction (not a post-open fix): the first Part A
  run asserted 1825 daily groups but live bars group into 1824 full UTC
  days (6 bars/day; the 6 union bars dated 2026-09-23 are on/after END
  and excluded by the live mask). The bound was relaxed pre-open to
  1820-1826 with the empirical n used generically in the bootstrap
  (`integers(n)`, wrap `% n`); the frozen `replication.json` records
  n=1824 with the full daily pool. Bit-exact leader quantiles confirm
  the leader's pool is identical.
- Blind extras with no numeric impact: full `daily` pool (1824 floats/
  row), `dd_quantiles`, `mean_ret_pct`, xs-vol pvol anchors/spearmans,
  `feats*_vol` lists, maker rate, orders/fills; leader rounds probs to
  3dp (blind 4dp, max diff 0.0004) and mean_g to 3dp (blind 4dp, max
  diff 0.0004).
- Leader-side wording only: v148 docstring "sum of the six 4h nets" vs
  code `prod(1+r)-1` (blind follows the code = assignment text).

## E. Manifest notes / verdict

- `v148/result_manifest.json`: track C, `rejected`, `live_approved:false`,
  audit pending. Scenario slots repeat the realised v144 primary row
  (3.374/19.63, fills placeholder); note matches the numbers (primary
  median 1y +45.09%, P(DD>20%) 0.192, P(loss) 0.085, P(>=5%/mo) 0.245).
  Blind reproduces every quantile bit-exact and every prob within 0.0004.
- `v149/result_manifest.json`: track B, `rejected`, `live_approved:false`,
  audit pending. Single realistic 1m scenario repeated in 3 slots;
  primary t25 3.365/19.65, t20 2.955/18.31, ref 2.369/16.79 matches blind
  bit-exact. Note "Neutral vs v144 (3.365/19.65 vs 3.374/19.63)" matches
  the numbers (t25 -0.009pp/month at +0.02pp DD; t20 +0.000pp at +0.03pp;
  ref +0.008pp at -0.10pp).
- Blind replication is bit-exact on all v148 return/DD quantiles and all
  v149 rows/yearlies/fills/DDs. No look-ahead in daily pooling, RNG
  resampling, vol xs/xr timing, the rng6 column switch, pvol retraining,
  tranching, scales, governor timing, or 1m fill/cost paths. Audit
  complete; leader files untouched.

## Files

- `replication.json` (Part A, blind), `replicate_v148_v149.py`,
  `tests/test_v148_v149_audit.py` pass 3/3.
