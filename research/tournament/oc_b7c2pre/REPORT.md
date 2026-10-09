# oc_b7c2pre — REPORT (2026-10-08; PLAN frozen before any outcome)

Does the B7xC2 stack (product of the B7 dip-budget boost and the C2 Chronos rung
tilt, verbatim oc_b7c2: m=m_B7*m_C2; cap min(product,1.5)) help on the UNSEEN
pre-sample years 2017-2020? Reused D0+B1 dip replica ledger (9,731 fills; SPOT
fills/exits, perp gate costs inside; spot-vs-perp caveat on every number). B7 rows
are COPIES from oc_cboostpre, C2 rows COPIES from oc_presampletilt (copy gates pass);
only the two stack rows are fresh. Diagnostic only: no selection, no engine.

CONTAMINATION LABEL (pre-registered): B7 was picked on dev4 after the delay replica
had covered the post-release year, and the C2 rule uses the anchor-2021 fit on earlier
years (labelled fit from later data, rule frozen); these pre-sample years are the
unseen evidence leg (nobody looked at them when the ideas were formed).

STATUS: DONE — stack replica + 1000 timing/block perms per variant/year complete,
frozen-kind stop splits complete (15 unknown, 0 missing joins). Tests pass (see below).

## Replica (reused ledger n = 9731, base sums reproduce 2.313362/2.678870/0.577643/0.297538)

| year x variant | n | base | norm_stack | gain_vs_base | gain_vs_B7 | gain_vs_C2 | timing pct | block pct | boosted(mult>1)% |
|---|---|---|---|---|---|---|---|---|---|---|
| Y2017 B7C2 | 909 | 2.313362 | 2.376156 | +0.062794 | +0.016881 | +0.044301 | 100.00 | 100.00 | 0.7063 |
| Y2018 B7C2 | 2986 | 2.678870 | 2.754824 | +0.075954 | -0.002132 | +0.075398 | 100.00 | 100.00 | 0.7384 |
| Y2019 B7C2 | 3115 | 0.577643 | 0.716020 | +0.138377 | +0.027373 | +0.099511 | 98.10 | 96.90 | 0.6941 |
| Y2020p B7C2 | 2721 | 0.297538 | 0.072688 | -0.224850 | -0.155390 | -0.065737 | 4.30 | 9.49 | 0.7376 |
| Y2017 B7C2_cap | 909 | 2.313362 | 2.382570 | +0.069208 | +0.023295 | +0.050715 | 100.00 | 100.00 | 0.7063 |
| Y2018 B7C2_cap | 2986 | 2.678870 | 2.756536 | +0.077666 | -0.000420 | +0.077110 | 100.00 | 100.00 | 0.7384 |
| Y2019 B7C2_cap | 3115 | 0.577643 | 0.710449 | +0.132806 | +0.021802 | +0.093940 | 97.90 | 96.70 | 0.6941 |
| Y2020p B7C2_cap | 2721 | 0.297538 | 0.132917 | -0.164620 | -0.095161 | -0.005508 | 10.99 | 23.48 | 0.7376 |

Copies for reference (B7 from oc_cboostpre, C2 from oc_presampletilt; not rerun):

| year | base | B7 norm (gain, timing) | C2 norm (gain, timing) |
|---|---|---|---|
| Y2017 | 2.313362 | 2.359275 (+0.045913, 100.00) | 2.331855 (+0.018493, 96.40) |
| Y2018 | 2.678870 | 2.756956 (+0.078085, 100.00) | 2.679426 (+0.000556, 99.80) |
| Y2019 | 0.577643 | 0.688647 (+0.111004, 92.31) | 0.616509 (+0.038866, 77.32) |
| Y2020p | 0.297538 | 0.228078 (-0.069459, 45.35) | 0.138425 (-0.159113, 2.90) |

- Helps vs no tilt (gain_vs_base>0): B7C2 3/4, B7C2_cap 3/4 (B7 copy 3/4, C2 copy 3/4; failure is Y2020p everywhere).
- Beats B7 alone (gain_vs_B7>0): B7C2 2/4 (Y2017/Y2019 only; Y2018 -0.002132, Y2020p -0.155390), cap 2/4 (Y2018 -0.000420, Y2020p -0.095161).
- Beats C2 alone (gain_vs_C2>0): B7C2 3/4 (all but Y2020p), cap 3/4 (Y2020p -0.005508, near zero).
- Timing significant (>=95): B7C2 3/4 (2017/2018/2019; Y2020p 4.30), cap 3/4 (Y2020p 10.99); block 3/4 and 3/4.
- COVID leg Y2020p (reported separately): B7C2 norm 0.072688 gain_vs_base -0.224850 (vs B7 gain -0.069459, vs C2 gain -0.159113); cap norm 0.132917 gain -0.164620. The stack deepens the COVID-leg loss vs EACH leg alone (gain_vs_B7 -0.155/-0.095, gain_vs_C2 -0.066/-0.006); timing insignificant (4.3/9.5 uncapped, 11.0/23.5 capped).

