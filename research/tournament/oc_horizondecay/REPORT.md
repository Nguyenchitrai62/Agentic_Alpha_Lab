# oc_horizondecay REPORT — Slow-horizon decay ensemble (IDEAS8 #4)

Method per PLAN.md (pre-registered 2026-10-08, frozen; H={1,2,6,18} = the
oc_bookichorizon horizons {1,2,6,18,42} truncated per "beyond 18 excluded").
A/Aq retrained at each h with y_h=clip(log(o[t+1+h]/o[t+1])/(vol42*sqrt(h)),±4)
(o[T+1]-based horizonfix forward; filters/embargoes unchanged), then
A_HD=sum w_h·A_h with frozen renormalised w (HD1 1/h → 18/31,9/31,3/31,1/31;
HD2 1/sqrt(h) → .4253/.3007/.1736/.1003). B/Bq/D/Dq frozen caches.
Engine = v421 R2B1D17BFG2 replica (inv, k 1.0, kd 1.7, bear, G 2.0, agents ON,
win_start 5, shifts 0-3). Full numbers in `results.json`.

## Gates first

- Builder check: PASS. Spearman(repro,cache)=1.000000 in EACH of 5 years for A
  and Aq (>=0.999 required).
- G2 reproduction: EXACT. REF == v421_result[R2B1D17BFG2] to the digit:
  R5 5.41, max-yearly DD 16.91, full-path DD 16.82.
- Gate costs (inside engine): maker 0.0002, taker 0.00055, longs 0.0001/8h,
  shorts zero; no fill minutes 0-4; stop-first.

## Engine per-year (R %/mo geometric reset metric; DD yearly; book_ep win)

REF (G2): 2021 2.588/10.86 (bk .503) | 2022 3.282/16.91 (.512)
  | 2023 6.045/15.81 (.515) | 2024 10.677/8.27 (.506)
  | 2025 4.648/12.90 (.538) [labelled, scored once]
  dev4 5.601/W 2.588/DD 16.91/losing 0; R5 5.41; full-path DD 16.82.
HD1 (1/h; NON-CHOSEN, dev4 only; 2025 redacted): 2021 2.542/11.27 (.499)
  | 2022 0.554/24.16 (.443) | 2023 4.308/16.95 (.497) | 2024 10.796/8.40 (.502)
  dev4 4.481/W 0.554/DD 24.16/losing 0. INELIGIBLE (DD>20).
HD2 (1/sqrt(h); NON-CHOSEN, dev4 only; 2025 redacted): 2021 2.510/12.03 (.501)
  | 2022 0.650/22.52 (.464) | 2023 4.986/16.70 (.508) | 2024 10.636/8.54 (.493)
  dev4 4.629/W 0.650/DD 22.52/losing 0. INELIGIBLE (DD>20).
CC1 (control for HD1, NOT eligible, dev4 only): 2021 2.652 (.504)
  | 2022 3.166 (.504) | 2023 6.757 (.515) | 2024 10.740 (.512);
  dev4 5.779/W 2.652/DD 16.87. CC2 (for HD2): 2.600/3.265/6.706/10.775;
  dev4 5.787/W 2.600/DD 16.71.
Selection (dev4 ONLY, robust): HD1/HD2 fail DD<=20; REF is the only eligible
row → pick = REF. Both HD variants trail REF by ~1.0-1.1pp dev4 mean AND trail
their own exposure-matched controls by ~1.2-1.3pp (CC1 5.779 vs HD1 4.481;
CC2 5.787 vs HD2 4.629): the decay timing destroys value; the small trim
(0.92-0.97x scale) alone beats G2.

## Exposure / fees / trades

- Realised mean |book| scale vs REF (pre-bear, per year): HD1
  0.967/0.917/0.945/0.929 (CC1 scalars); HD2 0.971/0.923/0.951/0.934.
  Spike bars are not above-average book bars (trim is uniform, no gate).
- Fee notionals (weight-scale, 4 shifts summed; fees = maker 0.0002 /
  taker 0.00055 on top): REF maker 638.0/taker 32.9; HD1 743.2/35.4;
  HD2 717.1/35.1; CC1 618.6/31.2; CC2 619.3/31.2. HD trades MORE (book
  episodes REF 5064 vs HD1 5747/HD2 5567) for LESS return: dust churn, and
  2022 book win collapses (HD1 .443, HD2 .464 vs REF .512).
- Rung/all-trade wins move little (all_win REF .61-.70 vs HD .61-.69);
  the damage is book-side timing + DD (2022 DD 24.16/22.52 vs 16.91).

## What failed / why (honest)

- Hypothesis rejected at engine level: overweighting slow horizons does not
  transfer — 2022 (the trend-break year) collapses to 0.55-0.65 %/mo with
  DD >22, while 2024 is flat (+0.1pp). Dev-mean gains nowhere; worst-year
  drops ~2pp vs G2. Matches the v189-v197 lesson (dev-mean tweaks fail OOS).
- The controls tell the story: a plain 3-8% exposure trim (CC1/CC2 dev4
  5.78-5.79) beats both the decay blends and G2 — the only "gain" available
  here is sizing, not horizon timing.
- Book win unmoved (~.50 except 2022 collapse): decay blending does not fix
  the MANUAL win-rate problem either.

## Leakage checklist

- Feature timing: audited v240/v144 builders reused unchanged (TV/flow merge
  on (t,sym), rows from bars <= t close; aggflow orders <= t). Tests assert
  truncation invariance of relabel_y.
- Label windows: y_h realised at t+1+h, trained only where realised before
  the native cutoff (filters kept: 102/144/78 bars = 17d/24d/13d >= 7d
  embargo; o[T+1] base per horizonfix). No future forward in any fit.
- Fit windows: all HGB + vol fits end before anchor-embargo; fresh models per
  year/quarter train only before Y-embargo. Weights frozen analytic (no fit,
  no test-year reweight). No test/most-recent statistic in any choice.
- Fill timing: inherited replica (minute-5+ trade-through, SL market/TP
  limit, stop-first). Tests: `tests/test_oc_horizondecay.py` 4 passed
  (weights/blend hand-check, label formula + truncation, bear/exposure).

## Verdict (tiếng Việt, 3 dòng)

- Bác bỏ: pha trộn decay chân trời chậm (1/h và 1/sqrt(h) trên h=1,2,6,18) làm tệ hơn G2 (dev4 ~4.5-4.6 vs 5.6, DD 2022 >22 vượt cổng 20, thua cả control khớp-exposure ~1.3pp).
- Chọn REF theo tiêu chí robust dev4 (HD1/HD2 đều rớt DD, REF đủ điều kiện duy nhất); năm gần nhất chỉ chấm cho REF (4.648%/tháng, DD 12.90).
- Đóng hướng horizon-decay, không cần prospective thêm; bài học là control khớp-exposure bắt đúng câu chuyện (trim nhẹ thắng nhờ size, timing horizon thua).
