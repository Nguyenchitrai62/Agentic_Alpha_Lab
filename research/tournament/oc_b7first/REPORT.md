# oc_b7first — REPORT (2026-10-08; PLAN frozen before any outcome)

First-cascade-only boost, no stacking (IDEAS7 #3, rank 3, prior 14%): base = B7
(dip budget x1.5 for 7 days after a > 4 sigma 4h close-to-close move, verbatim
oc_cascadedelay definition, market-wide per shift). Boost fires only from a
cascade with NO cascade in the prior N days (prior = ANY trigger); re-fires
inside the window neither stack nor extend (dropped). F14 N = 14 (V1);
F7 N = 7 (V2). Both frozen. Book untouched.

CONTAMINATION LABEL (pre-registered): anything derived from the cascade results
is contaminated for 2021-2026. The PRIMARY, clean test is the pre-sample
replica 2017 .. 2020-09-23 (unseen when the cascade idea was formed). The
2021-2026 replica below is a LABELLED, contaminated secondary (info only).
No engine was run (neither variant met the frozen pre-sample beater rule).

STATUS: DONE — pre-sample triggers + replica + 1000 timing/block perms per
variant/year + stop split (reused kinds, no new 1m) complete; secondary
2021-2026 replica complete; NO ENGINE (negative result, valid). Tests pass
(see bottom).

## Triggers (frozen, causal, verbatim arithmetic)

- Pre-sample raw fires reproduce oc_cboostpre exactly (915 total; BTC
  57/61/61/66, ETH 55/66/65/64, BNB 52/50/49/54, XRP 55/53/57/50 per shift
  s0..s3). Union per shift: s0 142 / s1 154 / s2 143 / s3 156 (same cascades as
  B7; the filter only drops re-fires). Qualifying: F14 28/26/27/29 per shift;
  F7 42/50/41/47 per shift.
- 2021-2026 raw fires 2112 (5 sym x 4 shifts); union per shift s0 264 / s1 266
  / s2 263 / s3 255 — IDENTICAL to oc_cascadeboost, confirming verbatim
  arithmetic. Qualifying: F14 31/32/30/32; F7 55/57/57/53 per shift.
- Boosted time-bar share pre-sample: F14 9-21 %/(yr,shift), F7 17-38 %
  (B7 34-54 %). Boosted FILL share is higher (F14 11-34 %, F7 40-50 %;
  B7 65-74 %): fills cluster in volatile downdrafts. F mults are strict
  subsets of B7 (every F-boosted bar is B7-boosted; tested).
- `boost_mult_presample_first.parquet`: 27,383 rows; mults in {1.0, 1.5};
  F14 subset of F7. `boost_mult_4shift_first.parquet`: 53,877 rows.

## PRIMARY — pre-sample replica (clean; reused ledger n = 9731, base sums reproduce)

| year x variant | n | base | norm_F | gain vs base | gain vs B7 | timing pct | block pct | boosted fills% |
|---|---|---|---|---|---|---|---|---|
| Y2017 F14 / F7 | 909 | 2.313362 | 2.342618 / 2.372531 | +0.029 / +0.059 | -0.017 / +0.013 | 56.9 / 100.0 | 57.9 / 99.1 | 11.4 / 39.7 |
| Y2018 F14 / F7 | 2986 | 2.678870 | 2.389763 / 2.514210 | -0.289 / -0.165 | -0.367 / -0.243 | 6.3 / 85.3 | 10.7 / 80.4 | 34.1 / 48.1 |
| Y2019 F14 / F7 | 3115 | 0.577643 | 0.619106 / 0.405133 | +0.041 / -0.173 | -0.070 / -0.284 | 74.4 / 10.0 | 75.1 / 9.7 | 25.8 / 49.7 |
| Y2020p F14 / F7 | 2721 | 0.297538 | 0.289768 / 0.103599 | -0.008 / -0.194 | +0.062 / -0.124 | 48.6 / 9.6 | 47.1 / 10.1 | 25.7 / 44.6 |

- Helps vs base (gain>0): F14 2/4 (2017, 2019), F7 1/4 (2017 only).
  B7 helps 3/4 on the same ledger (all but Y2020p).
- Beats B7 in-year: F14 1/4 (only the COVID leg Y2020p, +0.062), F7 1/4 (only
  Y2017, +0.013). Sum4 norm: F14 5.641 / F7 5.395 vs B7 6.033
  (gain vs B7: F14 -0.392, F7 -0.637). Frozen beater rule (sum4 norm_F >
  sum4 norm_B7) FAILS for both — no engine.
- Timing significant (>=95): F14 0/4, F7 1/4 (Y2017 only; B7 has 2/4).
  Dropping the re-fires destroys the timing edge: most of the post-cascade
  profit sits exactly in the stacked windows the filter removes.
- COVID leg Y2020p separately: F14 trims the loss vs B7 (+0.062, the filter
  skips levering the crash cluster) but still loses vs no boost (-0.008);
  F7 is worse than both (-0.194 vs base, -0.124 vs B7). The crash-leg guard
  hypothesis is directionally visible only for N=14 and far too small to matter.

## Boosted-fill stop rate (reused verbatim mu=1.0 kinds; 15 unknown of 9731)

| year | base stop% | F14 boosted (delta) | F7 boosted (delta) | B7 boosted (delta, ref) |
|---|---|---|---|---|
| Y2017 | 3.30 | 0.00 (-3.30) | 1.39 (-1.92) | 1.69 (-1.61) |
| Y2018 | 3.29 | 4.71 (+1.42) | 3.55 (+0.26) | 3.55 (+0.26) |
| Y2019 | 6.69 | 6.87 (+0.18) | 9.77 (+3.08) | 7.47 (+0.78) |
| Y2020p | 7.58 | 11.32 (+3.74) | 11.56 (+3.98) | 9.13 (+1.55) |
| pooled | 5.58 | 6.94 (+1.36) | 7.62 (+2.04) | 6.20 (+0.62) |

- The first-cascade filter CONCENTRATES crash risk: pooled stop delta F14
  +1.36pp / F7 +2.04pp vs B7 +0.62pp on a 5.6 % base; Y2020p boosted stops
  +3.7/+4.0pp (B7 +1.5pp). Keeping only the first window keeps the flush
  entries and drops the rebound windows that dilute the stop rate.

## SECONDARY — 2021-2026 replica (CONTAMINATED, info only; ledger n = 22312)

| year x variant | base | norm_F F14/F7 | gain vs base | gain vs B7 | timing pct |
|---|---|---|---|---|---|
| 2021 F14 / F7 | 0.911273 | 0.902098 / 0.983357 | -0.009 / +0.072 | -0.170 / -0.089 | 76.1 / 91.0 |
| 2022 F14 / F7 | 0.832599 | 0.594831 / 0.661292 | -0.238 / -0.171 | -0.248 / -0.182 | 2.5 / 10.8 |
| 2023 F14 / F7 | 2.099814 | 1.899824 / 1.918455 | -0.200 / -0.181 | -0.176 / -0.157 | 12.7 / 17.5 |
| 2024 F14 / F7 | 3.197390 | 3.209796 / 3.234621 | +0.012 / +0.037 | -0.115 / -0.090 | 99.3 / 100.0 |
| 2025 F14 / F7 | 0.677229 | 0.885460 / 0.936574 | +0.208 / +0.259 | +0.122 / +0.173 | 100.0 / 100.0 |

- Dev4 (2021-2024) sum vs B7: F14 -0.709, F7 -0.518 — both LOSE the 2021-2024
  gains on the contaminated leg too (only the post-release year 2025 beats B7,
  which is the labelled diagnostic and proves nothing).
- dSum5y vs B7: F14 -2.214, F7 -1.374 (vs base: F14 -0.23, F7 +0.64; B7 itself
  is +2.95 vs base). The filter gives back most of the B7 edge everywhere
  except the post-release year.

## Engine decision

NO ENGINE (pre-registered conditional): engine rows run ONLY for variants with
sum4 norm_F > sum4 norm_B7 on the PRIMARY pre-sample test. F14 -0.392 and F7
-0.637 both fail, so no `run_engine_first.py` / `analyze_first.py` exists and
no 4-phase rows were scored. This is a valid negative result, not a scope cut.

## Leakage checklist

- Feature timing: triggers use closes with close_time <= tc only; SIG window
  excludes the tested bar; first-filter uses only triggers with close <= tc;
  boost window strictly after tc; truncation-tested on real pre-sample bars
  (triggers + qualifying flags identical on kept prefix).
- Label windows: none fit anywhere (no harness join, no labels).
- Fit windows: no fits; threshold 4.0, windows 540/120, boost 1.5 x 7d,
  N = 14/7, seeds 20261007+y/20261008+y, BLOCK 42 all frozen ex-ante/inherited,
  never scanned; no statistic from any test year feeds any choice. Pre-sample
  years were never used for any fit.
- Fill timing: replica fills inherited (live 16..238 strict trade-through,
  stop-first); stop kinds reused verbatim; perms reassign mults within
  (year, shift) only.
- Coverage: no skipped year; all 9,731 pre-sample + 22,312 2021-2026 fills
  joined exactly (0 misses); 15 unknown kinds inherited, excluded from rates.
- Gate costs: inside the reused replica outcomes (maker 0.0002/taker 0.00055,
  adverse long funding 0.0001/8h); the variants are sizing-only overlays.
- Spot-vs-perp caveat on every pre-sample number (SPOT fills/exits, perp gate
  costs).

## What worked and what did not

- Did not work: first-cascade-only loses to plain B7 on the clean years
  (sum4 -0.39/-0.64, helps 2/4 and 1/4 vs B7's 3/4, timing 0/4 and 1/4 vs 2/4)
  AND on contaminated dev4 (-0.71/-0.52). The profit lives in the stacked
  windows: re-fires mark the volatile downdrafts where dip fills cluster, so
  skipping them cuts the edge while concentrating stop risk (+1.4/+2.0pp
  pooled vs +0.6pp for B7).
- Barely visible: F14 trims the COVID-leg loss vs B7 (+0.062) — the crash-leg
  guard mech exists but is an order of magnitude too small to pay for the
  edge given up in 2017-2019.
- Tests: 11 pass (`tests/test_oc_b7first.py`: hand-checked
  trigger/sigma/qualifying/no-stack/no-extend/boundary cases + truncation
  causality on real bars + parquet subset invariants + replica reproduction
  gate vs frozen oc_cboostpre B7 norms).

## Vietnamese verdict

Cả hai biến thể first-cascade-only đều THUA B7 trên 4 năm sạch chưa từng thấy
(sum4 F14 -0,39, F7 -0,64; chỉ thắng B7 đúng 1/4 năm mỗi biến thể, timing
0/4 và 1/4) và cũng mất luôn gains 2021-2024 ở leg nhiễm (-0,71/-0,52 dev4),
đồng thời gom rủi ro stop (pooled +1,4/+2,0pp so với +0,6pp của B7, chân COVID
+3,7/+4,0pp).
Lợi nhuận nằm đúng ở các window chồng nhau mà filter loại bỏ — giả thuyết
"re-fire = crash leg" sai ở mức replica.
Kết luận: REJECT — đóng hướng first-cascade-only, giữ nguyên B7, không engine,
không triển khai.
