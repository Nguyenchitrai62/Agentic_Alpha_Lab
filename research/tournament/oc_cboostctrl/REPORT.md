# oc_cboostctrl — REPORT (2026-10-08; PLAN frozen before any outcome)

Is B7 timing or just more exposure? Exposure-matched controls IN THE ENGINE:
CTRL_C (constant per-year dip mult = B7's realised mean mult that year, no timing)
and CTRL_R (random 7-day x1.5 windows, same trigger count per year, 20 seeds).

CONTAMINATION LABEL (inherited, pre-registered): B7's idea post-dates oc_cascadedelay's
replica covering all five years incl. the post-release year. B7/REF numbers below are
reproductions of frozen rows; Y4 (2025-09-24..2026-09-23) is a scored-once DIAGNOSTIC for
every row (never used for selection — there is NO selection in this study).

STATUS: DONE — REF reproduces v421 G2 to the digit (dev + Y4 + 5y + full-path);
B7 reproduces oc_cascadeboost to the digit; all controls run (dev + last, once).

## Frozen inputs check

- Trigger recount (verbatim 4.0/540/120 closes-only, union/shift): per-year sums
  264/266/263/255 — IDENTICAL to oc_cascadeboost/oc_cascadedelay. Full-history unions
  (338/341/344/328) add pre-2021-09-24 triggers only.
- CTRL_C constants (mechanical, from B7's own run): c = 1.261/1.338/1.362/1.303
  (dev y0..3) + 1.346 (Y4); dev constants identical across stages (determinism).
  Exposure match confirmed: sized_mean CTRL_C 1.319193 vs B7 1.319311 dev
  (equal to 4 decimals), 1.324927 vs 1.325008 over 5y.
- CTRL_R: k per (y,s) = 39..69 (see tmp/ctrl_counts.json), 20 seeds
  seed(y,s,j) = 6100000+j*100+y*10+s, all distinct; all 400 (y,s,j) start sets have
  exactly k distinct sorted starts (tested).

## Engine dev4 (selection basis; %/mo reset + DD)

| row | 2021 | 2022 | 2023 | 2024 | mean | WORST | DDmax | losing |
|---|---|---|---|---|---|---|---|---|
| REF | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 5.601 | 2.588 | 16.91 | 0 |
| B7 | 2.955/14.67 | 3.264/17.92 | 8.537/15.94 | 12.486/11.01 | 6.738 | 2.955 | 17.92 | 0 |
| CTRL_C | 2.940/12.74 | 3.391/18.33 | 7.503/15.67 | 12.187/10.04 | 6.441 | 2.940 | 18.33 | 0 |
| CTRL_R mean (p5/p95) | 2.686 (2.36/2.97) | 3.229 (2.94/3.55) | 7.552 (7.00/8.14) | 12.248 (11.94/12.49) | 6.359 (6.16/6.49) | 2.686 (2.36/2.97) | 18.07 (17.00/18.84) | 0 |

- CTRL_R dev4 range over seeds: 5.998..6.536 (ALL 20 seeds beat REF 5.601; B7 6.738
  beats all 20 — B7 dev4 mean is above the random max, but only by +0.20 over the
  best seed R14 6.536).
- Worst-1m-marked episode (all rows): peak 2023-04-17 -> trough 2023-06-14 (same leg
  as G2); depth REF 16.82 / B7 17.75 / CTRL_C 18.24 / CTRL_R mean 17.91.
- Win rates do not separate rows (all-trade 5y: REF 0.654 / B7 0.650 / CTRL_C 0.651 /
  CTRL_R ~0.649..0.653): pure sizing effect, as expected.

## Share split (B7 gain over REF = exposure + timing)

| basis | CTRL | exposure (CTRL-REF)/(B7-REF) | timing (B7-CTRL)/(B7-REF) |
|---|---|---|---|
| dev4 mean | CTRL_C | 0.739 | 0.261 |
| dev4 mean | CTRL_R mean | 0.667 | 0.333 |
| 5y | CTRL_C | 0.705 | 0.295 |
| 5y | CTRL_R mean | 0.615 | 0.385 |

Two-thirds to three-quarters of B7's gain is plain extra exposure; timing keeps
only ~26-39%.

## B7 vs the random-window p95, per year

| year | B7 R | CTRL_R p95 | B7 above p95? |
|---|---|---|---|
| 2021 | 2.955 | 2.970 | NO (below) |
| 2022 | 3.264 | 3.550 | NO |
| 2023 | 8.537 | 8.143 | YES |
| 2024 | 12.486 | 12.486 | NO (tie, not strictly above) |
| Y4 diagnostic | 4.880 | 4.794 | YES (diagnostic, contaminated) |

Timing beats random placement in 1 of 4 dev years (2023); in 2021/2022 random windows
do as well or better with the same budget.

## Engine 5y + Y4 (scored ONCE; Y4 diagnostic)

- REF: 5y 5.410, Y4 4.648/12.90, full-path DD 16.82 (v421 to the digit).
- B7: 5y 6.364, Y4 4.88/13.81, full-path DD 17.75 (cascadeboost to the digit).
- CTRL_C: 5y 6.083, Y4 4.662/14.73, full-path DD 18.24.
- CTRL_R: 5y mean 5.997 (p5 5.879 / p95 6.111, min 5.717 / max 6.144);
  Y4 mean 4.561 (p5 4.376 / p95 4.794); full-path DD mean 17.91 (p5 16.79 / p95 18.79).
  No losing year for any row (5y or dev4).

## Leakage checklist

- Feature timing: triggers use closes with close_time <= tc only; SIG excludes the
  tested bar; windows strictly after tc; truncation-tested in
  tests/test_oc_cboostctrl.py (10 pass). B7 leg reads the frozen parquet (no refit).
- CTRL_C peeks at its year's realised mean BY DESIGN (non-tradable control, labelled;
  never feeds any tradable choice; no selection in this study).
- CTRL_R windows are random (no data use); seeds frozen ex-ante; starts built before
  any engine run.
- Fit windows: no fits (threshold/windows/boost/N/seeds frozen; c_y is a mechanical
  exposure equaliser; k_{y,s} are causal counts).
- Fill timing: engine win_start=5 + 1m trade-through + stop-first (inherited).
- Gate costs inside the engine. Coverage: full history covers all anchors; dev-stage
  out-of-window y=4 sizings fall back to mult 1.0 (inert for scored dev metrics).
- Implementation fixes (disclosed, neither changes any scored number): (1) before any
  outcome, `startswith("R")` matched "REF" — narrowed to the R00..R19 set (crashed run
  produced no outcome); (2) after a partial non-scored outcome (one shift eq_end),
  dev-stage CTRL_C lookup for out-of-window year-4 sizings falls back to 1.0 (only
  affects unscored bookkeeping; scored dev years 0..3 use the filed constants).

## Vietnamese verdict

B7 hơn G2 +1,14pp dev4 (+0,95pp 5y) nhưng CTRL_C (cùng exposure trung bình, không timing)
đã chiếm 74% dev4 (71% 5y), CTRL_R trung bình chiếm 67% (62% 5y) — timing chỉ còn ~26-39%.
B7 chỉ vượt p95 của 20 seed ngẫu nhiên đúng 1/4 năm dev (2023; 2021/2022 thua, 2024 hòa),
Y4 diagnostic vượt nhẹ (4,88 vs 4,79) nhưng nhiễm nên không tính.
Kết luận: REJECT timing — cái "boost sau cascade" chủ yếu là tăng exposure, không phải
chọn đúng thời điểm; giữ nguyên trạng B7 (needs prospective), không adopt vì timing.
