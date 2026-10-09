# oc_b7btceth — REPORT (2026-10-08; PLAN frozen before any outcome)

BTC/ETH-only boost (IDEAS7 #5, rank 5, prior 11%): base = B7 (dip budget x1.5
for 7 days after a > 4 sigma 4h close-to-close move, verbatim oc_cascadedelay
definition, market-wide per shift). The B7 window is reused read-only from the
frozen parquets; the ONLY new logic is the coin mask: V1 boosts BTC+ETH rungs
only (mask {0,1}), V2 boosts BTC rungs only (mask {0}); other coins keep base
size in the window. Coin sets frozen ex-ante (never pick best coin ex-post).
No sizing-model change (NOT oc_corrbudget/governor). Book untouched.

CONTAMINATION LABEL (pre-registered): anything derived from the cascade
results is contaminated for 2021-2026. The PRIMARY, clean test is the
pre-sample replica 2017 .. 2020-09-23 (unseen when the cascade idea was
formed). The 2021-2026 replica below is a LABELLED, contaminated secondary
(info only). No engine was run (neither variant met the frozen pre-sample
beater rule).

STATUS: DONE — primary pre-sample replica + 1000 timing/block perms per
variant/year + stop split (reused kinds, no new 1m) + per-coin dSum complete;
secondary 2021-2026 replica complete; NO ENGINE (negative result, valid).

## PRIMARY — pre-sample replica (clean; reused ledger n = 9731, base sums reproduce)

| year x variant | n | base | norm_V | gain vs base | gain vs B7 | timing pct | block pct | boosted fills% |
|---|---|---|---|---|---|---|---|---|
| Y2017 V1 / V2 | 909 | 2.313362 | 2.359275 / 2.337938 | +0.046 / +0.025 | +0.000 / -0.021 | 100.0 / 99.9 | 100.0 / 99.0 | 65.2 / 30.5 |
| Y2018 V1 / V2 | 2986 | 2.678870 | 2.665628 / 2.543575 | -0.013 / -0.135 | -0.091 / -0.213 | 100.0 / 95.9 | 99.8 / 95.6 | 40.8 / 19.3 |
| Y2019 V1 / V2 | 3115 | 0.577643 | 0.592513 / 0.646035 | +0.015 / +0.068 | -0.096 / -0.043 | 91.2 / 96.8 | 89.5 / 97.4 | 37.6 / 18.6 |
| Y2020p V1 / V2 | 2721 | 0.297538 | 0.234658 / 0.197857 | -0.063 / -0.100 | +0.007 / -0.030 | 40.0 / 13.4 | 40.0 / 14.1 | 34.3 / 16.5 |

- Helps vs base (gain>0): V1 2/4 (2017, 2019), V2 2/4 (2017, 2019).
  B7 helps 3/4 on the same ledger (all but Y2020p).
- Beats B7 in-year: V1 1/4 on a tie-plus-dust basis (only the COVID leg
  Y2020p, +0.007; Y2017 is exactly +0.000 because that ledger leg holds
  BTC+ETH fills only incl. warm-up, so V1 == B7 there BY CONSTRUCTION).
  V2 beats B7 0/4. Sum4 norm: V1 5.852 / V2 5.725 vs B7 6.033
  (gain vs B7: V1 -0.181, V2 -0.308). Frozen beater rule
  (sum4 norm_V > sum4 norm_B7) FAILS for both — no engine.
- Timing significant (>=95): V1 2/4 (2017, 2018), V2 3/4 (2017, 2018, 2019).
  Timing survives masking, but the LEVEL (normalised gain) does not: the
  masked-out alt-coin fills carried part of the B7 edge.
- COVID leg Y2020p separately: V1 trims the B7 loss by +0.007 (dust), V2 is
  worse than B7 (-0.030) and worse than no boost (-0.100). Masking alts does
  not guard the crash leg.
- Per-coin sum4 (normalised, gain vs base): BTC 1.518 (+0.054, shared by both
  variants), ETH 2.262 (+0.123, V1 only), BNB 1.066 (+0.000), XRP 1.199
  (+0.000). The edge IS present in BTC+ETH fills — but the alt fills B7
  boosted were also profitable, so dropping them nets negative vs plain B7.
  (No ex-post coin picking: masks frozen; this breakdown is diagnostic.)

## Boosted-fill stop rate (reused verbatim mu=1.0 kinds; 15 unknown of 9731)

| year | base stop% | V1 boosted (delta) | V2 boosted (delta) | B7 boosted (delta, ref) |
|---|---|---|---|---|
| Y2017 | 3.30 | 1.69 (-1.61) | 1.08 (-2.22) | 1.69 (-1.61) |
| Y2018 | 3.29 | 3.29 (+0.00) | 4.51 (+1.22) | 3.55 (+0.26) |
| Y2019 | 6.69 | 7.53 (+0.84) | 8.46 (+1.77) | 7.47 (+0.78) |
| Y2020p | 7.58 | 9.87 (+2.29) | 11.58 (+4.00) | 9.13 (+1.55) |
| pooled | 5.58 | 5.88 (+0.30) | 6.91 (+1.33) | 6.20 (+0.62) |

