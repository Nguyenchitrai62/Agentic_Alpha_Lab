# oc_i2_spreadveto REPORT — Spread/depth-state dip veto (IDEAS2_20261007 §4)

## PRE-REGISTRATION (written BEFORE any outcome is computed — 2026-10-07)

Idea: binary VETO (not sizing): skip new dip bids when trailing-7d median
spread > p90 or top-5 depth < p10. Data: data/raw/bookdepth_20261004
(Binance bookDepth from 2023-01 ONLY) + data/raw/topbook_live (maturing,
not gate). Not a repeat of oc_depthtilt (depth-TILTED SIZING), oc_bookcorr,
oc_depthregime (deep loses every regime), IDEAS2_20261006#10 spread-SIZING.

Pre-registered variants (exactly 2, no others):
- S1: skip new dip bids when trailing-7d median spread > p90.
- S2: skip on spread-p90 OR depth-p10.

Frozen state definitions:
- Spread state: trailing-7d median quoted spread (ask-bid)/mid from depth
  snapshots with ts strictly before the bar open T. Depth state: trailing-7d
  median top-5 total notional tot5 = bid_n5 + ask_n5 over snapshots with
  ts in [T-7d, T). Bar needs >= 1000 snapshots else NaN -> no veto.
- Thresholds: per anchor year A and coin, p90 (spread) / p10 (depth) of the
  bar-state series over the calibration window [2023-01-08, A-7d) (expanding
  from depth start, 7d embargo, never the test year). Min 60 bars else NaN
  -> no veto. 2021-2022 bars: no depth data -> veto inactive (size 1,
  no imputation, per spec).
- Veto scope: per (phase, bar, coin) — vetoed coin-bars contribute no new
  dip bids that bar; holds/exits of already-open rungs unchanged; depths/
  stops/TP unchanged; G-cap walk re-run on the vetoed candidate set.
- Replica: audited oc_depthtilt ledger (research/tournament/oc_depthtilt/
  fills.parquet, 22312 fills, phase-0 sums = placebo ref to 1e-6); fills
  identical across arms, only membership differs by veto.
- Scoring: dip replica + placebo gate on 4-phase means per year:
  PASS_sum(Y) iff S_rule_bar(Y) >= S_base_bar(Y); PASS_dd(Y) iff
  DD_rule_bar(Y) <= DD_base_bar(Y) + 0.01; PROMISING iff both in >= 4/5
  years AND dSum5y >= +0.273 (pooled placebo p95, oc_placebo_dip).
  PRIMARY = uncapped w*y (placebo-gate-compatible); capped G=2.0 wk*y side row.
- Selection: compare/choose ONLY on dev years 2021-2024 (robust criterion:
  DD <= 20 and no losing dev year, prefer dev4 mean >= 5, then highest dev4
  WORST year). Overlap note (spec §4 leak row): depth exists from 2023-01,
  so WF selection is reported on the 2023-2024 overlap + paper proof
  (underpowered by design); 2021-2022 veto legs are no-op ties (disclosed).
  Most recent year 2025-09-24..2026-09-23 scored ONCE, for the chosen
  variant only, and labelled POST-HOC. Gate costs: maker 0.02%, taker
  0.055%, longs pay 0.01%/8h (dip replica uses maker/taker + v293 settle
  funding, same as baseline).
- Baseline gate: reproduce G2+carry (5.634 / DD 16.75 / full 16.66,
  oc_carrycompound) or G2 (5.41) exactly first, else stop and report.
- Engine gate: 4-phase engine runs ONLY on the 2023-2024 overlap (+ paper)
  and ONLY if the dip screen passes. 4-phase reset metric
  (research/diagnostics/r2_decompose5/reset_metric.py) + full-path DD
  like v421/v422 reported for any engine run.

## (results below — appended after the run; pre-registration above unchanged)

## RESULTS (2026-10-07; selection on dev 2021-2024 only; 2025 never scored)

