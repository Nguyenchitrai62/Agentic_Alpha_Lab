# oc_vrpconsistent REPORT — weekly short-straddle re-priced CONSISTENTLY at observed 7d-ATM/DVOL

Frozen rule (PLAN.md, pre-registered 2026-10-07): V2 (weekly naked ATM straddle
BTC+ETH, Fri 08:05, K nearest grid, settle mean 07:30..07:59, Deribit-style fee
caps, SL -1x gross hourly / TP 0.3x gross at 4h, UTA overlay on G2) with EVERY
sigma scaled by r = sigma_true/DVOL: sell 0.97r, TP/mark 1.0r, SL 1.05r.
Rows: R100 r=1.0 (must reproduce V2), R087 r=0.87 (7d-ATM median 0.862/mean
0.868, B.json pooled 61 Fridays), R080 r=0.80 (p10 stress). Repro:
`run_consistent.py dev | recent | gap | collect` (via heavy_slot) +
`tests/test_oc_vrpconsistent.py`. G2 baseline reproduced to the digit before
any overlay (asserted in-script); R100 reproduces oc_vrpstraddle standalone V2
dev4 AND overlay f=0.25 (6.566/4.365/16.10) AND C4 gap numbers to the digit
(asserted); else the run stops.

## Post-hoc change log (original rows kept, one disclosed bug fix)

1. `_px` leg-price floor at 0: the copied BS code returns dust-negative puts
   (~-3e-14) for a deep-OTM leg at tiny T; `fee_per_side` NaNs on negative legs
   and poisoned 2 R080 SL buybacks (2023-04-07 / 2025-07-04 ETH) into account
   NaNs. At r=1.0 the same corner prices tiny-positive so R100 never triggered
   it (verified: R100 asserts still pass bit-identically after the fix).
   Economics move <1e-12. Upstream files were not touched; the latent flaw is
   reported (it can bite any low-sigma row of the copied engine).

## Standalone sleeve V2, dev4 (R %/mo geometric / DD % / end / trades / win)

| year | R100 (V2) | R087 | R080 |
|---|---|---|---|
| 2021-09-24 | 8.004 / 25.82 / 2.519 / 104 / 0.712 | 3.596 / 26.70 / 1.528 / 104 / 0.654 | 0.724 / 31.48 / 1.090 / 104 / 0.606 |
| 2022-09-24 | 4.197 / 18.24 / 1.638 / 102 / 0.716 | 1.406 / 23.24 / 1.182 / 102 / 0.667 | -0.529 / 31.35 / 0.938 / 102 / 0.598 |
| 2023-09-24 | -0.165 / 25.05 / 0.980 / 102 / 0.598 | -2.261 / 30.97 / 0.760 / 102 / 0.539 | -3.788 / 39.48 / 0.629 / 102 / 0.500 |
| 2024-09-24 | 1.903 / 23.40 / 1.254 / 102 / 0.657 | -1.514 / 30.78 / 0.833 / 102 / 0.598 | -2.716 / 36.04 / 0.719 / 102 / 0.598 |
| dev4 mean / worst / maxDD / losing | 3.441 / -0.165 / 25.82 / 1 | 0.280 / -2.261 / 30.97 / 2 | -1.593 / -3.788 / 39.48 / 3 |

Consistent repricing destroys the standalone sleeve: the IV-RV gap turns
negative (R087 gap -0.016/-0.066, R080 -0.077/-0.107 vs R100 +0.097/+0.009),
SL counts jump (R087 14/20/31/29 vs R100 13/17/23/17), DD balloons past 30%.

## Overlay on G2, dev4 (reset metric R %/mo / yearly DD %; full-path DD)

| year | G2 | R100 f=0.25 | R087 f=0.25 | R080 f=0.25 | R100 f=0.10 | R087 f=0.10 | R080 f=0.10 |
|---|---|---|---|---|---|---|---|
| 2021 | 2.588 / 10.86 | 4.655 / 11.18 | 3.578 / 11.23 | 2.866 / 11.44 | 3.419 / 10.42 | 2.991 / 10.43 | 2.707 / 10.46 |
| 2022 | 3.282 / 16.91 | 4.365 / 16.10 | 3.665 / 17.22 | 3.173 / 18.35 | 3.719 / 16.58 | 3.439 / 17.03 | 3.243 / 17.48 |
| 2023 | 6.045 / 15.81 | 6.073 / 15.59 | 5.488 / 15.59 | 5.081 / 15.58 | 6.061 / 15.68 | 5.825 / 15.68 | 5.662 / 15.67 |
| 2024 | 10.677 / 8.27 | 11.314 / 8.53 | 10.372 / 8.21 | 10.030 / 8.22 | 10.938 / 8.22 | 10.560 / 8.23 | 10.423 / 8.24 |
| dev4 mean / worst / maxDD / losing | 5.601 / 2.588 / 16.91 / 0 | 6.566 / 4.365 / 16.10 / 0 | 5.740 / 3.578 / 17.22 / 0 | 5.249 / 2.866 / 18.35 / 0 | 5.992 / 3.419 / 16.58 / 0 | 5.662 / 2.991 / 17.03 / 0 | 5.465 / 2.707 / 17.48 / 0 |
| full-path DD | 16.82 | 16.01 | 17.14 | 18.26 | 16.49 | 16.94 | 17.39 |

