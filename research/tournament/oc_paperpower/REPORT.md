# oc_paperpower REPORT — how much paper evidence do the go-live gates need?

Method per pre-registered PLAN.md. Research return process: G2 (R2B1D17BFG2
4-phase) + carry f = 0.25 continuous full-path hourly close equity, built
EXACTLY as oc_carrycompound/analyze_carrycompound.py (same grid, same
last-CLOSED-hourly marking, same fees, same N = f x live A recursion), then
causal daily-last returns over 2021-09-24..2026-09-23 (1825 values, descriptive,
no selection). Fixed 10-day block bootstrap exactly as
scripts/prospective_scorecard.py (non-circular starts, 5000 paths per
scenario x horizon, seed 0); horizons 8/12/26/52w = 56/84/182/364d. Scenarios:
S_good as-is; S_half mean halved; S_zero zero mean; S_neg mean -1 %/month
(mu_neg = (1-0.01)^(1/30.4167)-1/day). PASS = (cumret >= p20 of S_good same
horizon) AND (daily-close maxDD <= 15 %); STOP = (maxDD > 20 %) OR (cumret < p5).
Sensitivity: full repeat with 30-day blocks. Repro:
`.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_paperpower
--min-free-gb 2.0 -- .venv/Scripts/python.exe
research/tournament/oc_paperpower/analyze_paperpower.py` + test
`tests/test_oc_paperpower.py`. No engine rerun, no 1m, no GPU, seed fixed.

## G2 baseline reproduced (validation gate PASS)
f = 0 reproduces v421_result R2B1D17BFG2 TO THE DIGIT (asserted in-script):
R 5.41 / W 2.588 / DD 16.91 / full-path DD 16.82 (marked 16.82 / close 16.05).

## Research context (reset metric %/mo R / DD %; most-recent year labelled)
| year | G2 (f=0) | G2+carry f=0.25 (study process) |
|---|---|---|
| 2021-09-24 | 2.588 / 10.86 | 2.778 / 10.86 |
| 2022-09-24 | 3.282 / 16.91 | 3.353 / 16.75 |
| 2023-09-24 | 6.045 / 15.81 | 6.590 / 15.69 |
| 2024-09-24 | 10.677 / 8.27 | 10.956 / 8.20 |
| 2025-09-24 (most recent, context only) | 4.648 / 12.90 | 4.698 / 12.66 |
| 5y mean / worst / maxDD / losing | 5.410 / 2.588 / 16.91 / 0 | 5.634 / 2.778 / 16.75 / 0 |
| full-path DD (marked/close/full) | 16.82 / 16.05 / 16.82 | 16.66 / 15.90 / 16.66 |
Carry add +0.224 pp/mo matches oc_carrycompound. Daily stats (1825 returns):
mean +0.194 %/day, std 1.256 %/day, min -11.22 %, max +12.75 %.

## Power table, 10-day blocks (PASS % | STOP %; p20/p5 = S_good cumret cuts)
| horizon | p20 / p5 cumret % | S_good | S_half | S_zero | S_neg |
|---|---|---|---|---|---|
| 8w (56d) | +1.28 / -5.21 | 79.8 / 5.0 | 59.0 / 16.1 | 38.3 / 35.5 | 32.0 / 43.6 |
| 12w (84d) | +4.28 / -4.28 | 79.4 / 5.1 | 55.1 / 18.9 | 30.8 / 43.2 | 25.0 / 51.5 |
| 26w (182d) | +18.65 / +2.59 | 76.6 / 6.1 | 41.1 / 27.6 | 13.7 / 64.2 | 8.1 / 74.5 |
| 52w (364d) | +54.89 / +25.96 | 68.8 / 8.6 | 23.9 / 45.4 | 2.5 / 87.6 | 1.0 / 94.5 |
False-pass (PASS under no edge): S_zero 38.3 / 30.8 / 13.7 / 2.5 %;
S_neg 32.0 / 25.0 / 8.1 / 1.0 %. True-pass (S_good): 79.8 / 79.4 / 76.6 / 68.8 %
(< 80 % because the DD <= 15 % leg also binds a good process).

## Sensitivity, 30-day blocks (PASS % | STOP %)
| horizon | S_good | S_half | S_zero | S_neg |
|---|---|---|---|---|
| 8w | 80.0 / 5.0 | 57.1 / 19.6 | 37.9 / 42.6 | 33.1 / 49.5 |
| 12w | 79.6 / 5.0 | 54.2 / 21.1 | 33.9 / 46.5 | 27.8 / 53.5 |
| 26w | 77.2 / 5.5 | 43.9 / 29.7 | 15.4 / 64.6 | 9.3 / 74.7 |
| 52w | 71.8 / 6.4 | 25.2 / 46.8 | 2.9 / 87.1 | 1.1 / 93.6 |
Same picture: longer blocks do not rescue short horizons.

## Recommendation (pre-registered rule: shortest horizon with S_zero PASS <= 20 %)
26 weeks. 8 weeks is plainly weak: a zero-edge process passes the combined
percentile+DD gate 38 % of the time (a -1 %/month process 32 %), and the STOP
rule catches only ~36-44 % of them. 12 weeks is still weak (31 % / 25 %
false-pass). At 26 weeks the false-pass falls to 14 % / 8 % with 64-75 % STOP;
at 52 weeks to 3 % / 1 % with ~88-94 % STOP. Cost of waiting: even a good
process passes only ~77 % at 26w (~69 % at 52w) because the DD <= 15 % leg binds.

## What this does NOT cover / what failed
- Divergence (paper-vs-plan <= 1.5 pp/month) and cycle_error (> 1 h) are live
  execution checks; nothing here simulates them. Nothing failed to run; the
  f = 0 digit-reproduction gate passed first try.
- Optimistic biases (all push true sharpness DOWN): daily-close DD understates
  the official max(4h-close, 1m-marked) DD, so real PASS rates are lower and
  real STOP rates higher than tabled; reference and scenarios share the same
  five in-sample years (descriptive, not OOS).

## Leakage / timing check
Features: hourly carry marks use only the last CLOSED hourly bar strictly
before t (`searchsorted(..., side="left") - 1`); daily E[d] uses only A_c <= D[d]
(E[2021-09-24] seeded with A_c[0], disclosed in PLAN). Labels: none (returns are
resampled as printed). Fits/thresholds: none fitted; p20/p5 are descriptive
quantiles of the same five years (no selection feeds back). Fills: gate costs
already inside the equity (maker 0.0002 / taker 0.00055, gate funding, no
1m trade-through simulated here — returns only). No statistic from this study
feeds any model, threshold, or deployment choice.

## Verdict (3 dòng tiếng Việt)
- 8 tuần QUÁ YẾU: process zero-edge vẫn PASS ~38 % (lỗ 1 %/tháng vẫn ~32 %), đừng go-live chỉ vì qua cổng 8 tuần.
- Cần ít nhất 26 tuần để false-pass rớt dưới 20 % (còn ~14 % / 8 %); 52 tuần mới thật sự chắc (~3 % / 1 %).
- Không đổi triển khai từ nghiên cứu này; giữ nguyên cổng paper 8 tuần tối thiểu nhưng coi đó chỉ là điều kiện cần.
