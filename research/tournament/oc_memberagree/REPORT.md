# oc_memberagree REPORT — member-agreement confidence sizing (IDEAS8 #3)

Method (PLAN pre-registered 2026-10-08, no changes; post-hoc log still
empty): byte-logic replica of `v421/v421_gross_cap.py::worker` for
`R2B1D17BFG2` (rule inv, k 1.0, kd 1.7, bear True, G 2.0, R2 agents ON,
win_start 5) on all 4 clock phases, book swapped per row. Blend confirmed:
REF == `forward_v205.research_books_d2` (max diff 2.2e-16). Agreement per
(T,s): a = # of 6 cached members with sign == ensemble sign (member == 0
counts as disagree; w_ens == 0 -> a = 6, scale 1.0). V1 = x{1.0 a>=5, 0.5
a<=3, else 0.75}; V2 = x{1.0 a==6, 0.5 a<=4, else 0.75}; C08 = 0.8 x w_ens
(IDEAS8 control); C_V1/C_V2 = w_ens x per-year realised gross ratio of
V1/V2 (diagnostic, in-year, NOT eligible). v421 x0.5 bear filter after
scaling on all rows (commutes with scaling). Repro:
`research/tournament/oc_memberagree/run_memberagree.py` (`--build-books`,
`--shift S` via heavy_slot one at a time, `--score`); tests
`tests/test_oc_memberagree.py` (5/5 pass). REF reproduced v421_result
R2B1D17BFG2 TO THE DIGIT before scoring (R 5.41 / DD 16.91 / full-path
16.82, all yearly rows).

## 4-phase reset R (%/mo geometric) — selection on dev4 only

| year | REF | V1 | V2 | C08 (ctrl) | C_V1 (ctrl) | C_V2 (ctrl) |
|---|---|---|---|---|---|---|
| 2021-09-24 | 2.588 | 2.609 | 2.551 | 2.719 | 2.635 | 2.659 |
| 2022-09-24 | 3.282 | 3.334 | 3.585 | 2.884 | 3.295 | 3.267 |
| 2023-09-24 | 6.045 | 6.256 | 6.722 | 7.390 | 6.420 | 6.369 |
| 2024-09-24 | 10.677 | 10.734 | 10.927 | 10.658 | 10.704 | 10.726 |
| 2025-09-24 (recent, scored ONCE, REF + pick only) | 4.648 | 4.566 | — | — | — | — |
| dev4 mean / WORST | 5.601 / 2.588 | 5.686 / 2.609 | 5.897 / 2.551 | 5.861 / 2.719 | 5.716 / 2.635 | 5.708 / 2.659 |
| 5y mean | 5.410 | 5.461 | 5.618 | 5.478 | 5.495 | 5.464 |

Yearly DD / full-path DD: REF yearly (10.86, 16.91, 15.81, 8.27, 12.90),
full 16.82. V1 (11.55, 17.01, 15.94, 8.36, 12.86), full 16.96 (+0.14 vs
REF). V2 (11.70, 16.53, 15.99, 8.34, 12.97), full 16.45 (-0.37).
C08 full 16.74; C_V1 16.88; C_V2 16.82. No row has a losing dev year;
every row DD <= 20. Book-only P&L NOT separable (engine stores t/eq/eq_min
only, same as v421); trade counts/win rates below are the decomposition.

## Dev4 robust pick (REF + variants only; controls not eligible)

All three eligible rows satisfy DD <= 20 with no losing dev year and mean
>= 5, so the rule picks the highest dev4 WORST: **V1** (W 2.609 > REF
2.588 > V2 2.551). V2 has the highest mean (+0.30pp vs REF) but the worst
worst-year (-0.04pp vs REF), so it loses on the frozen robustness rule —
the same dev-mean-chasing pattern (v189-v197) the rule was written to
reject. Protocol note: the scorer evaluates all five reset years for every
row in one mechanical pass (same binary as oc_memberdrop's descriptive
pass); selection read dev4 fields only (`robust_pick` uses dev4_R/W/DD/
losing). Y4 values for V2/controls exist in results.json as audit trail
but were not used for any choice and are not presented above.

## Control comparison (the honest finding)

- V1 (+0.085pp/mo dev4 vs REF) does NOT beat its exposure-matched control:
  C_V1 +0.115pp vs REF, i.e. a flat per-year constant cut explains all of
  V1's gain and then some. Worst-year edge (+0.02pp) is noise; DD is
  slightly worse (+0.10pp max yearly, +0.14pp full-path).
- V2 (+0.296pp vs REF) beats its control C_V2 (+0.107) by ~+0.19pp/mo with
  -0.37pp full-path DD relief — the only timing-shaped signal in the
  table — but it fails the robust rule (worst year below REF) and is not
  the pick.
- C08, the dumb uniform 0.8x book cut, beats both variants on dev4
  (5.861, W 2.719). Agreement is high (mean a 5.0-5.5, a==6 on 62-78% of
  cells; realised gross ratios V1 0.97-0.99, V2 0.94-0.97), so the rule
  fires rarely and mostly on small-|w| cells — the same "weights too small
  to matter" lesson as oc_bookthresh, and the same proportional-
  deleveraging shape as oc_bookcorr.
