# oc_i2_oiguard REPORT — OI-unwind dip-bid guard (IDEAS2_20261007 §2)

## 0. PRE-REGISTRATION (frozen BEFORE any outcome; 2026-10-07)

Idea: skip NEW dip bids when 24h OI drops >2σ AND price drops >2σ (crowded
unwind = positioning as skip, not member). Not a repeat: DATA LEADERBOARD
positioning member (+0.12 in 2023 only, closed as member), oc_velocity guard
(CLOSED), oc_cooldown cascade-fuse-only, oc_postflush (<10 events/yr floor).
Exactly 2 variants, no others:
- O1: skip new bids on guard-fired (phase, coin, bar) bars (holds/exits unchanged).
- O2: O1 + 1-bar re-entry delay (a fired bar also skips the next bar of the
  same phase/coin; no chasing, no re-peg).
Frozen guard (per phase p, coin c, 4h bar open T, bar index j on that phase grid):
- OI_now = sum_open_interest(c) at last create_time <= T-5min (5-min lag per
  metrics_ext manifest note); OI_24h = same at <= T-24h-5min.
  dOI = ln(OI_now/OI_24h), NaN if either missing/non-positive.
- dPx = ln(o1[j]/o1[j-6]) from the replica's own causal bar opens (24h on 4h grid).
- Trailing window: up to 540 prior bars (90d) of dOI / dPx on the same (p,c)
  grid, strictly before j; need >=60 finite each and sd>0, else NO fire.
- z = (x-trailing_mean)/trailing_sd; FIRE iff z_OI < -2.0 AND z_Px < -2.0.
- Threshold 2.0 fixed (not fitted); trailing stats use only data <= T;
  OI vintages used as-of (no restatement); embargo satisfied (dip horizon <4h,
  all stats strictly pre-T). Missing/short-history bars (ETH/SOL/BNB/XRP OI
  starts 2021-12-01) default to NO fire (no imputation).
Replica (audited blocks only): oc_placebo_dip exact D0+B1 4-phase replica
(TP 1sg, close5 stop 4sg, 8sg backstop, timeout next-bar open; maker
0.0002/taker 0.00055; v293 settle funding; B1 sizes w=1/(1+n); majors x R2
2.5..5.0; live 16..238 strict trade-through; bars open [2021-09-24,2026-09-24);
4 clock phases from 2020-08-01 +0/1/2/3h). Kept fills keep price/size/exits;
guard = subset sums, NO renormalisation. Minute-5 fill ban kept (live>=16).
Daily sums of w*y by exit date; per-year 4-phase means (S, DD of cumulative
daily-sum path from 0).
Screen-pass rule (pre-registered, dev4 2021-2024 ONLY): PASS iff ALL of
(a) sum_leg: S_var >= S_base in >=3/4 dev years;
(b) dd_leg: DD_var <= DD_base + 0.01 in >=3/4 dev years;
(c) effect: dev4 4-phase-mean sum delta >= +0.273 (full 5y pooled placebo p95
from oc_placebo_dip, applied strictly on four years).
Choose O1 vs O2 on dev4 ONLY (robust spirit: passer wins; both pass -> higher
dev4 dSum, tie -> lower dev4 DD; neither passes -> NO chosen variant, NO
engine, NO 2025 variant scoring). Score 2025-09-24..2026-09-23 ONCE for the
chosen variant only, labelled POST-HOC. 4-phase engine only if the screen
passes. Gate costs for any engine row: maker 0.02%, taker 0.055%, longs pay
0.01%/8h. Baseline first: reproduce G2+carry (5.634/DD16.75/full16.66,
oc_carrycompound) or G2 (5.41) exactly, else stop and report.
(PENDING: results below filled after the single run; no post-hoc variant.)

## 1. Baseline reproduction (gate, read-only; no engine rerun)

PASS. `run_oiguard.py` step 0 loads `oc_carrycompound/results.json` and
`v421/v421_result.json` and asserts to the digit (exits 2 = STOP otherwise):
G2+carry f=0.25: R 5.634 / W 2.778 / DD 16.75 / losing 0 /
full-path DD marked 16.66 / close 15.90 / full 16.66; G2 f=0: R 5.410 /
W 2.588 / DD 16.91 / full 16.82 (= v421 R2B1D17BFG2 years/D years/full DD).
Carry add +0.224 pp/mo. Assertion passed, run continued.

## 2. Replica fidelity

