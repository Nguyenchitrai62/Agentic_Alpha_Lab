# oc_cascadeboost — REPORT (2026-10-08; PLAN frozen before any outcome)

INCREASE the dip budget after a cascade bar (the opposite of oc_cascadedelay): after any 4h bar
with |close-to-close log move| > 4 x trailing-90d sigma (closes-only cascade proxy, VERBATIM
oc_cascadedelay definition, multiplier inverted 0.5 -> 1.5), dip budget x1.5 (market-wide per
shift) for N days. B7 N = 7; B3 N = 3 (both frozen). Book untouched. G2 dip gross cap (2.0)
and every other G2 limit bind. Existing 4h closes only (no new data).

CONTAMINATION LABEL (pre-registered): oc_cascadedelay's replica covered all five years incl. the
post-release year, so this idea was formed after seeing those years: select on dev4 ONLY
(anchors 2021-2024); the post-release year (2025-09-24 .. 2026-09-23) number is a LABELLED
DIAGNOSTIC (not clean evidence); only prospective paper could confirm.

STATUS: DONE — both variants PASS the replica+placebo gate; engine run for REF + B7 + B3 (dev)
and REF + dev4 pick B7 (last, once). Dev4 robust pick: B7.

## Triggers (frozen, causal, verbatim oc_cascadedelay)

- 4h closes (`oc_kronoshidden/bars_4h_4shift.parquet`), per (sym, shift): r[i] = ln(C[i]/C[i-1]);
  SIG[i] = std of r[i-540..i-1] (min_periods 120, tested bar excluded); fire iff |r[i]| >
  4.0*SIG[i]; tc = T[i]+4h. Union over 5 majors per shift. (`boost_mult_4shift.parquet`,
  53,877 rows = same grid as the delay file; union triggers per shift s0 264 / s1 266 /
  s2 263 / s3 255 — IDENTICAL to oc_cascadedelay, confirming verbatim arithmetic.)
- Boosted time-bar share: B7 38-55 %/yr/shift, B3 20-33 %/yr/shift. Boosted FILL share is
  higher (B7 52-72 %, B3 37-52 %): dip fills cluster in the volatile downdrafts that follow
  big bars — the boost binds exactly where the sleeve earns. Full 540-return windows for all
  of 2021-09-24.. — no skipped year, nothing imputed; NaN-sigma bars never fire.
- Sized mean multiplier (engine): B7 1.319 (boosted share of sizings 63.9 %), B3 1.226 (45.3 %).

## Replica + placebo gate (reused D0+B1 ledger, n = 22312, base sum5y = 7.718304 exact)

| year x variant | n | base | boosted | norm | timing pct | block pct | boosted fills% |
|---|---|---|---|---|---|---|---|
| 2021 B7 / B3 | 4171 | 0.911273 | 1.349830 / 1.106289 | 1.0722 / 0.9335 | 96.6 / 77.7 | 97.0 / 79.2 | 51.8 / 37.0 |
| 2022 B7 / B3 | 4059 | 0.832599 | 1.128056 / 0.938556 | 0.8432 / 0.7621 | 67.7 / 42.5 | 69.9 / 37.6 | 67.6 / 46.3 |
| 2023 B7 / B3 | 5352 | 2.099814 | 2.827361 / 2.721598 | 2.0754 / 2.1642 | 85.4 / 98.9 | 87.5 / 99.0 | 72.5 / 51.5 |
| 2024 B7 / B3 | 3958 | 3.197390 | 4.330611 / 3.983387 | 3.3250 / 3.2805 | 100.0 / 100.0 | 100.0 / 100.0 | 60.5 / 42.9 |
| 2025 screen B7 / B3 | 4772 | 0.677229 | 1.028874 / 0.986742 | 0.7636 / 0.7939 | 98.1 / 100.0 | 98.2 / 99.9 | 69.5 / 48.6 |

- dSum5y (4-phase-mean w*y): B7 +2.946, B3 +2.018 — both far above +0.273 (exact mirror of
  the delay dSums -2.946/-2.018 up to rounding, as pre-registered: 1.5 = 1+0.5 vs 0.5 = 1-0.5
  on the same cooled sets). Sum-half: 5/5 each (boosted >= base every year). Gate needs BOTH
  legs: B7 PASS, B3 PASS.
- Timing percentiles are HIGH where it matters (B7: 96.6 in 2021, 100.0 in 2024; B3: 98.9 in
  2023, 100.0 in 2024): the boost beats random time-bar reassignment — the mirror image of
  the delay's significantly-worse-than-random timing.
- The 2025 row above is the replica screen (same ledger years as the tilt studies), NOT a
  scored-once engine year.

## Engine dev4 (4-phase reset %/mo + DD; selection basis)

| row | 2021 | 2022 | 2023 | 2024 | mean | WORST | DDmax | losing |
|---|---|---|---|---|---|---|---|---|
| REF | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 5.601 | 2.588 | 16.91 | 0 |
| B7 | 2.955/14.67 | 3.264/17.92 | 8.537/15.94 | 12.486/11.01 | 6.738 | 2.955 | 17.92 | 0 |
| B3 | 2.597/14.58 | 3.137/18.05 | 7.823/15.74 | 12.036/8.99 | 6.330 | 2.597 | 18.05 | 0 |

- REF reproduces v421 G2 dev years 0..3 R/DD to the digit (reproduction gate passed before
  any variant row was scored). Full-path DD dev window: REF 16.82, B7 17.75, B3 17.94.