Baseline gate (reproduced exactly or stop — PASSED): v421 R2B1D17BFG2 =
5.41 / W 2.588 / DD 16.91 / full-path 16.82; oc_carrycompound G2_f0.25 =
5.634 / W 2.778 / DD 16.75 / full 16.66 (asserted in-script; reset_metric.
year_reset re-ran live: per-year R/DD match v421_result to the digit).
Replica fidelity: audited oc_depthtilt ledger (22312 fills); phase-0 sums
2.388052/0.182865/3.809764/2.579274/0.711509 = placebo ref to 1e-6; dev
4-phase-mean base sums 0.9113/0.8326/2.0998/3.1974 = placebo base exactly.

S1 (spread-p90 veto): INFEASIBLE — the archive stores ONLY 1/2/5%
cumulative notionals (bid/ask_n1/n2/n5; scripts/fetch_bookdepth.py), no
bid/ask prices, so no spread exists to threshold. S1 = no-op (rule==base,
dSum 0.0, legs 4/4 on ties, fails the +0.273 tail gate). topbook_live is 3
days (2026-10-04..06), maturing, no WF overlap — not gate-usable. S1 scored
as pre-registered but untestable; NOT a candidate.

S2 (depth leg; spread leg missing, disclosed): 643/17540 dev fills vetoed
(3.7%), ALL in 2023 (12% of 2023 fills); 2021/2022 inactive by design
(no depth, size 1); 2024 fires zero (post-Sep2024 med7 never dips below
the pre-anchor p10 — depth trended up). Thresholds p10 per coin:
2023-anchor BTC 549M / ETH 253M / SOL 13.8M / BNB 22.2M / XRP 23.3M;
2024-anchor higher except BNB/XRP slightly lower.

PRIMARY uncapped w*y 4-phase means (S_base -> S_rule / DD_base -> DD_rule):

| year | S_base -> S_S2 | DD_base -> DD_S2 | sum leg | DD leg |
|---|---|---|---|---|
| 2021 | 0.9113 -> 0.9113 (+0.0000) | 0.856 -> 0.856 | tie-pass | pass |
| 2022 | 0.8326 -> 0.8326 (+0.0000) | 0.951 -> 0.951 | tie-pass | pass |
| 2023 | 2.0998 -> 1.8184 (-0.2814) | 0.800 -> 0.807 | FAIL | pass |
| 2024 | 3.1974 -> 3.1974 (+0.0000) | 0.355 -> 0.355 | tie-pass | pass |

dSum_dev4 = -0.281 (gate +0.273); overlap 2023-2024: sum 1/2, dSum -0.281.
Capped G=2.0 side row: dSum -0.133, sum 3/4, DD 3/4. Pooled dev4: veto
drops 643 fills (n 17540->16897), win 71.26%->71.01%, DD 3.127 unchanged.

Leak audit: state from snapshots ts strictly before bar open; thresholds
fit on [2023-01-08, A-7d) (7d embargo, never the test year); 2021-2022 no
imputation; no row ts>=2026-09-24 used; year 2025-09-24..2026-09-23 never
scored for any variant (dev screen decides; nothing passed so no 2025 run,
no engine run — per assignment the 4-phase engine runs only if the screen
passes). No 4-phase reset metric / full-path DD beyond the reproduced
baselines, for the same reason. POST-HOC label: all five anchor years were
visible when the rule was frozen; a passing result would still need
prospective paper proof (none claimed).

Verdict: REJECT — S1 untestable with the current archive (no spread
columns); S2-depth veto loses -0.28 dev sums (fails +0.273 gate, sum legs
3/4 dev and 1/2 on the 2023-2024 overlap), fires in one year only, moves
DD by ~0. Close direction oc_i2_spreadveto.

## Vietnamese verdict (3 lines)
- S1 (veto spread-p90) KHONG THE kiem dinh: archive bookdepth khong co
  cot spread (chi co notional 1/2/5%) -> loai, khong phai ung vien.
- S2 (veto depth-p10) REJECT: mat -0.28 tong dev4 (gate +0.273), chi dat
  sum 3/4 nam dev (1/2 tren overlap 2023-2024), DD gan nhu khong doi.
- Khong chay engine 4-phase / khong cham nam 2025 vi screen truot; huong
  dong lai: can prospective paper evidence, khong adopt.