Ledger 22312 fills (= oc_placebo_dip 22312 = oc_stoptf n_rungs).
Phase-0 raw sums 2.3881/0.1829/3.8098/2.5793/0.7115 = oc_velocity B1
(2.388/0.183/3.810/2.579/0.712) to 1e-3. 4-phase-mean sums
0.9113/0.8326/2.0998/3.1974/0.6772 = oc_placebo_dip base
(0.911/0.833/2.100/3.197/0.677) to 1e-3. Checksum differs from placebo's only
because the hash covers (w,y10) vs their (w,y09,y10,y11); fill count and all
compared sums agree, so the guard comparison is on the audited replica.
OI: `sum_open_interest` as-of <= T-5min per coin; BTC eligible ~13194/13470
grid bars, ETH/SOL/BNB/XRP ~10470 (OI history starts 2021-12-01; pre-history
bars default NO fire, no imputation). Fires per (phase,coin) over the full
grid: BTC ~91-99, ETH ~61-66, SOL ~42-49, BNB ~46-50, XRP ~74-82 (~0.5-0.7%
of eligible bars — thin by construction). O1 removed 511 fills (2.3%),
O2 715 (3.2%).

## 3. Screen: base vs O1 vs O2 (dev4 selection; 2025 once for chosen only)

Per-year 4-phase-mean sums S (w*y) / DD, dev4 = anchors 2021-2024:
| year | base S | O1 S (d) | O2 S (d) |
|---|---|---|---|
| 2021-09-24 | 0.9113 | 0.8730 (-0.038) | 0.9807 (+0.069) |
| 2022-09-24 | 0.8326 | 0.7743 (-0.058) | 0.7491 (-0.083) |
| 2023-09-24 | 2.0998 | 2.0533 (-0.047) | 2.1816 (+0.082) |
| 2024-09-24 | 3.1974 | 3.0873 (-0.110) | 3.0133 (-0.184) |
DD leg (tol +0.01): O1 4/4, O2 4/4 (guard barely moves dip-sleeve DD).
Sum leg: O1 0/4, O2 2/4. dev4 dSum: O1 -0.253, O2 -0.116 vs gate +0.273.
Neither variant passes the pre-registered screen (need sum>=3/4 AND dd>=3/4
AND dSum>=+0.273). O1 loses edge in ALL four dev years: the guard deletes net
winning rungs (same failure mode as the oc_velocity guard, whose removed rungs
won 76%). O2's delay mixes one positive year with deeper losses elsewhere.
Chosen variant: NONE. Per protocol, 2025 is masked for both variants (2025
scored once for the chosen variant only; there is none). Base 2025 replica
context (already published shape): S 0.6772 / DD 0.6073.
4-phase engine: NOT RUN (screen-gated; screen failed).

## 4. Reset metric + full-path DD (v421/v422 convention)

No variant engine run exists, so this row restates the reproduced frozen
baseline (reset_metric.year_reset per anchor year, v421 continuous full-path
DD) that any future engine comparison must beat:
G2+carry f=0.25 per anchor R/DD: 2021 2.778/10.86, 2022 3.353/16.75,
2023 6.590/15.69, 2024 10.956/8.20, 2025 4.698/12.66 (POST-HOC, published);
5y R 5.634 / W 2.778 / maxDD 16.75 / losing 0; full-path DD 16.66.
Gate costs for reference: maker 0.02%, taker 0.055%, longs pay 0.01%/8h.

## 5. Verdict

NOT PROMISING — the OI-unwind guard (joint 24h OI+price <-2sigma skip) removes
net-winning dip rungs in 4/4 dev years (O1 dSum -0.25) and is mixed-to-negative
with the re-entry delay (O2 dSum -0.12, 2/4 sums); DD is flat, effect is far
below the +0.273 placebo gate, events are thin (~0.5-0.7% of bars). Reject the
guard for the BOT dip sleeve; close direction §2 with no engine run and no
prospective-paper claim (a PROMISING tag would have needed prospective
validation anyway). Data note: ETH/SOL/BNB/XRP OI starts 2021-12-01, so early
2021 bars are guard-ineligible by construction — disclosed, not imputed.
Repro: `research/tournament/oc_i2_oiguard/{run_oiguard.py,results.json}` +
`tests/test_oc_i2_oiguard.py` (9 pass); heavy via `scripts/heavy_slot.py`.

Nhận định (3 dòng): Từ chối áp dụng bộ lọc OI-unwind cho dip sleeve BOT vì
màn hình dev4 cho delta tổng âm ở cả hai biến thể (O1 -0,25, O2 -0,12 so với
ngưỡng +0,273) dù DD không đổi. Không chạy engine 4-phase và không chấm năm
2025 cho biến thể nào, đúng quy tắc chọn chỉ trên 2021-2024. Hướng §2 đóng tại
đây; nếu muốn cứu vãn thì chỉ còn cách ghi paper-log prospective, không tinh
chỉnh thêm trên dữ liệu cũ.
