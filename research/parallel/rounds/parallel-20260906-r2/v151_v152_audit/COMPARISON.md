# v151 + v152 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v151_v152_audit/` +
`tests/test_v151_v152_audit.py` only. Base: v144 replication (v142 xs/xr
books + v141 sequential governor + 10bps 1m execution, audited in
`v141_v142_audit` A2 / `v148_v149_audit`) and v150 replication
(`v150_audit`: options features, no-xs reading, v144 engine otherwise).
No leader files edited.

Blind protocol: `replication.json` (`replicate_v151_v152.py`,
`tests/test_v151_v152_audit.py` passing 4/4) was saved BEFORE opening
`v151/` or `v152/`. Pre-save reads were limited to the allowed base
(`AGENTS.md`, `OPENCODE_VF_COMMON.md`, `OPENCODE_V151_V152_AUDIT.md`,
skill, `OPENCODE_V150_AUDIT.md`, `v144/v144_deploy_v3.py` +
`v144_result.json`, `v150_audit/replicate_v150.py` + `replication.json` +
`COMPARISON.md`, `v148_v149_audit/` replication + COMPARISON,
`v129_v131_audit` pvol rows, raw 4h/1d/funding/spot/Coinbase/Bitstamp
panels, carry, 1m intraday, Deribit options parquet; directory listing
showed `v151/`/`v152/` filenames only, no file contents). `v151/`
(`v151_info_ensemble.py`, `v151_result.json`, manifest, logs) and `v152/`
(`v152_dd30_frontier.py`, `v152_result.json`, manifest, logs) were first
opened after the Part A save. Part A imports no
v151/v152/v150/v144/v142/v141 leader module (all formulas inline from
the assignment text + audited replication code + raw data + carry + 1m
intraday).

Key maps: blind `v151.rows.{reference_t15_ungoverned,t20_governed,
primary_t25_governed}` <-> leader `v151_result.json` same keys; blind
`v152.rows.{t30_governed_dd30,t35_governed_dd30,
primary_t40_governed_dd30}` <-> leader `v152_result.json`
`{t30_gov30,primary_t35_gov30,t40_gov30}`. Thresholds per assignment:
return diff > 1pp, DD diff > 0.5pp.

## A. Number comparison (blind vs leader)

### v151 — small monthly, large offsetting yearly gaps (xs-scope inheritance)

| row | blind monthly / fullDD | leader monthly / fullDD | Δ monthly | Δ DD |
|---|---|---|---|---|
| reference_t15_ungoverned | 2.411 / 15.99 | 2.456 / 16.43 | +0.045 | +0.44pp |
| t20_governed | 3.038 / 17.98 | 3.090 / 17.96 | +0.052 | -0.02pp |
| primary_t25_governed | 3.454 / 18.98 | 3.526 / 19.41 | +0.072 | +0.43pp |

(Δ = leader − blind. Full-path DD does not breach 0.5pp, but yearly
cells do — see below. Fills match within 11: t15 2090 vs 2081,
t20 2094 vs 2083, t25 2100 vs 2090 in 2021; all other years exact or
±5.)

Yearly nets exceed the 1pp threshold in almost every year of every row:

| row | 2021 Δnet/ΔDD | 2022 Δnet/ΔDD | 2023 Δnet/ΔDD | 2024 Δnet/ΔDD | 2025 Δnet/ΔDD |
|---|---|---|---|---|---|
| t15 | -2.28/-0.40 | +8.06/-0.40 | +1.81/+0.66 | -2.50/+0.04 | -1.70/+0.09 |
| t20 | -2.60/-0.02 | +11.69/-0.39 | -0.31/+1.80 | -2.72/-0.23 | -2.05/+0.11 |
| t25 | -2.18/+0.43 | +13.64/-0.65 | -0.54/+1.60 | -2.02/-0.66 | -3.16/-0.07 |

