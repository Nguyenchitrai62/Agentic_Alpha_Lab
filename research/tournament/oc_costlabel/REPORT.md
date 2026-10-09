# oc_costlabel REPORT (2026-10-07 wave; PLAN.md frozen pre-registration)

## Question

Retrain the whale-flow book member A/Aq (regression on vol-normalised forwards)
on a COST-THRESHOLDED binary label `y = 1{fwd h=6 raw log-return from o[T+1] > thr}`
(thr = 8 bps CV1 / 5 bps CV2), HGB Classifier + pre-anchor isotonic mapping back
to the deployed weight scale? Rows: REF (G2 deployed), CV1 (8 bps), CV2 (5 bps);
CC1/CC2 exposure-matched constant controls (reported, not eligible).

## Gates first

- Builder check: PASS. Spearman(repro, cache) = 1.000000 in EACH of 5 anchor
  years for A and for Aq (>= 0.999 required). Quarterly cut fix logged in
  PLAN.md post-hoc (before any engine outcome; annual files unaffected).
- REF reproduction: EXACT. REF == v421_result[R2B1D17BFG2] to the digit:
  R5 5.41, max-yearly DD 16.91, full-path DD 16.82. Engine replica confirmed.
  REF vs `forward_v205.research_books_d2` max diff 2.2e-16.
- Costs (gate): maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts zero;
  no fill minutes 0-4 after 4h close; stop-first. Engine v421 R2B1D17BFG2
  (inv, k 1.0, kd 1.7, bear True, G 2.0, agents ON, win_start 5, shifts 0-3).

## Engine per-year (R = %/month geometric, reset metric; DD yearly; win = rates)

REF (CHOSEN, G2): 2021 2.588 / 10.86 (5001, .613; book 926, .503)
  | 2022 3.282 / 16.91 (4802, .657; book 861, .512)
  | 2023 6.045 / 15.81 (5979, .696; book 1002, .515)
  | 2024 10.677 / 8.27 (5010, .670; book 1163, .506)
  | 2025 4.648 / 12.90 (5783, .627; book 1112, .538) [labelled, scored once]
  dev4 mean 5.601, W 2.588, DD 16.91, losing 0; R5 5.41, full-path DD 16.82.
CV1 8bps (NON-CHOSEN, dev4 only; 2025 redacted): 2021 1.996 / 10.61
  (5124, .619; book 1065, .551) | 2022 1.870 / 16.54 (4799, .664; book 1065, .584)
  | 2023 5.224 / 20.68 (5862, .704; book 1101, .580)
  | 2024 11.541 / 8.73 (5204, .680; book 1358, .567)
  dev4 mean 5.086, W 1.870, DD 20.68 (> 20, FAIL), losing 0.
CV2 5bps (NON-CHOSEN, dev4 only; 2025 redacted): 2021 2.084 / 10.60
  (5140, .620; book 1081, .558) | 2022 1.925 / 16.90 (4996, .668; book 1108, .592)
  | 2023 5.711 / 20.39 (5855, .698; book 1190, .572)
  | 2024 10.948 / 8.77 (5137, .676; book 1291, .544)
  dev4 mean 5.104, W 1.925, DD 20.39 (> 20, FAIL), losing 0.
CC1/CC2 controls (exposure-matched REF rescales x0.89-0.97/yr, NOT eligible):
  CC1 dev4 5.837 / W 2.611 / DD 16.82; CC2 dev4 5.855 / W 2.627 / DD 16.83,
  book wins ~.50-.52 (as REF). Exposure trim alone gains ~+0.24pp over REF.
Selection (dev4 ONLY, robust, eligible {REF,CV1,CV2}):
  CV1/CV2 both fail DD <= 20 -> the only passer is REF -> choose REF.
  No row meets the full gate (recent year REF 4.648 < 5 alone).

## What transferred / what failed

- The win-rate mechanism WORKED: CV book-episode win rises +4-7pp in every dev
  year (CV1 .551/.584/.580/.567 vs REF .503/.512/.515/.506; CV2 similar) with
  MORE episodes (5657/5693 vs 5064 total) at ~90-97% of REF exposure. The cost
  filter does cut dust losers.
- But P&L and tail did NOT: dev4 mean -0.50pp (CV1) / -0.50pp (CV2) vs REF,
  worst-year -0.72/-0.66pp, 2023 DD 20.68/20.39 (breach), full-path DD > 21.
  Higher win + lower return = smaller average wins / larger average losses and
  worse concentration in the 2023 trend year. The isotonic-mapped proba keeps
  direction but compresses conviction sizing: fewer big winners, same fat tail.
- Controls decide the attribution: CC1/CC2 (REF direction at CV exposure) BEAT
  REF by +0.24pp with DD flat, so the CV loss is direction/conviction, not size.
- Threshold 8 vs 5 bps: indistinguishable (dev4 means within 0.02pp, same DD
  breach) - no threshold guidance; V1/V2 both rejected.

## Fee split (4-phase sums, book-episode walk; maker vs stop-taker)

REF: maker 0.166528, taker 0.052421. CV1: maker 0.181582, taker 0.042909.
CV2: maker 0.181459, taker 0.044590. CC1: maker 0.159750, taker 0.049239.
CV pays MORE maker (more episodes) but less stop-taker (fewer stops per episode
is not enough: stops are deadlier when they hit). Funding: engine-internal
(longs 0.0001/8h, shorts zero), not separately stored - same rule all rows.

## Leakage checklist

- Feature timing: builders reused unchanged (TV/flow merge on (t,sym), rows
  from bars <= t close; order-flow frame from aggflow orders <= t).
- Label windows: y_cost realised at t+1+6, trained only where realised before
  the native cutoff (kept filters 102/144/78 bars = 17d/24d/13d, each implying
  t+7*4h < cutoff, subset of before-anchor-7d). Thresholds frozen round numbers.
- Fit windows: classifiers + isotonic + vol models all end before
  anchor-embargo; fresh models per year/quarter train only before Y-embargo;
  isotonic X/y both in-sample pre-anchor (disclosed). No test-year statistic
  in any fit. No feedback from 2025 (CV 2025 redacted, unused).
- Fill timing: inherited replica (minute-5+ trade-through, SL market/TP limit,
  stop-first). Tests: `tests/test_oc_costlabel.py` 5 passed (hand-checked binary
  formula + threshold edge, truncation causality, filter-requires-realised,
  bear, isotonic monotonicity).

## Verdict (Vietnamese, 3 lines)

- Tu choi gia thuyet: nhan cost-aware (P(return > 5/8bps), h=6) lam win book tang +4-7pp nhung P&L dev4 giam -0.5pp (5.09/5.10 vs 5.60) va DD vuot 20 (20.7/20.4) - control khop-exposure (+0.24pp) chung minh loi o direction/conviction chu khong phai size.
- Chon REF (G2) theo tieu chi robust dev4 (CV1/CV2 rot DD); nam gan nhat REF 4.65%/thang < 5, khong row nao dat gate day du.
- Khong ap dung; huong cost-label dong lai, khong can bang chung prospective them.