## Crash risk (stop-hit share of boosted fills vs base rate; frozen kinds, 15 unknown)

| year | base stop% | B7 boosted (copy, delta) | B7C2 boosted (delta) | B7C2_cap boosted (delta) | stack deboosted stop% |
|---|---|---|---|---|---|
| Y2017 | 3.30 | 1.69 (-1.61) | 1.56 (-1.74) | 1.56 (-1.74) | 0.00 |
| Y2018 | 3.29 | 3.55 (+0.26) | 3.54 (+0.25) | 3.54 (+0.25) | 0.00 |
| Y2019 | 6.69 | 7.47 (+0.78) | 7.32 (+0.64) | 7.32 (+0.64) | 14.17 |
| Y2020p | 7.58 | 9.13 (+1.55) | 9.33 (+1.75) | 9.33 (+1.75) | 0.00 |

- Pooled: base 5.58%, B7 copy boosted 6.20% (+0.62), B7C2 boosted 6.18% (+0.60), cap same. Ex-COVID pooled: base 4.80%, stack boosted 4.92% (+0.11). No crash-risk reduction from adding C2.
- COVID leg Y2020p separately: base 7.58%; B7 boosted 9.13% (+1.55); stack boosted 9.33% (+1.75, both variants). C2 does NOT reduce B7's crash-leg damage there — it adds +0.20pp to the boosted stop rate.
- Y2019 (the other elevated-stop year): base 6.69%; B7 7.47% (+0.78); stack 7.32% (+0.64) — marginally lower than B7 but still elevated; deboosted (0.75) fills stop 14.17% that year (small 3.85% share, context only).

## Leakage checklist

- Feature timing: B7 triggers use closes with close_time <= tc only; SIG window excludes the tested bar; boost window strictly after tc (0 < T-tc <= 7d); C2 forecast for T uses only 512 closes of bars closing <= T; stack lookup uses only (sym,shift,T) at the holding bar with ffill-causal B7 join. Truncation-tested in tests/test_oc_b7c2pre.py (stack mults from truncated frozen boost+Chronos tables identical on kept prefix; multisets subset of the pre-registered sets).
- Label windows: none fit anywhere in this study (no harness join, no labels).
- Fit windows: B7 no fits (frozen 4.0/540/120/1.5/7d); C2 frozen anchor-2021 fit (dir +1, q20/q80, hi/lo 1.25/0.75) applied to earlier years and labelled fit-from-later; no statistic from any test year feeds any choice. Pre-sample years never used for any fit.
- Fill timing: replica fills inherited (live 16..238 strict trade-through, stop-first); kind splits reuse the frozen outcome_mu branch with the same window + stop-first ordering; perms reassign mults within the year only (bar-level joint null + block-42 per (sym,shift)).
- Coverage: no skipped year; all 9,731 fills joined (0 missing time-bars, 0 missing boost; 5,547 C2-missing->1 by burn-in/context, counted); 15 unknown kinds excluded from rates only.
- Gate costs: inside the reused replica outcomes (maker 0.0002/taker 0.00055, adverse long funding 0.0001/8h); the stack is a sizing-only overlay with no extra cost.
- Spot-vs-perp caveat on every number (SPOT fills/exits, perp gate costs).

## What worked and what did not

- Worked: the stack helps vs doing nothing in 3/4 unseen years (gains +0.063/+0.076/+0.138 uncapped, +0.069/+0.078/+0.133 capped) with significant joint timing in 2017-2019 (100/100/~98 timing, ~97-100 block); it beats C2 alone in all non-COVID years. Pooled crash risk is flat vs B7 (pooled delta +0.60 vs B7 +0.62).
- Did not: the stack does NOT beat B7 alone (Y2018 gain_vs_B7 -0.002/-0.0004; the B7 edge does not compose); the COVID leg Y2020p fails harder under the stack than under either leg (gain -0.225/-0.165 vs B7 -0.069, C2 -0.159; timing lost; boosted stops +1.75 vs B7 +1.55) — C2 deepens rather than cushions B7's crash-leg damage, the same mechanism as the deepened 2023 episode in oc_b7c2.

## Vietnamese verdict

- Stack B7xC2 giúp 3/4 năm chưa từng thấy so với không tilt (gain +0,06/+0,08/+0,14, timing 100/100/98) và hơn C2 đơn lẻ ở mọi năm không-COVID, nhưng KHÔNG hơn B7 đơn lẻ (Y2018 thua nhẹ, bản cap cũng vậy; chỉ Y2017/Y2019 hơn B7).
- Chân COVID Y2020p làm stack lỗ sâu hơn cả hai chân (gain -0,22/-0,16 so với B7 -0,07 và C2 -0,16; timing mất) và stop của fill được boost tăng +1,75pp so với B7 +1,55pp — C2 không giảm mà còn đào sâu damage của B7 ở chân crash.
- Kết luận: REJECT stack trên unseen-years — giữ B7 làm ứng viên (chờ paper prospective), không đưa B7C2/B7C2_cap vào G2.
