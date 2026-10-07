# oc_i2_tapecancel REPORT — IDEAS2_20261007 §3 tape-contingent dip-bid cancel

## PRE-REGISTRATION (frozen 2026-10-06T19:34:35Z, BEFORE any outcome is computed)

Idea: IDEAS2_20261007.md §3 (BOT execution). Nearest closed: oc_bidttl
(FIXED 2h TTL 0/5), oc_fillttl, oc_earlystart (early ENTRY fragile). This is
STATE-contingent cancel, not fixed TTL and not early entry: an unfilled rung
is cancelled at +30m/+60m after the live window opens IF the post-placement
taker-sell share exceeds a trailing-30d quantile; never re-pegged same bar
(no chasing per rules). Depths/stops/TP unchanged.

Pre-registered variants (exactly 2, no others):
- C1: cancel at +30m (cancel minute K1 = 46) on p80. Tape window = 1m bars
  with open in (T+16, T+46] (30 bars, strictly after live-open minute 16,
  closed before the cancel decision). Rungs with fill f <= 46 keep the exact
  replica fill; rungs with f > 46 are cancelled (claim no fill) iff toxic.
- C2: cancel at +60m (cancel minute K2 = 76) on p90. Tape window = 1m opens
  in (T+16, T+76] (60 bars). Rungs with f <= 76 kept; f > 76 cancelled iff
  toxic.
- Toxicity: s30 (C1) = sum(sell)/(sum(buy)+sum(sell)) notional over the 30m
  window of the rung's OWN coin (Binance aggTrades 1m size store
  data/raw/aggflow_20260929_orders_1m); toxic iff s30 > q80, where q80 =
  80th percentile (linear) of s30 over trailing-30d same-coin bars with open
  in [T-30d, T-4h] (causal: every sample bar's tape ends before T opens;
  >= 30 samples required else never cancel). C2 identical with s60/q90.
- Rationale for placement=live-open-16: the replica live window is 16..238;
  the minute-5 fill ban is kept trivially (16 > 5); tape is strictly
  post-placement and pre-cancel; no re-pegging.

Replica (deployed baseline, oc_bidttl/oc_placebo_dip-exact): majors
(BTC/ETH/SOL/BNB/XRP) x R2 depths 2.5..5.0, B1 sizes w=1/(1+n_fill) with
v399-exact n, strict low<lv trade-through fills on live 16..238, D0 exits
(TP lv*(1+sg) maker; close5 stop 4sg / backstop 8sg taker; timeout next open
taker; 0.0001 funding on settling timeouts; stop-first priority), gate costs
maker 0.0002 / taker 0.00055, 4 clock phases (4h grid from 2020-08-01
+0/1/2/3h), bars with open in [2021-09-24, 2026-09-24). v421-style G=2.0
gross-cap walk per (phase,bar) ordered by (f,k,coin), cut to room, skip when
full; PRIMARY = cap-adjusted wk*y daily sums by exit date; 4-phase means.
Placebo gate: 5y sum delta dSum5y >= +0.273 (oc_placebo_dip pooled p95).

Baseline gate (step 0): reproduce G2+carry (5.634 %/mo / DD 16.75 / full
16.66, oc_carrycompound) with f=0 == G2 (5.41) == v421_result R2B1D17BFG2 to
the digit, else STOP and report.

Selection protocol (AGENTS.md 2026-09-27): compare and choose C1 vs C2 ONLY
on dev years 2021-2024 (bar-open years Y0..Y3). Robust criterion adapted to
screen units: eligible iff (i) DD leg on dev4: DD_rule <= DD_base+0.01 in 4/4
dev years (no worse tail), and (ii) sum leg on dev4: S_rule >= S_base in
>=3/4 dev years; among eligible pick the highest dev4 WORST-year sum delta,
ties -> higher dev4 mean delta. If none eligible, BOTH rejected, no 2025
scoring, no engine. The chosen variant (if any) is scored on
2025-09-24..2026-09-23 ONCE, labelled POST-HOC. Screen PROMISING (engine
gate) iff the chosen variant additionally clears the joint legs on 5y
(sum>=base 4/5 AND DD<=base+0.01 4/5 AND dSum5y>=+0.273). 4-phase engine
(reset_metric + full-path DD like v421/v422) ONLY if PROMISING.

Leak audit (pre-registered): tape minutes strictly after placement (16) and
at/before cancel (46/76); thresholds from bars with open <= T-4h only;
depths from sigma360 (pct_change().rolling(360).std().shift(1)) <= bar close;
minute-5 ban kept; cancels claim no fill; no statistic from a test year
feeds any choice (no fitting anywhere: 30m/60m/p80/p90/30d all fixed here).