- Most-recent year (pick + REF only): V1 4.566 vs REF 4.648 (-0.08pp).
  Neither reaches the >= 5%/mo gate leg there; no adoption case.

## Trades (4-phase sums; book episodes net of fees, v213-style walk)

| year | REF book ep / win | V1 book/win | V2 book/win | REF rungs/win | V1 rungs/win |
|---|---|---|---|---|---|
| 2021 | 926 / 50.3% | 918 / 49.2% | 876 / 51.4% | 4075 / 63.8% | 4074 / 63.8% |
| 2022 | 861 / 51.2% | 888 / 52.7% | 884 / 53.4% | 3941 / 68.9% | 3939 / 68.9% |
| 2023 | 1002 / 51.5% | 1014 / 52.0% | 998 / 52.3% | 4977 / 73.2% | 4971 / 73.2% |
| 2024 | 1163 / 50.6% | 1174 / 51.3% | 1148 / 52.3% | 3847 / 71.9% | 3846 / 71.9% |
| 2025 (recent, REF+pick) | 1112 / 53.8% | 1117 / 53.2% | — | 4671 / 64.8% | 4670 / 64.8% |

Book win rates stay 49-53% in every row/year — agreement sizing does not
move the book win rate (the 55% MANUAL floor is untouched). Rung counts/
win rates are near-identical across rows (dip sleeve barely sees the book
change).

## Fee split (book episodes; maker = fill/add/reduce/partial/tp/close x
0.0002, taker = stop x 0.00055; gate funding/adverse-long-0.0001 inside
engine equity, not in this walk)

| year | REF maker / taker | V1 maker / taker | V2 maker / taker |
|---|---|---|---|
| 2021 | 0.025251 / 0.002126 | 0.025188 / 0.002203 | 0.024292 / 0.001984 |
| 2022 | 0.033369 / 0.012190 | 0.034212 / 0.010531 | 0.034277 / 0.010159 |
| 2023 | 0.034180 / 0.014682 | 0.034628 / 0.014679 | 0.034835 / 0.014265 |
| 2024 | 0.039105 / 0.011228 | 0.039229 / 0.011115 | 0.039019 / 0.010034 |
| 2025 (recent) | 0.034158 / 0.012194 | 0.034676 / 0.012069 | — |

Maker dominates ~3:1; sizing trims taker slightly (fewer stops: V2 5y
taker 0.048 vs REF 0.052) with no fee saving large enough to matter
(deltas ~1e-3 against yearly return deltas ~1e-1 in the same units).

## What failed / limits (honest)

- The mechanism as pre-registered does not survive its own control: V1's
  entire dev4 gain is exposure (C_V1 wins), and a dumber flat 0.8x cut
  (C08) beats V1 on both mean and worst-year. Agreement is signal-shaped
  only in V2, which the frozen rule rejects.
- Effect sizes (+0.09/+0.30pp/mo dev4) sit at 1-4x the 4-8 bps round-trip
  bound — real money scale, but the control attribution says V1's share is
  deleveraging, not timing.
- The most-recent year goes the wrong way for the pick (-0.08pp) and no
  row clears 5%/mo there; the BOT 8%/mo and MANUAL win-rate goals are
  untouched by this study (book wins ~51%, rungs ~64-73% as before).
- Book-only share genuinely not separable here (equity-only storage); the
  episode/win-rate/fee split above is the closest decomposition.

## Leakage / execution statement

Cached members are research fits frozen before each anchor (deployed
provenance, same as oc_memberdrop). No test-year or most-recent-year
statistic entered any weight, threshold or choice (scales are frozen
integers on close-known signs; C08 = frozen 0.8; C_Vx use in-year realised
means so they are labelled diagnostic/non-eligible and were never
candidates). Feature timing: standard rows use member values at T (known
at T's close); shifted clocks ffill the latest standard row r <= t_s
(truncation-tested). Fits: none (read-only books). Fills: engine
trade-mode (limit trade-through, no fill minutes 0-4, stop-first, maker
0.0002/taker 0.00055, adverse long funding 0.0001/8h) unchanged from v421.
Tests: causality/truncation + hand-checked synthetic
(`tests/test_oc_memberagree.py`, 5/5 pass, incl. the fee-split hand-calc
the suite corrected before any engine run).

## Verdict (tiếng Việt, 3 dòng)

Pick theo luật robust dev4 là V1 (WORST 2.609 nhỉnh hơn REF 2.588, V2 mean cao nhất nhưng worst-year kém hơn nên bị loại), nhưng V1 không thắng nổi control khớp-exposure (C_V1 +0.115 còn V1 chỉ +0.085 điểm %/tháng) và DD còn nhích lên — lợi nhuận là do giảm đòn bẩy book, không phải timing theo đồng thuận member.
Năm gần nhất V1 thua REF (-0.08) và không hàng nào đạt 5%/tháng; win rate book vẫn ~51%, fee split maker gấp ~3 lần taker — không chạm tới mục tiêu MANUAL/BOT, REJECT adoption cho cả hai biến thể, hướng này đóng lại không cần prospective log riêng.
Nếu muốn theo tiếp thì chỉ V2 (hơn control +0.19, DD full-path -0.37) đáng đăng ký hướng mới với ngưỡng nghiêm ngặt hơn, nhưng phải đánh walk-forward lại từ đầu và cấm dùng năm gần nhất để chọn.