Gains over G2 dev4 mean (+pp): R100 f=0.25 +0.965, R087 f=0.25 +0.139,
R080 f=0.25 -0.352; f=0.10: +0.391 / +0.061 / -0.136. Robust criterion on dev4
(DD<=20, no losing year, then highest worst-year): R100 (worst 4.365) >
R087 (3.578) > R080 (2.866) — the ORIGINAL V2 still wins; consistent
repricing does not improve selection.

## Most recent year 2025-09-24..2026-09-23, scored ONCE (labelled descriptive)

R087 f=0.25: 4.946 %/mo, DD 15.20, end 1.785. G2 ref: 4.648 / 12.90.
(For context, r=1.0's seen rows: overlay f=0.25 5.780/13.70. No selection was
or will be made on this year.)

## Gap stress, worst minute 2024-01-03 14:00 UTC (R087's own worst minute coincides with C4's)

Method reproduced for R100 first (worst ret -5.58%, acct 1.487041, G2_mix
0.3456/0.3456, combined 5.65/8.74/-2.46/-3.23 — all to the digit vs C4.json),
then R087 f=0.25 (worst ret -5.59%, acct 1.46583, same G2 mix, 2 open
straddles; shock sigma 1.5x sigma_true_asof). Loss % of combined equity:

| gap | G2 alone | R087 overlay | diff |
|---|---|---|---|
| -10% | 3.47 | 5.71 | +2.23 |
| -15% | 5.20 | 8.83 | +3.63 |
| +10% | -3.44 (gain) | -2.47 (gain) | +0.97 |
| +15% | -5.17 (gain) | -3.19 (gain) | +1.97 |

Down-gap overlay loss exceeds G2 alone by 2.2-3.6pp (the C4 +3pp bar passes at
-10% but fails at -15% by 0.6pp): the sleeve is NOT a crash hedge, consistent
with the -0.128 daily-P&L correlation in oc_vrpstraddle.

## Leakage statement

Feature timing: DVOL candle known at its close (last close <= decision; same
`dvol_known` truncation, tested); S at 08:04 known at 08:05; marks use latest
closed hourly DVOL only; settlement 07:30..07:59 known at 08:00; first event
09:00 so nothing fills in the first 5 min by construction; inexact 1m lookups
0 in every row. Label windows: payoffs use only post-entry minutes. Fit
windows: r=0.87/0.80 come from the pre-existing B.json term-structure study
(mostly 2021 + 2023-03 + 2025-06 Fridays), NOT refit here; no thresholds,
quantiles or calibration on any test year. Fill timing: options at model marks
(no book; bid/ask compressed into the 0.97/1.05 haircuts, labelled). Gap
shocks are post-hoc overlays. Causality/truncation tests in
tests/test_oc_vrpconsistent.py.

## Verdict

**R087 overlay f=0.25 dev4: mean 5.740 / worst 3.578 / DD 17.22 vs G2 5.601 /
2.588 / 16.91 — gain +0.139 pp mean, +0.990 pp worst, +0.31 DD. It beats G2 on
mean AND worst within DD <= G2+0.5, BUT the R080 stress row (5.249) loses
0.352 pp vs G2, over the 0.3 pp bar — NOT adopt-worthy as a PAPER candidate.
The dev4 robust winner stays R100 (original V2). Negative result, honestly
earned: pricing the short end at its own (lower) IV removes the edge that made
V2 work — the "premium" was DVOL overpricing, not a harvestable VRP at 7d.**

Tiếng Việt:
Kết quả âm: R087 hơn G2 một chút nhưng R080 mất 0,35 điểm, vượt ngưỡng 0,3 nên bị loại làm ứng viên paper.
Biến thể thắng trên dev4 vẫn là R100 (V2 gốc); định giá nhất quán không cải thiện lựa chọn.
Năm gần nhất chỉ mang tính mô tả, không dùng để chọn; không triển khai tiền thật.