- All-trade win rates dev4 (book+rung): REF [0.613, 0.658, 0.697, 0.671]; B7 [0.610, 0.651,
  0.695, 0.664]; B3 [0.610, 0.655, 0.694, 0.667] — the boost does not move win rates (sizing
  only). Book win 5y ~0.51-0.52 (below any manual floor; this study sizes the BOT sleeve).
- Robust pick on dev4 ONLY among DD <= 20 / no-losing-dev-year rows: all three qualify and
  all three have dev4 mean >= 5 %/mo, so the highest dev4 WORST-year wins: B7 (2.955 vs B3
  2.597 vs REF 2.588; ties would go to the higher mean, also B7 6.738). PICK: B7.

## Engine 5y + post-release year (scored ONCE, REF + pick B7 only; Y4 LABELLED DIAGNOSTIC)

- REF: 5y 5.410, W 2.588, DDmax 16.91, full-path DD 16.82 (reproduces v421_result G2 to the
  digit); Y4 4.648/12.90. Worst 1m-marked DD episode: peak 2023-04-17 -> trough 2023-06-14,
  depth 16.82 % (marked 16.82, close 16.05).
- B7: 5y 6.364, W 2.955, DDmax 17.92, full-path DD 17.75, no losing year; Y4 diagnostic
  4.88/13.81 (BELOW 5 — but contaminated: idea formed after seeing the delay replica incl.
  this year, so this number is not evidence for or against). Worst 1m-marked DD episode:
  peak 2023-04-17 -> trough 2023-06-14, depth 17.75 % (marked 17.75, close 16.96) — the SAME
  2023 crash leg as G2, deepened by ~0.9pp: the boost levers the crash legs, as expected.
- B7 5y fills: book 5033 @ 0.5118, rung 20939 @ 0.6827, all-trade 0.6496; Y4: book 1094 @
  0.5375, rung 4583 @ 0.6435, all 0.6230. Determinism OK (stage-last dev segments equal
  stage-dev).

## Leakage checklist

- Feature timing: triggers use closes with close_time <= tc only; SIG window excludes the
  tested bar (no self-inclusion); boost window strictly after tc (0 < T-tc <= Nd];
  truncation-tested in tests/test_oc_cascadeboost.py (dropping later bars cannot change
  triggers at kept times; 7 pass); exact (shift, T) match with causal ffill fallback in both
  replica and engine (0 replica misses — all 22,312 fills matched exactly; engine fallback
  is latest-grid-time <= T, missing -> 1.0).
- Label windows: none fit anywhere in this study (no harness join, no labels).
- Fit windows: no fits; threshold 4.0, windows 540/120, boost 1.5, N = 7/3 all frozen
  ex-ante, never scanned; no statistic from any test year feeds any choice. Trigger union
  counts identical to oc_cascadedelay (264/266/263/255) — no refit.
- Fill timing: replica fills inherited (live 16..238 strict trade-through, stop-first);
  engine win_start=5 + trade-through + stop-first; perms reassign mults within (year, shift)
  only (seeds 20261007+y / 20261008+y).
- Coverage: 4h closes cover every anchor year — no skipped year, nothing imputed.
- DISCLOSED (pre-registered): the k2placebo ledger carries no exit-date/daily path, so the
  replica DD-half cannot be scored at the replica stage; the binding DD check is the 4-phase
  engine (yearly DD + full-path DD <= 20 — B7 17.92/17.75, B3 18.05/17.94, both pass).
- Gate costs: inside the replica outcomes (maker 0.0002 / taker 0.00055, v293 settle
  funding) and inside the engine (maker 0.0002, taker 0.00055, longs pay 0.0001/8h,
  shorts 0).

## What worked and what did not

- Worked: the mirror hypothesis holds mechanically — post-cascade dips carry the profit, so
  1.5x sizing there adds +2.9/+2.0 replica units and +1.14/+0.73pp/mo dev4 mean (B7/B3),
  lifting the worst dev year (B7 W 2.955 vs REF 2.588). Timing placebo supports it (100.0 in
  2024 both variants).
- Cost: DD rises ~1pp (B7 DDmax 17.92 vs REF 16.91; the worst episode is the same 2023 leg,
  deepened). Win rates do not move (pure sizing change). B3's longer-tail behaviour is
  strictly weaker than B7 on dev4 (mean 6.33 < 6.74, W 2.60 < 2.96, DD 18.05 > 17.92).
- Not shown: the post-release Y4 diagnostic (B7 4.88 vs REF 4.65) is contaminated by
  construction and proves nothing; the dev4 gain (+1.14pp) exceeding the 5y gain (+0.95pp)
  is the usual shrinkage pattern. Only prospective paper (data that did not exist when the
  rules were frozen) can confirm B7.

## Vietnamese verdict

B7 là pick robust duy nhất trên dev4 (mean 6,74, WORST 2,96, DD 17,92 — hơn G2 +1,14pp mean
và +0,37pp worst-year với giá +1,01pp DD; cùng đoạn drawdown 2023 bị đào sâu thêm ~0,9pp),
B3 yếu hơn trên mọi mặt dev4 nên loại.
Nhưng Y4 post-release chỉ là diagnostic nhiễm (4,88 < 5, ý tưởng hình thành sau khi thấy replica
5 năm) nên KHÔNG đủ bằng chứng để adopt.
Kết luận: NEEDS PROSPECTIVE EVIDENCE — giữ B7 làm ứng viên, chờ log paper prospective xác nhận,
không triển khai thật.
