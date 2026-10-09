# oc_b7deep — REPORT (2026-10-08; PLAN frozen before any outcome)

Deep-rung-only boost, no veto (IDEAS7 #2, rank 2, prior 15%): base = B7
(dip budget x1.5 for 7 days after a > 4 sigma 4h close-to-close move, verbatim
oc_cascadedelay definition, market-wide per shift). During the B7 window ONLY
rungs >= X get 1.5x; shallow rungs stay at base size. V1 X = 3.5sg (ledger
ri >= 2: rungs 3.5/4.0/5.0); V2 X = 4.0sg (ri >= 3: rungs 4.0/5.0). Both frozen.
Book untouched. NOT oc_rungquality (that vetoed cells on stop rate; this is a
depth-threshold boost, no veto).

CONTAMINATION LABEL (pre-registered): anything derived from the cascade results
is contaminated for 2021-2026. The PRIMARY, clean test is the pre-sample
replica 2017 .. 2020-09-23 (unseen when the cascade idea was formed). The
2021-2026 replica below is a LABELLED, contaminated secondary (info only).
No engine was run (neither variant met the frozen pre-sample beater rule).

STATUS: DONE — pre-sample B7 rebuild (915 raw fires) + replica + 1000
timing/block perms per variant/year (window-flag null + frozen rung gate) +
stop split (reused kinds, no new 1m) complete; secondary 2021-2026 rebuild
(2112 raw fires) + replica complete; NO ENGINE (negative result, valid).
Tests: 10 pass (`tests/test_oc_b7deep.py`).

## Triggers (frozen, causal, verbatim arithmetic)

- Pre-sample raw fires reproduce oc_cboostpre exactly (915 total; BTC
  57/61/61/66, ETH 55/66/65/64, BNB 52/50/49/54, XRP 55/53/57/50 per shift
  s0..s3; rebuilt B7 flags equal the frozen cboostpre parquet on all 27,383
  rows). Deep-rung mix of fills: V1-deep (ri>=2) 35.6 %, V2-deep (ri>=3) 18.6 %.
- 2021-2026 raw fires 2112 (5 sym x 4 shifts); rebuilt B7 flags equal the
  frozen cascadeboost parquet on all 53,877 rows. Deep mix: V1 34.0 %,
  V2 17.3 % of fills.
- Deep-boosted FILL share (window AND deep rung): pre-sample V1 23.6-27.9 %
  (B7 65-74 %), V2 12.4-14.7 %; 2021-2026 V1 ~22.7 %, V2 ~11.8 % pooled.
  The gate binds on a minority of fills by construction.

## PRIMARY — pre-sample replica (clean; reused ledger n = 9731, base sums reproduce)

| year x variant | n | base | norm_V | gain vs base | gain vs B7 | timing pct | block pct | deep-boosted fills% |
|---|---|---|---|---|---|---|---|---|
| Y2017 V1 / V2 | 909 | 2.313362 | 2.389511 / 2.340277 | +0.076 / +0.027 | +0.030 / -0.019 | 100.0 / 100.0 | 100.0 / 100.0 | 25.5 / 13.6 |
| Y2018 V1 / V2 | 2986 | 2.678870 | 2.733785 / 2.701942 | +0.055 / +0.023 | -0.023 / -0.055 | 100.0 / 100.0 | 100.0 / 100.0 | 25.7 / 13.0 |
| Y2019 V1 / V2 | 3115 | 0.577643 | 0.578211 / 0.586533 | +0.001 / +0.009 | -0.110 / -0.102 | 66.6 / 64.5 | 58.9 / 55.8 | 23.6 / 12.4 |
| Y2020p V1 / V2 | 2721 | 0.297538 | 0.119078 / 0.132748 | -0.178 / -0.165 | -0.109 / -0.095 | 7.9 / 3.0 | 9.3 / 3.9 | 27.9 / 14.7 |

- Helps vs base (gain>0): V1 3/4 (all but Y2020p), V2 3/4 (all but Y2020p).
  B7 helps 3/4 on the same ledger (all but Y2020p) with larger gains
  (+0.046/+0.078/+0.111 vs V1 +0.076/+0.055/+0.001, V2 +0.027/+0.023/+0.009).
- Beats B7 in-year: V1 1/4 (only Y2017, +0.030), V2 0/4. Sum4 norm: V1 5.821 /
  V2 5.762 vs B7 6.033 (gain vs B7: V1 -0.212, V2 -0.271). Frozen beater rule
  (sum4 norm_V > sum4 norm_B7) FAILS for both — no engine.
- Timing significant (>=95): V1 2/4 (2017, 2018), V2 2/4 (2017, 2018);
  B7 has 2/4 with a near-miss third (2019 92.3). Deep gating keeps the 2017-2018
  timing but destroys the 2019 edge (66.6/64.5 vs B7 92.3) and stays dead in
  the COVID leg (7.9/3.0 vs B7 45.4).
- COVID leg Y2020p separately: both variants lose vs no boost (-0.178/-0.165,
  worse than B7's -0.069) AND vs B7 (-0.109/-0.095). Concentrating the boost on
  deep rungs levers the crash leg harder, not softer.

## Deep-boosted-fill stop rate (reused verbatim mu=1.0 kinds; 15 unknown of 9731)

| year | base stop% | V1 deep-boosted (delta) | V2 deep-boosted (delta) | B7 boosted (delta, ref) |
|---|---|---|---|---|
| Y2017 | 3.30 | 0.00 (-3.30) | 0.00 (-3.30) | 1.69 (-1.61) |
| Y2018 | 3.29 | 3.52 (+0.23) | 4.13 (+0.84) | 3.55 (+0.26) |
| Y2019 | 6.69 | 9.96 (+3.27) | 10.44 (+3.76) | 7.47 (+0.78) |
| Y2020p | 7.58 | 13.74 (+6.16) | 17.29 (+9.71) | 9.13 (+1.55) |
| pooled | 5.58 | 8.20 (+2.62) | 9.67 (+4.09) | 6.20 (+0.62) |

- The deep gate CONCENTRATES crash risk far beyond B7: pooled stop delta V1
  +2.62pp / V2 +4.09pp vs B7 +0.62pp on a 5.6 % base; Y2019 deep stops +3.3/+3.8pp
  (B7 +0.8pp); Y2020p deep stops +6.2/+9.7pp (B7 +1.5pp). Deep fills are where
  stops live: the "overshoot pays deep fills" mech runs the wrong way — the
  snapback does not compensate the extra stop rate at the replica level.
  (Y2017 0.0 % on 232/124 deep-boosted fills is the small-sample exception.)

## SECONDARY — 2021-2026 replica (CONTAMINATED, info only; ledger n = 22312)

| year x variant | base | norm_V V1/V2 | gain vs base | gain vs B7 | timing pct |
|---|---|---|---|---|---|
| 2021 V1 / V2 | 0.911273 | 0.924732 / 0.894030 | +0.013 / -0.017 | -0.147 / -0.178 | 68.9 / 29.5 |
| 2022 V1 / V2 | 0.832599 | 0.824944 / 0.820413 | -0.008 / -0.012 | -0.018 / -0.023 | 63.0 / 64.9 |
| 2023 V1 / V2 | 2.099814 | 2.047985 / 2.087388 | -0.052 / -0.012 | -0.027 / +0.012 | 71.5 / 88.3 |
| 2024 V1 / V2 | 3.197390 | 3.326444 / 3.263965 | +0.129 / +0.067 | +0.001 / -0.061 | 100.0 / 100.0 |
| 2025 V1 / V2 | 0.677229 | 0.762957 / 0.723827 | +0.086 / +0.047 | -0.001 / -0.040 | 97.2 / 97.6 |

- Dev4 (2021-2024) sum vs B7: V1 -0.192, V2 -0.250 — both LOSE the 2021-2024
  gains on the contaminated leg too (V1's only in-year win vs B7 is 2024
  +0.001; V2's is 2023 +0.012).
- dSum5y vs base: V1 +1.029, V2 +0.509 (B7 itself +2.946); vs B7: V1 -1.918,
  V2 -2.437. The deep gate gives back roughly two-thirds (V1) to four-fifths
  (V2) of the B7 edge while keeping the crash-leg concentration.
- Timing placebo is dead outside 2024 (V1 63-72, V2 29-88 where B7 shows
  96.6/100.0 in 2021/2024): randomising the window destroys what little deep
  edge exists, confirming the deep-boosted profit is not timing.

## Engine decision

NO ENGINE (pre-registered conditional): engine rows run ONLY for variants with
sum4 norm_V > sum4 norm_B7 on the PRIMARY pre-sample test. V1 -0.212 and V2
-0.271 both fail, so no `run_engine_deep.py` / `analyze_deep.py` exists and
no 4-phase rows were scored. This is a valid negative result, not a scope cut.

## Leakage checklist

- Feature timing: triggers use closes with close_time <= tc only; SIG window
  excludes the tested bar; window strictly after tc; rung gate uses the frozen
  signal-time ledger rung only (the rung IS the depth, known at signal time),
  never placement-window 1m; truncation-tested on real pre-sample bars.
- Label windows: none fit anywhere (no harness join, no labels).
- Fit windows: no fits; threshold 4.0, windows 540/120, boost 1.5 x 7d,
  X = 3.5/4.0 with ri cutoffs >=2/>=3, seeds 20261007+y/20261008+y, BLOCK 42
  all frozen ex-ante/inherited, never scanned; no statistic from any test year
  feeds any choice. Pre-sample years were never used for any fit.
- Fill timing: replica fills inherited (live 16..238 strict trade-through,
  stop-first); stop kinds reused verbatim; perms reassign window flags within
  (year, shift) only, rung gate re-applied after permutation.
- Coverage: no skipped year; all 9,731 pre-sample + 22,312 2021-2026 fills
  joined exactly (0 misses); 15 unknown kinds inherited, excluded from rates.
- Gate costs: inside the reused replica outcomes (maker 0.0002/taker 0.00055,
  adverse long funding 0.0001/8h); the variants are sizing-only overlays.
- Spot-vs-perp caveat on every pre-sample number (SPOT fills/exits, perp gate
  costs).

## What worked and what did not

- Did not work: deep-rung-only loses to plain B7 on the clean years (sum4
  -0.21/-0.27, beats-B7 1/4 and 0/4, timing 2/4 each with a dead 2019) AND on
  contaminated dev4 (-0.19/-0.25). The shallow fills the gate cuts carry a
  material share of the post-cascade profit, while the deep fills it keeps
  carry a much higher stop rate (pooled +2.6/+4.1pp vs +0.6pp for B7; COVID leg
  +6.2/+9.7pp). The "overshoot pays deep fills" hypothesis is backwards at the
  replica level: deep fills catch the falling knife more often than they catch
  the snapback.
- Barely visible: V1 beats B7 only in Y2017 (+0.030, the smallest pre-sample
  year) and ties it in contaminated 2024 (+0.001) — an order of magnitude too
  small to pay for the edge given up in 2018-2019 and the crash-leg stop
  concentration.
- Tests: 10 pass (`tests/test_oc_b7deep.py`: hand-checked
  trigger/sigma/deep-gate/X-boundary/no-veto cases + truncation causality on
  real bars + parquet B7-equality invariants + replica reproduction gate vs
  frozen oc_cboostpre B7 norms).

## Vietnamese verdict

Cả hai biến thể deep-rung-only đều THUA B7 trên 4 năm sạch chưa từng thấy
(sum4 V1 -0,21, V2 -0,27; chỉ thắng B7 đúng 1/4 năm với V1 ở 2017, V2 0/4) và
cũng mất luôn gains 2021-2024 ở leg nhiễm (dev4 -0,19/-0,25), đồng thời gom rủi
ro stop mạnh hơn B7 nhiều (pooled +2,6/+4,1pp so với +0,6pp của B7, chân COVID
+6,2/+9,7pp so với +1,5pp).
Lợi nhuận sau cascade nằm cả ở các rung nông mà gate loại bỏ — giả thuyết
"overshoot trả tiền cho fill sâu" sai ở mức replica.
Kết luận: REJECT — đóng hướng deep-rung-only, giữ nguyên B7, không engine,
không triển khai.
