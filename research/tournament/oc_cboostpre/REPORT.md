# oc_cboostpre — REPORT (2026-10-08; PLAN frozen before any outcome)

Does the post-cascade dip-budget boost (B7/B3, x1.5 after a > 4 sigma 4h close-to-close
move, frozen definition of oc_cascadedelay/oc_cascadeboost) help in the UNSEEN pre-sample
years 2017-2020? Pre-sample 4h closes (`oc_presampletilt/bars_4h_presample.parquet`, 4 syms,
SOL absent) + the reused D0+B1 dip replica ledger (9,731 fills; SPOT fills/exits, perp gate
costs inside). Diagnostic only: no selection, no engine, no adoption here.

CONTAMINATION LABEL (pre-registered): B7 was picked on dev4 after oc_cascadedelay's replica
had covered all five years incl. the post-release year, so post-release numbers are
diagnostics; these pre-sample years are the unseen evidence leg.

STATUS: DONE — triggers built (915 raw fires 4 sym x 4 shifts; union/shift/year below),
replica + 1000 timing/block perms per variant/year complete, stop-kind recompute complete
(15 unknown of 9,731). Tests: 12 pass (`tests/test_oc_cboostpre.py`).

## Triggers (frozen, causal, verbatim oc_cascadedelay arithmetic on pre-sample closes)

- Per (sym, shift): r[i] = ln(C[i]/C[i-1]); SIG[i] = std of r[i-540..i-1] (min_periods 120,
  tested bar excluded); fire iff |r[i]| > 4.0*SIG[i]; tc = T[i]+4h. Union over available
  majors per shift. Raw fires: BTC 57/61/61/66, ETH 55/66/65/64, BNB 52/50/49/54,
  XRP 55/53/57/50 (per shift s0..s3). Union triggers per (year, shift):

| year | s0 | s1 | s2 | s3 |
|---|---|---|---|---|
| Y2017 | 8 | 12 | 9 | 11 |
| Y2018 | 43 | 42 | 47 | 46 |
| Y2019 | 46 | 53 | 49 | 57 |
| Y2020p | 31 | 39 | 31 | 29 |

- Boosted time-bar share: B7 34-54 %/(yr,shift), B3 21-30 %/(yr,shift). Boosted FILL share
  is higher (B7 65-74 %, B3 47-51 %): dip fills cluster in the volatile downdrafts that
  follow big bars — the boost binds where the sleeve earns. Pooled boosted-fill share:
  B7 71.0 %, B3 49.6 %. Early bars with NaN SIG never fire (inert, counted).
- `boost_mult_presample.parquet`: 27,383 rows; mults in {1.0, 1.5}; B3 subset of B7.

## Replica (reused ledger n = 9731, base sums reproduce 2.313362/2.678870/0.577643/0.297538)

| year x variant | n | base | boosted | norm | gain | timing pct | block pct | boosted fills% |
|---|---|---|---|---|---|---|---|---|
| Y2017 B7 / B3 | 909 | 2.313362 | 3.128830 / 2.910837 | 2.359275 / 2.339479 | +0.045913 / +0.026117 | 100.00 / 100.00 | 100.00 / 100.00 | 65.2 / 48.8 |
| Y2018 B7 / B3 | 2986 | 2.678870 | 3.772117 / 3.422254 | 2.756956 / 2.727572 | +0.078085 / +0.048702 | 100.00 / 100.00 | 100.00 / 100.00 | 73.6 / 50.9 |
| Y2019 B7 / B3 | 3115 | 0.577643 | 0.923097 / 1.095912 | 0.688647 / 0.875436 | +0.111004 / +0.297794 | 92.31 / 100.00 | 89.51 / 100.00 | 68.1 / 50.4 |
| Y2020p B7 / B3 | 2721 | 0.297538 | 0.311690 / 0.199088 | 0.228078 / 0.160867 | -0.069459 / -0.136671 | 45.35 / 20.38 | 45.05 / 19.88 | 73.3 / 47.5 |

- Helps (gain>0): B7 3/4 (all but Y2020p), B3 3/4 (all but Y2020p). Timing significant
  (>=95): B7 2/4 (2017, 2018; 2019 92.3/89.5 just below), B3 3/4 (2017, 2018, 2019).
- The failure is the COVID leg Y2020p (both variants negative gain + insignificant timing)
  — the same leg that breaks every tilt in oc_presampletilt (V_RV6/V_GARCH/C2 all fail
  Y2020p). Post-cascade sizing levers the crash, not the rebound.