- V1 pooled stop delta +0.30pp (lighter than B7's +0.62pp) but Y2020p boosted
  stops +2.3pp (B7 +1.5pp). V2 CONCENTRATES crash risk: pooled +1.33pp,
  Y2020p +4.0pp — BTC-only boosted fills in the crash leg stop out hardest.

## SECONDARY — 2021-2026 replica (CONTAMINATED, info only; ledger n = 22312)

| year x variant | base | norm_V V1/V2 | gain vs base | gain vs B7 | timing pct |
|---|---|---|---|---|---|
| 2021 V1 / V2 | 0.911273 | 1.055 / 0.986 | +0.144 / +0.075 | -0.017 / -0.086 | 99.8 / 99.1 |
| 2022 V1 / V2 | 0.832599 | 0.852 / 0.834 | +0.019 / +0.001 | +0.008 / -0.009 | 90.9 / 92.0 |
| 2023 V1 / V2 | 2.099814 | 1.968 / 2.026 | -0.131 / -0.074 | -0.107 / -0.050 | 41.3 / 37.6 |
| 2024 V1 / V2 | 3.197390 | 3.203 / 3.186 | +0.005 / -0.011 | -0.122 / -0.139 | 100.0 / 100.0 |
| 2025 V1 / V2 | 0.677229 | 0.645 / 0.627 | -0.032 / -0.050 | -0.119 / -0.136 | 93.2 / 81.8 |

- Dev4 (2021-2024) sum vs B7: V1 -0.238, V2 -0.284 — both LOSE the 2021-2024
  gains on the contaminated leg too. dSum5y vs B7: V1 -0.357, V2 -0.420
  (vs base: V1 +0.924, V2 +0.386; B7 itself is +2.95 vs base).
- Per-coin secondary dSum confirms the primary: masking alts gives back most
  of the B7 edge on BOTH legs. "Without losing the 2021-2024 gains" FAILS.

## Engine decision

NO ENGINE (pre-registered conditional): engine rows run ONLY for variants with
sum4 norm_V > sum4 norm_B7 on the PRIMARY pre-sample test. V1 -0.181 and V2
-0.308 both fail, so no `run_engine_btceth.py` / `analyze_btceth.py` exists
and no 4-phase rows were scored. This is a valid negative result, not a scope
cut.

## Leakage checklist

- Feature timing: B7 windows reuse frozen closes-only triggers (close_time <=
  tc, SIG excludes the tested bar, window strictly after tc); mask is a static
  per-coin flag known at signal time; truncation-tested on real pre-sample
  bars in tests/test_oc_b7btceth.py.
- Label windows: none fit anywhere (no harness join, no labels).
- Fit windows: no fits; threshold 4.0, windows 540/120, boost 1.5 x 7d, masks
  {0,1}/{0}, seeds 20261007+y/20261008+y, BLOCK 42 all frozen ex-ante/
  inherited, never scanned; no statistic from any test year feeds any choice.
  Pre-sample years were never used for any fit.
- Fill timing: replica fills inherited (live 16..238 strict trade-through,
  stop-first); stop kinds reused verbatim; perms reassign the UNDERLYING B7
  mults within (year, shift) only, mask applied deterministically.
- Coverage: no skipped year; all 9,731 pre-sample + 22,312 2021-2026 fills
  joined exactly (0 misses); 15 unknown kinds inherited, excluded from rates.
- Gate costs: inside the reused replica outcomes (maker 0.0002/taker 0.00055,
  adverse long funding 0.0001/8h); the variants are sizing-only overlays.
- Spot-vs-perp caveat on every pre-sample number (SPOT fills/exits, perp gate
  costs).

## What worked and what did not

- Did not work: BTC/ETH-only (V1) and BTC-only (V2) both lose to plain B7 on
  the clean years (sum4 -0.18/-0.31, helps 2/4 each vs B7's 3/4) AND on
  contaminated dev4 (-0.24/-0.28). The toxicity-heterogeneity mech is
  directionally visible (BTC +0.054, ETH +0.123 sum4 gains in masked fills)
  but the alt fills the mask drops were also profitable, so masking nets
  negative. V2 additionally concentrates stop risk (pooled +1.3pp, COVID leg
  +4.0pp).
- Barely visible: V1 trims the COVID-leg loss vs B7 by +0.007 — three orders
  of magnitude too small to matter, and V1 still loses vs no boost (-0.063)
  on that leg.
- Post-hoc fix (disclosed, no method/result change): added the missing
  `if __name__ == "__main__": main()` guard to
  `compute_replica_gate_btceth.py` after PLAN freeze (the file as first
  written defined main but never called it; no outcome existed yet for the
  secondary leg and no threshold/window/mask was touched).

## Vietnamese verdict

Cả hai biến thể coin-mask đều THUA B7 trên 4 năm sạch chưa từng thấy (sum4 V1
-0,18, V2 -0,31; mỗi biến thể chỉ giúp 2/4 năm so với 3/4 của B7) và cũng mất
gains 2021-2024 ở leg nhiễm (dev4 -0,24/-0,28); V2 còn gom rủi ro stop
(pooled +1,3pp, chân COVID +4,0pp).
Edge có trong fill BTC+ETH nhưng fill alt bị loại cũng lời nên mask ròng âm —
giả thuyết "edge chỉ ở deep books" sai ở mức replica.
Kết luận: REJECT — đóng hướng BTC/ETH-only, giữ nguyên B7, không engine,
không triển khai.
