# v190 blind audit — COMPARISON.md (Part B)

Scope: research/parallel/rounds/parallel-20260906-r2/v190_audit/ +
tests/test_v190_audit.py only. Base: v144 books_v142, v125 tranching,
v129 vol forecast, v151 info ensemble, engine_user gate engine. No
leader files edited.

Blind protocol: replication.json (replicate_v190.py,
tests/test_v190_audit.py passing 5/5) was saved BEFORE opening v190/.
Pre-save reads were limited to the allowed base (AGENTS.md,
OPENCODE_VF_COMMON.md, OPENCODE_V190_AUDIT.md, skill,
v144/v144_deploy_v3.py, v142/v142_cross_sectional_features.py,
v125/v125_tranching.py, v129/v129_vol_forecast_sizing.py,
v103/v103_flow_short_horizon.py, v92/v92_pooled_hgb_vt.py,
v94/v94_long_short_ensemble.py, v115/v115_candidate.py,
v114/v114_bitstamp_history.py, v113/v113_longer_history.py,
v151/v151_info_ensemble.py, v150/v150_options_flow.py,
engine_user/engine_user.py, v189_audit/ + v151_v152_audit/ replication
+ COMPARISON as method reference, raw 4h/1d/funding/spot panels, carry,
1m intraday, Deribit options parquet; directory listing showed v190/
filenames only, no file contents). v190/ (v190_bracket_target_model.py,
v190_result.json, manifest, logs) was first opened after the Part A
save. Part A imports no v190 module (all formulas inline from the
assignment text + audited base modules + raw data + 1m intraday).

Key maps: blind rows v151, E, blend_50_50 <-> leader rows ref_v151,
E_alone, blend_v151_E. Thresholds per assignment: return diff > 1pp,
DD diff > 0.5pp.

## A. Number comparison (blind vs leader)

### ref_v151 — bit-exact

| row | blind monthly dev4 / 5y / gateDD | leader monthly dev4 / 5y / gateDD | diff |
|---|---|---|---|
| v151 <-> ref_v151 | 3.896 / 3.584 / 19.41 | 3.896 / 3.584 / 19.41 | 0 / 0 / 0.00pp |

Yearly nets blind = leader in all 5 years (max abs diff 0.00pp):
23.37, 52.50, 86.27, 78.73, 32.02. DDs, mean_g, fills (35288),
unfilled (8296), stops (74), tps (51), rungs (2571), fees (0.096),
funding (0.1835) all exact. This also reproduces v189 P2_sleeve
bit-exact, confirming v154 members A,B equal the rebuilt v144/v150
books and the shared engine_user path.

### E_alone — materially different (all thresholds exceeded)

| | blind | leader | delta leader-blind |
|---|---|---|---|
| monthly dev4 | 3.004 | 2.601 | -0.403pp/month |
| monthly 5y | 2.830 | 2.570 | -0.260pp/month |
| last year monthly | 2.139 | 2.449 | +0.310pp/month |
| gate DD | 22.04 | 22.56 | +0.52pp |
| fills / stops / tps | 30805 / 74 / 55 | 30092 / 76 / 63 | -713 / +2 / +8 |

Yearly nets (pp, delta = leader-blind):

| 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|
| 38.08 vs 29.10 (-8.98) | 4.95 vs 2.26 (-2.69) | 69.42 vs 65.08 (-4.34) | 68.59 vs 57.36 (-11.23) | 28.92 vs 33.68 (+4.76) |

All five years exceed 1pp. Yearly DDs also differ by >0.5pp in
2021 (18.64 vs 18.84), 2023 (16.42 vs 16.45 is small), 2024 (10.58 vs
14.28, +3.70pp), 2025 (16.22 vs 17.84, +1.62pp).

### blend_50_50 — materially different

| | blind | leader | delta |
|---|---|---|---|
| monthly dev4 | 3.523 | 3.298 | -0.225pp/month |
| monthly 5y | 3.341 | 3.146 | -0.195pp/month |
| last year | 2.616 | 2.537 | -0.079pp/month |
| gate DD | 20.70 | 21.06 | +0.36pp |

Yearly nets delta: 2021 +5.40pp blind above leader (32.33 vs 26.93),
2022 +0.72 (21.18 vs 20.46), 2023 +1.74 (81.18 vs 79.44),
2024 +8.34 (81.38 vs 73.04), 2025 +1.26 (36.33 vs 35.07). Four of five
years exceed 1pp; 2024 dominates.

### ICs — different definitions, same qualitative pattern