(Δ = leader − blind, nets in pp, DDs in pp.) Mean_g gaps exceed
rounding on governed rows (e.g. t25 2021 0.86 vs 0.8735, 2023 0.946 vs
0.9618; t20 2023 0.961 vs 0.9748) while ungoverned mean_g = 1.0 both
sides. Large offsetting yearly diffs with a small monthly diff is the
signature of materially different direction books, not of cost/engine
drift — the same signature as the `v150_audit` §A gap, halved.

### v152 — bit-exact on every row, year, fill, and DD

| row (blind <-> leader) | blind monthly / fullDD | leader monthly / fullDD | diff |
|---|---|---|---|
| t30_governed_dd30 <-> t30_gov30 | 3.764 / 25.04 | 3.764 / 25.04 | 0 / 0.00pp |
| t35_governed_dd30 <-> primary_t35_gov30 | 3.932 / 25.28 | 3.932 / 25.28 | 0 / 0.00pp |
| primary_t40_governed_dd30 <-> t40_gov30 | 4.091 / 25.28 | 4.091 / 25.28 | 0 / 0.00pp |

Yearly nets/DDs/fills blind = leader in all 3 rows x 5 years (max abs
net diff 0.00pp, DD diff 0.00pp, fills diff 0):
t30: 14.88/25.04/2015, 43.54/12.45/2190, 101.56/17.15/2188,
73.27/12.87/2189, 59.41/15.68/2178;
t35: 14.23/25.28/2033, 42.33/12.56/2190, 113.61/17.15/2188,
78.04/13.25/2189, 63.63/16.88/2178;
t40: 14.23/25.28/2033, 41.86/12.56/2190, 124.64/17.15/2188,
82.65/13.62/2189, 66.74/16.88/2178.
Mean_g blind (4dp) vs leader (3dp): max abs diff 0.0005 (rounding
only). No 1pp / 0.5pp threshold exceeded anywhere in v152.

## B. Why v151 differs — inherited v150 xs-scope error, halved by the ensemble

Blind B leg = frozen `v150_audit` reading "(no xs versions)" as "no
xs/xr features at all": return feats v114 26+5=31, v103 36+5=41.
Leader B leg (`v150_options_flow.py:9-10,60-63,72`, reused by
`v151_info_ensemble.py:29-41` via `books_with_options()`) joins opt
feats to the base panels BEFORE the v142 xs step and then still runs
it: return feats base + opt + xs/xr (49/65). Documented and measured in
`v150_audit/COMPARISON.md` §B (leader t25 3.465/19.15 vs blind no-xs
3.338/18.31: +0.127pp/month, +0.84pp DD).

v151 averages books 0.5/0.5, so the inherited gap is expected at ~half
weight — observed t25 +0.072pp/month at +0.43pp DD, t20 +0.052pp at
-0.02pp, t15 +0.045pp at +0.44pp (cf. half of +0.127/+0.84 =
+0.064/+0.42). The 2022 year dominates both audits (leader beats blind
by 14-25pp across rows in v150; by 8-14pp in v151, roughly half). The
xs direction features, not the opt features, drive the gaps.

Everything else matches line-for-line:

- Blind v144 base reproduces the audited values bit-exact (2.361/16.89,
  2.955/18.28, 3.374/19.63; ICs v92 0.0662/-0.0539/0.1148/0.1029/0.1425
  etc.; pvol spearmans = v129 bit-exact). Blind v150 leg reproduces the
  frozen `v150_audit` numbers exactly (2.351/16.54, 2.967/17.84,
  3.338/18.31).
- Ensemble math: blind union index (10950 = 10950 ∩ 10950, overlap
  recorded) with missing→0 ≡ leader `:48-49`
  (`A.index.union(B.index)`, `reindex(...).fillna(0.0)`, 0.5/0.5).
  Vol recomputed from the ensemble books with the same
  rolling-360/min-120 formula; opens/carry shared (identical grids).
