# oc_amihudbybit REPORT — venue-consistent Amihud tilt (POST-HOC, labelled)

AB1 = A1 with Amihud from BYBIT daily built from `data/raw/bybit_linear_1m_20261004`
(1m linear perps 2021-06-01..2026-10-03; daily |close-to-close return| / daily
turnover in USDT — USES THE TURNOVER COLUMN, present for all 5 symbols).
Same 30d window (min 20), same D+1 00:00 availability, same K=0.25,
clip [0.5,1.5], both-legs v426 slot as A1 (after bear filter, before
shifted-clock ffill; rows before 2021-09-24 untilted).
PLAN.md written before any engine run. POST-HOC: motivated by seeing A1 fail
the Bybit-price stress; even a win is paper evidence only, never deployment.
Gate costs: maker 0.0002, taker 0.00055, longs 0.0001/8h, shorts nothing;
limits fill only on 1m trade-through, no fill first 5 min (win_start=5),
stop-first same bar. Engine via heavy_slot (Pool 2).
Coverage: Bybit SOL starts 2021-10-15 so SOL Amihud30 is NaN until ~2021-11-03
(NaN->mult 1 fallback, same as A1); all-5-finite on 97.7% of decision times
(AB1 share tilted 0.974 in 2021, 1.0 after).

## Reproduction gate (PASS, to the digit)

Cached v421_runs.pkl: 5.41 / W 2.588 / DD 16.91 / full 16.82. Engine re-ran:
G2 dev4 5.601, A1 dev4 5.844, G2_S5 dev4 4.994 / 5y 4.883,
A1_S5 dev4 4.989 / 5y 4.884 — all match oc_amihudrobust to the digit.
Harness proof valid; S5 = Bybit 1m prices from 2021-11-15 (2021 = short window,
labelled), win_start=5, exactly as robust_v421.py.

## Base grid (Binance 1m prices) — dev4 selects, Y4/5y labelled byproducts

| dev year | G2 R/DD | A1 R/DD | AB1 R/DD | CTRL_AB1 R/DD |
|---|---|---|---|---|
| 2021-22 | 2.588/10.86 | 2.798/12.21 | 2.735/10.90 | 2.602/10.93 |
| 2022-23 | 3.282/16.91 | 3.395/16.81 | 2.930/17.60 | 3.311/16.79 |
| 2023-24 | 6.045/15.81 | 6.390/15.77 | 6.429/15.86 | 6.304/15.81 |
| 2024-25 | 10.677/8.27 | 10.987/8.42 | 11.112/8.34 | 10.669/8.27 |
| dev4 mean/W/DD | 5.601/2.588/16.91 | 5.844/2.798/16.81 | 5.748/2.735/17.60 | 5.674/2.602/16.79 |

Y4 labelled (2025-26, NOT a selection input): G2 4.648/12.90, A1 4.750/11.14,
AB1 4.935/10.86, CTRL 4.617/12.92.
5y labelled: G2 5.410/full-DD 16.82, A1 5.624/16.66, AB1 5.585/17.49,
CTRL_AB1 5.462/16.74.
Template check on base: AB1 beats G2 mean (+0.147) and worst (+0.147) and beats
control (+0.074), but max yearly DD 17.60 > 16.91+0.5=17.41 -> FAILS the DD leg.
AB1 also loses to A1 on dev4 (-0.096) and 5y (-0.039). Mean mult ~1.0
(1.0057/0.9988/0.9976/1.0005/0.9923 per year = CTRL constants).

## S5 grid (Bybit 1m prices, owner venue) — primary verdict grid

| dev year | G2_S5 R/DD | A1_S5 R/DD | AB1_S5 R/DD | CTRL_AB1_S5 R/DD |
|---|---|---|---|---|
| 2021-22* | 2.129/12.36 | 2.145/13.70 | 2.251/12.39 | 2.151/12.14 |
| 2022-23 | 2.735/18.11 | 2.316/18.58 | 2.281/19.95 | 2.723/18.11 |
| 2023-24 | 4.932/16.89 | 4.934/16.30 | 4.905/16.61 | 4.940/16.89 |
| 2024-25 | 10.377/9.22 | 10.789/8.83 | 10.954/8.34 | 10.349/9.22 |
| dev4 mean/W/DD | 4.994/2.129/18.11 | 4.989/2.145/18.58 | 5.039/2.251/19.95 | 4.992/2.151/18.11 |

\* 2021 S5 year is a short window (from 2021-11-15), labelled.
Y4 labelled (NOT a selection input): G2_S5 4.443/12.37, A1_S5 4.467/10.74,
AB1_S5 4.677/10.42, CTRL_S5 4.413/12.38.
5y labelled: G2_S5 4.883/full-DD 18.09, A1_S5 4.884/21.32,
AB1_S5 4.966/22.48, CTRL_S5 4.876/18.09.
Template check on S5: AB1_S5 beats G2_S5 mean (+0.045), worst (+0.122) and
control (+0.047), but max yearly DD 19.95 > 18.11+0.5=18.61 -> FAILS the DD
leg, and full-path DD 22.48 > 20 -> FAILS the gate DD. The 2022 year drives
both the return leak (2.281 vs 2.735) and the DD spike (19.95).

## Leakage / causality checks (how verified)

- Feature timing: Bybit day D from minutes < D+1 00:00 only;
  `test_signal_truncation_causal` recomputes Amihud30 at D0 from data truncated
  to <=D0 (matches 1e-12), checks the +-1s boundary exposes exactly the prior
  day, and sampled-T truncation leaves multipliers unchanged.
- A1 path bit-exact vs `oc_lit_xs/xs_signal.py` on sampled T (test asserts
  frame equality); G2/A1/G2_S5/A1_S5 engine numbers match oc_amihudrobust to
  the digit, so the v426 slot is unchanged.
- Label windows: none fitted (engine uses realised 1m path).
- Fit windows: no fits; XS mean/std at same T only; K/window/clip/side rules
  fixed in PLAN (copied from A1).
- Fill timing: win_start=5 + 1m trade-through + stop-first (asserted in test,
  same harness as oc_amihudrobust). `tests/test_oc_amihudbybit.py` passes (2).
- Turnover is a realised volume sum (no price lookahead); close_d is the last
  minute close of the day.

## Post-hoc log

- No definition changes after outcomes (signal, K, window, clip, side masks,
  control rule identical to PLAN). One pre-outcome code fix only: removed a
  leftover placeholder line in `build_tilt_frames_std` before the first
  engine launch. First engine run already included the to-the-digit G2/A1/S5
  re-runs.

## Vietnamese verdict (3 lines)

- AB1 (Amihud đo bằng volume Bybit) giữ được chênh lệch dương nhỏ trên giá Bybit
  (dev4 +0.045, 5y +0.083, năm gần nhất +0.234 khi chấm dán nhãn, hơn control
  +0.047) nhưng DD vượt ngưỡng: DD năm tệ nhất dev4 19.95 và DD full-path 22.48
  (>20), nên theo tiêu chí template/gate là KHÔNG đạt.
- Trên giá Binance gốc AB1 cũng rớt cửa DD (17.60 > 17.41) và thua A1
  (−0.096 dev4); hiệu ứng nhỏ, post-hoc 1-trong-nhiều biến thể nên nhiều khả
  năng là nhiễu/multiple-testing, không phải venue edge.
- Từ chối đưa AB1 vào G2; hướng venue-consistent đóng lại ở dạng tilt này, chỉ
  giữ làm bằng chứng paper; nếu theo đuổi phải giảm DD S5 trước bằng dữ liệu
  prospective ngoài mẫu.