Blind ic_combined = Spearman(pred, y_long - y_short):
0.0995, -0.0017, 0.1282, 0.1657, 0.1558.
Leader ic_pred_vs_y = Spearman(pred, y) where y is the original v103
7-day target: 0.1183, 0.0109, 0.1187, 0.1489, 0.1823.
Blind ic_long (pred_long vs y_long): 0.0863, -0.0171, 0.0868, 0.1339,
0.1785 vs leader ic_long 0.104, -0.0091, 0.082, 0.1225, 0.1706.
Blind ic_short: 0.103, 0.008, 0.1578, 0.1892, 0.1182 vs leader ic_short
0.1354, 0.0093, 0.1595, 0.1783, 0.1423.
2022 is near zero on both sides; other years 0.08-0.19. The gap is
expected: different target (bracket spread vs 7-day return) and
different short-return math (see B).

Net assessment: v151 exact confirms books + engine_user path. E and
blend gaps are direction-book differences, not cost/engine drift:
same vol forecast quality bit-exact (pvol spearmans 0.507/0.503/0.614/
0.703/0.665), same phased/vol-target/engine code, same fills scale.
Both blind and leader agree E alone and the blend fail the gate
(DD > 20, monthly < 5%) and trail v151 on dev4.

## B. Why E differs — short-return math + bar source + tail rule

1. Short gross return formula. Blind uses the exact short return
e/exit-1 (v190_bracket_target_model.py:91-95 uses the linear
approximation 1-exit/e). For SL = e(1+4sd), exact = e/SL-1 =
-4sd/(1+4sd); leader = -4sd. For a 4-sigma stop of ~10-20%, the
leader overstates loss magnitude by ~10-20% of the move, and similarly
overstates short gains at TP. Long legs are identical
(sl/e-1 both sides). The short model therefore trains on different
ys values, shifting p_short, pred, and the E book. This alone explains
multi-pp yearly gaps concentrated in short-driven years (2021, 2024).

2. Bar source for labels/sigma. Blind uses v144.v103.v92.load_asset
(base: Binance perps + 2017 spot prefix, the same bars the p103 panel
was built from). Leader bracket_labels uses ext.v92.load_asset
(v190_bracket_target_model.py:56, extended: + Coinbase 2015 + Bitstamp
2013 for BTC, Coinbase for ETH). Recent OOS bars (2021+) are identical,
so sigma_d and exits match there; early training rows differ (longer
prefix changes the 360-bar sigma availability and the bar index map).
Training composition therefore differs slightly, compounding the
short-math gap.

3. End-of-history label requirement. Leader skips any row with
r+1+H >= len(O) (v190_bracket_target_model.py:68), i.e. no label in the
last 43 bars even if SL/TP would have hit earlier. Blind allows SL/TP
hits in the available tail and only requires open(t+43) for the timeout
path. Effect is tiny (last 43 bars of 2026-09) but changes n_eval_rows:
blind 10752 vs leader implied 10750-style tail on 2025-09-24, and the
IC denominators (blind IC on y_comb vs leader IC on y).

4. IC definition. Blind ic_combined = Spearman(pred, y_long-y_short);
leader ic_pred_vs_y = Spearman(pred, y) (v190_bracket_target_model.py:
126, y = original v103 7-day target). Blind ic_long/ic_short match the
leader per-side construction (corr(p_side, y_side)) but on the exact
short labels, hence the 0.01-0.03 gaps above.

5. v151 source. Leader v151 = (Am+Bm)/2 from cached
members_v154.parquet (v190_bracket_target_model.py:104-107); blind
v151 = 0.5*books_v142() + 0.5*books_with_options() rebuilt. Bit-exact
match (see A) proves the two sources are identical books on the same
grid (10950 bars), so no gap here. Opens/prep are likewise identical
(books154 vs p103 pivot on the same 10950 grid; same eu.prepare/
eu.simulate with m=4, sleeve, target 0.25, cap 2).

Everything else matches line-for-line: f103 36 cols, HGB params,
t+43 < anchor-78 filter, pred = p_long-p_short, v129 vol_predict with
f103 and EMBARGO 102 then left-join replace (n_replaced 54750 both
sides), v125.raw_ls + phased 6 + ext.v94.vol_target_scale, union index
missing->0, engine_user m=4/sleeve/target/cap.

## C. Look-ahead audit

### v190/v190_bracket_target_model.py — no look-ahead found