- Engine: sequential governor j=i-2, 540-bar peak, clip((0.20-DD)/0.10),
  per-target s cap 2, 10bps 1m rule (T=t+4h, strict through minutes
  2..14, maker 0.0002 rel ∓0.0010 else taker 0.0005) ≡ audited
  `books_v142()` + `simulate()`.
- Leader `references` (v144_t25 3.374/19.63, v150_t25 3.465/19.15)
  match the audited v144 values and the true (with-xs) v150 values;
  leader note "better than both members" matches the numbers
  (3.526 > 3.465 > 3.374). Leader `corr_book_returns_proxy` 0.063534
  has no blind counterpart (blind stores no book-return correlation).
- v152 bit-exact (§A) confirms the v144-book + engine path independently.

Net assessment: v151 ≈ average of two members on the monthly
(t15 2.411 between 2.361 and 2.351? slightly above both — diversification;
t20 3.038 between 2.955 and 2.967? above both; t25 3.454 between 3.374
and 3.338? above both) with DD at or below both members on t15/t20 in
blind (15.99, 17.98) and mixed on t25 — same qualitative pattern as the
leader (t15 2.456, t20 3.090, t25 3.526 all above both members with DDs
16.43/17.96/19.41). v152 dd30 frontier (3.764/25.04, 3.932/25.28,
4.091/25.28) exceeds the 20% user limit on every row — reporting
frontier only, consistent with the leader note "Not a recommendation to
exceed the 20% limit".

## C. Look-ahead audit

### `v151/v151_info_ensemble.py` — no look-ahead found

- Chain (`:30-33` + `:45-47`): imports the audited `v144_deploy_v3`
  module and the audited `v150_options_flow` module only; no data
  touched directly. Pass.