Outputs: research/tournament/oc_i2_tapecancel/{tapecancel.py,
run_tapecancel.py, results.json, fills.parquet, REPORT.md (this file)} +
tests/test_oc_i2_tapecancel.py. Scratch only under tmp/. Heavy steps via
scripts/heavy_slot.py. No commits. No touch of artifacts/bot/*, bot/ code,
credentials; no orders.

## STATUS: run complete (Stage A dev4 only; Stage B 2025 unscored — no dev-eligible variant)

## RESULTS (all computed AFTER the frozen pre-registration above)

### Step 0 — baseline reproduced exactly (else would have stopped)
G2+carry f=0.25: 5.634 %/mo / DD 16.75 / full-path DD 16.66; f=0 == G2 5.41 /
W 2.588 / DD 16.91 == v421_result R2B1D17BFG2 per-year R/WD to the digit
(asserted in-script from research/tournament/oc_carrycompound/results.json).
Reset-metric years (R %/mo / DD %): 2021 2.778/10.86, 2022 3.353/16.75, 2023
6.590/15.69, 2024 10.956/8.20, 2025 4.698/12.66 (POST-HOC reference only).

### Stage A — dev4 screen (bars open [2021-09-24, 2025-09-24); 17540 candidates)
Fidelity: phase-0 uncapped base raw sums 2.388052 / 0.182865 / 3.809764 /
2.579274 = oc_placebo_dip ref to 1e-6; base 4-phase-mean sums/DD per year =
oc_bidttl base exactly. Tape: Binance aggTrades 1m
(data/raw/aggflow_20260929_orders_1m, no re-download); toxic-bar rate ~21%
(C1) as designed. Ledger checksum b9870becf4e0e1a9.

| year | S_base | S_C1 | dS_C1 | S_C2 | dS_C2 | DD_b | DD_C1 | DD_C2 | sC1/sC2 | dC1/dC2 |
|---|---|---|---|---|---|---|---|---|---|---|
| 2021-09-24 | 0.5069 | 0.4593 | -0.0476 | 0.3069 | -0.2000 | 0.3463 | 0.3170 | 0.3384 | 0/0 | 1/1 |
| 2022-09-24 | 0.2708 | 0.2093 | -0.0615 | 0.1834 | -0.0874 | 0.4639 | 0.5036 | 0.4451 | 0/0 | 0/1 |
| 2023-09-24 | 1.2960 | 1.0513 | -0.2447 | 1.3208 | +0.0248 | 0.2379 | 0.2008 | 0.1938 | 0/1 | 1/1 |
| 2024-09-24 | 1.1702 | 1.1278 | -0.0424 | 1.1248 | -0.0454 | 0.2409 | 0.2391 | 0.2409 | 0/0 | 1/1 |

s = PASS_sum (S_rule >= S_base), d = PASS_dd (DD <= base+0.01), cap-adjusted
4-phase means. C1: sums 0/4, dd 3/4 (2022 +0.0397 worse), dSum_dev4 -0.3962.
C2: sums 1/4 (only 2023 +0.0248), dd 4/4, dSum_dev4 -0.3080.
Cancelled fills ("dodged losers") win 60-72% every year with POSITIVE sums
(C1 lost_sum +0.36/+0.05/+0.98/+0.65; C2 +0.64/+0.42/+0.11/+0.38) — the tape
filter discards winners, the same clean failure as oc_bidttl late fills.
Extra fills from freed cap headroom are non-zero but net-mixed (reported
exactly in results.json; 5y gate nowhere in reach).
Dev4 pooled full path (all phases, cap-adjusted): base n=7261 sum=12.9754
DD=1.4857 win=68.8%; C1 n=6568 sum=11.3906 DD=1.2207 win=69.1%; C2 n=6903
sum=11.7433 DD=1.3974 win=69.0%.

### Selection (dev4 ONLY, pre-registered robust rule)
C1 eligible=false (0/4 sums, 3/4 dd); C2 eligible=false (1/4 sums, 4/4 dd).
Need dd-ok 4/4 AND sum-pass >=3/4. chosen=null. Both rejected on dev4.

### Stage B 2025-09-24..2026-09-23: UNSCORED (no dev-eligible variant; per
protocol the most recent year is scored once for the chosen variant only —
there is none). No 5y dSum5y vs +0.273 computed for choice; for the record
neither variant could reach the gate from dev4 (C1 -0.396, C2 -0.308 dev4
alone already below +0.273 even with a perfect 2025).

### 4-phase engine: NOT RUN (screen not PROMISING — correct per "engine only
if the screen passes"). No reset-metric/full-path-DD engine rows to report
beyond the Step-0 baseline above.

### Leak audit (explicit)
Tape minutes strictly post-placement (offsets 17..46 / 17..76, live-open 16)
and at/before cancel (46/76); thresholds from bars with open in [T-30d, T-4h]
only (>=30 samples else never cancel); depths from sigma360
(pct_change().rolling(360).std().shift(1)) <= bar close; minute-5 ban kept
(live from 16); cancels claim no fill, never re-pegged; no statistic from any
test year fed any choice (all parameters frozen pre-run; NOTHING fitted).

## Verdict
VERDICT: NOT PROMISING — C1 loses cap-adjusted sums 4/4 dev years
(dSum -0.396), C2 loses 3/4 (dSum -0.308); cancelled fills win 60-72% yearly,
so adverse-selection cancel discards winners. Direction closed, no engine.

Kết luận (3 dòng):
REJECT — cả C1 và C2 đều thua base trên dev 2021–2024 (C1 0/4, C2 1/4 năm, dSum lần lượt -0.40/-0.31 so với ngưỡng +0.273).
Không có biến thể nào đạt chọn, năm 2025 nhất không được chấm, không chạy engine theo đúng protocol.
Hướng này đóng lại, không cần bằng chứng prospective thêm.