## Crash risk (stop-hit share of boosted fills vs base rate; kinds recomputed verbatim mu=1.0)

- Kinds: TP 5,729 / time 3,445 / stop 480 / backstop 62 / unknown 15 (levels from bars
  opens + verbatim compute_sigma; see PLAN caveat; rates over known kinds only).

| year | base stop% | B7 boosted stop% (delta) | B3 boosted stop% (delta) | base TP% |
|---|---|---|---|---|
| Y2017 | 3.30 | 1.69 (-1.61) | 1.80 (-1.50) | 80.3 |
| Y2018 | 3.29 | 3.55 (+0.26) | 3.35 (+0.06) | 55.8 |
| Y2019 | 6.69 | 7.47 (+0.78) | 3.58 (-3.11) | 55.3 |
| Y2020p | 7.58 | 9.13 (+1.55) | 10.84 (+3.27) | 59.5 |
| pooled | 5.58 | 6.20 (+0.62) | 5.29 (-0.29) | — |

- Pooled: no excess crash risk from the boost (B7 +0.6pp, B3 -0.3pp on a 5.6 % base).
  But Y2020p boosted stops ARE elevated (+1.5/+3.3pp) — the boost levers the crash leg,
  the same mechanism as the deepened 2023 episode in oc_cascadeboost (+0.9pp DD).

## Leakage checklist

- Feature timing: triggers use closes with close_time <= tc only; SIG window excludes the
  tested bar (no self-inclusion); boost window strictly after tc (0 < T-tc <= Nd];
  truncation-tested on real pre-sample bars (triggers + sigma identical on kept prefix).
- Label windows: none fit anywhere in this study (no harness join, no labels).
- Fit windows: no fits; threshold 4.0, windows 540/120, boost 1.5, N = 7/3, seeds
  20261007+y/20261008+y, BLOCK 42 all frozen ex-ante/inherited, never scanned; no statistic
  from any test year feeds any choice. Pre-sample years were never used for any fit.
- Fill timing: replica fills inherited (live 16..238 strict trade-through, stop-first);
  kind recompute uses the same live window + stop-first ordering; perms reassign mults
  within (year, shift) only.
- Coverage: no skipped year; all 9,731 fills joined exactly (0 misses); 15 unknown kinds
  (0.15 %, window rebuild on gapped bars) excluded from rates only.
- Gate costs: inside the reused replica outcomes (maker 0.0002/taker 0.00055, adverse long
  funding 0.0001/8h); the boost is a sizing-only overlay with no extra cost.
- Spot-vs-perp caveat on every number (SPOT fills/exits, perp gate costs).

## What worked and what did not

- Worked: the boost helps in 3 of 4 unseen years for both variants (B7 gains
  +0.046/+0.078/+0.111; B3 +0.026/+0.049/+0.298), with significant timing in 2017-2018
  (both) and 2019 (B3; B7 92.3 just below 95). Pooled crash risk is flat.
- Did not: Y2020p fails for both (gain -0.07/-0.14, timing ~20-45) — the COVID crash leg,
  exactly the leg that breaks all presampletilt tilts. Y2020p boosted stops are elevated.
- Post-hoc fix (disclosed, no method change): one syntax typo in compute_stop_presample.py
  (`out[f"{variant}_pooled}"`) fixed after the replica outcome so the stop script could run;
  no result row changed, no threshold/window touched.

## Vietnamese verdict

B7 giúp 3/4 năm chưa từng thấy (gain +0,05/+0,08/+0,11; timing 100/100/92,3) và B3 cũng
3/4 (timing 100/100/100) — boost sau cascade KHÔNG phải artefact của 5 năm đã thấy, nhưng
chân COVID Y2020p làm cả hai lỗ (gain âm, timing mất) và stop của fill được boost tăng
(+1,5/+3,3pp), đúng cơ chế đào sâu drawdown đã thấy ở 2023.
Rủi ro crash gộp không tăng (B7 +0,6pp, B3 -0,3pp trên nền 5,6%), nên đây là bằng chứng
unseen-years ỦNG HỘ một phần cho B7.
Kết luận: NEEDS PROSPECTIVE EVIDENCE — cộng điểm unseen cho B7 nhưng chưa adopt, chờ log
paper prospective xác nhận, không triển khai thật.