- Chain (:47-50): imports engine_user, then reuses eu.er.v144 and its
v129/v125/v103 plus ext = v115.v114.v113. No data touched directly.
Pass.
- Labels (:53-98): sigma = o.pct_change().rolling(360,min120).std()*
sqrt(6) uses bars <= t only; entry = O[r+1], scan Hh/Ll[r+1:r+1+H],
timeout O[r+1+H] use future bars only as the target; SL-first within a
bar (k_s<=k_t) matches the assignment and the engine stop-first rule.
Training filter (:115, p.t+43h < cutoff with cutoff = anchor-78 bars)
guarantees exit open(t+43) before anchor-embargo; per-side notna
filter (:118) drops incomplete labels. No normalisation/threshold fit
on any test year. Pass (modulo the exact-vs-linear short note in B,
which is a return-math choice, not leakage).
- Features (:110, f103 = non-y/t/open/sym/bar): same 36 cols as blind.
Panel p103 from audited books_v142 includes the audited xs/xr timing
(contemporaneous mean/rank at t) and causal v92/flow features.
Pass.
- Models (:117-122): per-anchor/side HGB with the specified params on
past-only rows; pred = p_yl-p_ys on the anchor year. Pass.
- Book E (:130-135): vol_predict on p103/f103 with EMBARGO 102, merge
pvol left-join replace, raw_ls/phased-6, vol_target_scale(p103,W),
reindex to books154.index fillna 0. All contemporaneous at t; no
future-t row enters. Pass.
- v151 (:102-107): cached members A,B (audited causal books) averaged
0.5/0.5 on the same index. Pass.
- Simulate (:136-141): eu.simulate with m_sl=4, sleeve, defaults
target 0.25 cap 2; trailing vol, governor j=i-2, 10bps limits,
SL/TP minute-0/fill-minute, stop-first, adverse funding, dip sleeve
16..238 all inside audited engine_user. Pass.
- Selection (:142-150): eligible = non-ref rows with gate_dd<=20 and
no losing year in the first four anchor years; fallback to all non-ref
candidates; selected = max monthly_dev4; beats_reference compares dev4
only; final_score reports 5y/last-year/losing/DD/gate_pass one time.
Uses no last-year statistic to choose. Pass.

### engine_user.py — executed engine verified

Blind asserts maker 0.0002 taker 0.00055 fund_long 0.0001 d_limit
0.001 size 0.25 s_ref 1.657 rungs 2.5/3/3.5/4, matching the gate cost
model. v151 bit-exact reproduction (fills, stops, tps, rungs, fees,
funding, yearly nets/DDs/mean_g) confirms the executed fill/stop/
funding arithmetic independently.

## D. Aggregation alignment

No new aggregation beyond the audited paths: 4h bars from Binance +
spot prefix (blind) vs + Coinbase/Bitstamp prefix (leader) for labels
only; panel aggregation unchanged; opt join not used here; 1m cubes via
eu.prepare on the 10950 decision grid. Prefix rows are past-only and
leave OOS test rows unchanged.

## E. Post-hoc corrections / protocol log

- No change to replication.json, replicate_v190.py, or
tests/test_v190_audit.py after opening v190/. Tests pass 5/5 pre- and
post-open.
- One pre-open spec gamble logged here (not a code bug): short funding
read as no funding term for shorts (ret-0.00075 only), long pays
0.0001*bars_held/2; leader confirms (COST always, FUND only on long:
v190_bracket_target_model.py:84 vs :96). Match confirmed post-open.
- Second pre-open gamble: exact short return e/exit-1 vs leader linear
1-exit/e. Blind kept the exact version as the honest blind output; the
linear version is documented in B.1. A confirmatory linear-rerun is
left to the leader; the code path is bracket_labels :91-95.
- Third pre-open gamble: base bars vs extended bars for labels (B.2);
blind used the panel bars; leader uses ext bars. Same honest-blind
note.
- Blind extras with no leader counterpart: ic_combined (pred vs
y_long-y_short), train_rows per side (both 32818..76648), vol quality
table, union_bars/columns, full spec/labels/engine blocks. Leader
extras: ic_pred_vs_y (pred vs original y), selected/beats_reference/
final_score_selected, per-row gate_pass.

## F. Manifest notes / verdict

- v190/result_manifest.json: track B, rejected, live_approved:false,
audit pending. Single gate scenario repeated in 3 slots
(3.146/21.06, fills 34666, 60 months); note matches the numbers
(triple-barrier IC 0.10-0.18 except 2022 ~0.01; E dev4 2.601 DD 22.56;
blend dev4 3.298 DD 21.06 < v151 3.896. Rejected.). Blind reproduces
the reference and the engine exactly; the only divergences are the
documented short-math/bar-source gaps, which fully explain the >1pp
yearly and >0.5pp DD gaps on E/blend at small IC gaps.
- No look-ahead in feature timing, label windows (future only as
targets), fit windows (t+43 < anchor-78), vol forecast embargoes,
tranching/scales, governor timing, or the 1m fill/cost paths. Selection
uses first-four-years only. E and blend DDs (22.56/21.06 leader,
22.04/20.70 blind) breach the 20% acceptance gate on every non-ref
row; monthlies (2.57-3.34) miss the 5%/month gate. Audit complete;
leader files untouched.

## Files

- replication.json (Part A, blind, frozen), replicate_v190.py,
tests/test_v190_audit.py pass 5/5.