- B leg (`:29-41`): `opt_features()` is the audited v150 math
  (reindex + fill present/past-only; trailing rolling 6/180 windows;
  `merge(feats,on="t",how="left")` = bar T to panel row t=T, same timing
  as the row's own OHLCV; 2-bar execution lag downstream). Vol wrapper
  (`:36`) drops exactly the 5 OPT cols before the audited
  `vol_predict` — embargoes, causal fv target, left-join replace
  unchanged. `books_v142()` then adds xs/xr on the merged panels with
  the audited groupby-t mean + `rank(pct=True)` over majors present at
  the same bar t (contemporaneous only). Pass.
- A leg (`:46`): audited `books_v142()` unchanged. Pass.
- Ensemble (`:48-49`): union index, `fillna(0.0)`, 0.5/0.5 average of
  two already-scaled causal book series at the same t — contemporaneous
  only, no future-t row enters. Missing→0 applies to no bars here
  (identical 10950 grids). Pass.
- Simulate (`:51`): audited `v144.simulate(p103, books)` unchanged —
  trailing vol, per-target s cap 2, governor j=i-2, 10bps 1m fills,
  carry/funding per AGENTS.md. `p103` from the A leg shares the grid
  with B (opt merge adds columns, not rows). Pass.
- Costs/funding per AGENTS.md; target choice ex post (0.25 primary) is
  the disclosed v144 frontier, unchanged by v151.

### `v152/v152_dd30_frontier.py` — no look-ahead found; executed engine verified

- Chain (`:22-24`): imports the audited `v144_deploy_v3` module only.
  Pass.
- Guard (`:30`): asserts the exact audited governor string
  `"(0.20 - (1 - eq[j] / peak)) / 0.10"` is present in the loaded
  source — fails closed if upstream changes. Pass.
- Source replacement (`:33`): replaces ONLY that constant pair with
  `"(0.30 - (1 - eq[j] / peak)) / 0.15"` on the extracted
  `simulate` function text (`src[index("def simulate"):index("def main")]`),
  then `exec`s it with `ns["ROWS"] = ((t30,0.30,True),
  (primary_t35,0.35,True), (t40,0.40,True))`. Peak window
  (`eq[max(0,j-90*PD+1):j+1]`, 540 bars), lag `j=i-2`, per-target
  `minimum(target/vol,CAP)` with `CAP=2`, tranching/scales, 10bps
  p0/lo/hi/p15 fill logic, carry/funding, and sequential equity
  accounting are all outside the replaced string and execute unchanged.
  The docstring/governor field `"clip((0.30 - DD)/0.15, 0, 1)"` matches
  the executed replacement. Bit-exact blind reproduction (§A) confirms
  the executed engine. Pass.
- Governor timing still causal (trailing 540-bar peak on realised
  equity at j=i-2; no future equity enters). All three rows governed
  (no ungoverned leg — matches the assignment's target list). Pass.
- No normalisation/threshold fitting beyond the disclosed ex-post
  target frontier (0.30/0.35/0.40); costs/funding per AGENTS.md.

## D. Aggregation alignment

Covered by `v150_audit` §D (`fetch_deribit_options_4h.py`: bar =
`ts.floor(4h)`, trades in [T,T+4h) → bar T; join on t is bar-close
timing with 2-bar execution lag). No new data path in v151/v152.

## E. Post-hoc corrections / protocol log

- No change to `replication.json`, `replicate_v151_v152.py`, or
  `tests/test_v151_v152_audit.py` after opening `v151/`/`v152/`. Tests
  pass 4/4 pre- and post-open.
- One pre-open spec gamble logged here (not a code bug): v152 rows all
  governed with the dd30 governor — the assignment lists only "targets
  0.30, 0.35, 0.40 (cap 2)" with the new governor and no ungoverned
  leg; leader confirms (`ROWS = (...,True)` x3). Match confirmed
  post-open by bit-exact numbers.
- The v151 xs-scope inheritance (§B) was known pre-open from the frozen
  `v150_audit` COMPARISON; blind did NOT rerun with xs (the frozen
  numbers above are the honest blind output). A confirmatory xs-rerun is
  left to the leader; the code path is `books_with_options()` =
  opt-merged panels through `books_v142()`, i.e. exactly the leader
  script.
- Blind extras with no leader counterpart: full v144/v150 base rows +
  ICs, pvol spearmans, `feats*x`/`feats*o` lists, maker rates,
  orders/fills, `overlap_bars`/`idx144`/`idx150`, full `meta`. Leader
  extras: `corr_book_returns_proxy` (v151), `coverage` (v150 leg),
  rounded `mean_g` (3dp vs blind 4dp).

## F. Manifest notes / verdict

- `v151/result_manifest.json`: track B, `rejected`, `live_approved:false`,
  audit pending. Single realistic 1m scenario repeated in 3 slots
  (3.526/19.41, fills 10839, 60 months); note matches the numbers
  (0.5 v144 + 0.5 v150, better than both members). Blind reproduces the
  ensemble math and engine exactly; the only divergence is the
  documented inherited xs-scope gap (≈half the v150 gap), which fully
  explains the >1pp yearly and several >0.5pp yearly-DD gaps at small
  monthly/fullDD gaps.
- `v152/result_manifest.json`: track C, `rejected`, `live_approved:false`,
  audit pending. Single realistic 1m scenario repeated in 3 slots
  (3.932/25.28, fills 10778, 60 months); note matches the numbers
  (0.40 → 4.09%/month at 25.28% DD; cap binds at 0.35-0.40 — blind
  t35/t40 monthlies +0.168pp apart vs t30/t35 +0.168pp, consistent with
  cap compression). Blind reproduces every row/year/fill/DD bit-exact.
- No look-ahead in the ensemble averaging, the opt join/broadcast, the
  vol wrapper, xs timing, embargoes, tranching, scales, governor timing
  (both gov20 and gov30), the v152 source-replacement execution, or the
  1m fill/cost paths. v152 DDs (25.04/25.28/25.28) breach the 20%
  acceptance gate on every row. Audit complete; leader files untouched.

## Files

- `replication.json` (Part A, blind, frozen), `replicate_v151_v152.py`,
  `tests/test_v151_v152_audit.py` pass 4/4.
