# oc_c2frontier — REPORT (2026-10-08; engine + scoring complete, pytest 4/4)

Question: does the Chronos C2 dip tilt move the BOT return/drawdown frontier outward
(DD < 15 goal)? PLAN.md was written BEFORE any outcome; no definition changed after
outcomes. Engine via heavy_slot (sequential, heartbeat 600 s). pytest 4/4.

STATUS: DONE. 5 new engine configs x 4 phases = 20 phase sims (full-window [DEV0,Y1),
CPU scoring). Reproduction gates PASS to the digit. Post-release year scored ONCE
(labelled below; G2/G2+C2 Y4 quoted read-only from oc_chronos, never rescored).

## 0. Reproduction gates (PASS, to the digit — else STOP)

- G2 (stored `v421_runs.pkl` strat R2B1D17BFG2, scored CPU here): years
  2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27, 4.648/12.90 == v421_result.json.
- D13BF_base (kd 1.3, bear, no G cap, tilt 1, new engine): years 2.485/10.21,
  3.286/14.98, 4.975/14.76, 9.526/7.33, 4.723/10.97; 5y 4.971; full-path DD 14.86
  == v424 R2B1D13BF to the digit (validates kd parameterisation + no-G path).
- G2 / G2+C2 quoted read-only from oc_chronos (its own gates PASS to the digit).

## 1. Binance base — dev4 (UPPER BOUND: Chronos-Bolt released 2024-11, dev possibly-contaminated)

4-phase reset %/mo (yearly DD) [2021, 2022, 2023, 2024] | dev4 mean / WORST / maxDD:

| row | y0 | y1 | y2 | y3 | mean | WORST | maxDD |
|---|---|---|---|---|---|---|---|
| D13BF | 2.485/10.21 | 3.286/14.98 | 4.975/14.76 | 9.526/7.33 | 5.033 | 2.485 | 14.98 |
| D13BF+C2 | 2.458/10.04 | 3.269/14.24 | 6.093/15.62 | 9.681/7.13 | 5.338 | 2.458 | 15.62 |
| G2 (quoted) | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 5.601 | 2.588 | 16.91 |
| G2+C2 (quoted) | 2.711/11.52 | 3.460/15.48 | 6.250/15.07 | 10.721/8.29 | 5.739 | 2.711 | 15.48 |
| G2K20+C2 | 2.982/13.26 | 3.601/16.40 | 7.029/15.87 | 11.710/9.37 | 6.275 | 2.982 | 16.40 |

No losing dev year anywhere. C2 lifts dev4 mean on both bases (+0.305 on D13BF,
+0.138 on G2 per oc_chronos). All-trade win rates move <= 0.002 (sizing, not selection).

## 2. Binance base — 5y + full-path DD + Y4 scored ONCE

| row | 5y R | 5y W | full-path DD | maxDD_full* | Y4 R/DD (ONCE) |
|---|---|---|---|---|---|
| D13BF | 4.971 | 2.485 | 14.86 | 14.98 | 4.723/10.97 (reproduces v424, not new) |
| D13BF+C2 | 5.222 | 2.458 | 14.91 | 15.62 | 4.760/11.17 (new, +0.037 vs D13BF) |
| G2 (quoted) | 5.410 | 2.588 | 16.82 | 16.91 | 4.648/12.90 (oc_chronos, not rescored) |
| G2+C2 (quoted) | 5.542 | 2.711 | 15.42 | 15.48 | 4.754/12.86 (oc_chronos, +0.106) |
| G2K20+C2 | 5.983 | 2.982 | 16.24 | 16.40 | 4.826/13.73 (new; vs v422 G2K20 4.716: +0.110) |

\* maxDD_full = max(max yearly DD, full-path DD). 5y gaps (new, Binance): D13BF+C2 -
D13BF = +0.251; G2K20+C2 - v422 G2K20 (5.874/17.69) = +0.109 with -1.45 pp full-path DD.
Y4 book/all win (new rows): D13BF 0.5357/0.6298 vs D13BF+C2 0.5383/0.6303;
G2K20+C2 0.5343/0.6251.

## 3. Bybit prices S5 (D13BF rows; y2021 SHORT from 2021-11-15, labelled)

| row | dev4 mean/W/maxDD | 5y R/W | full-path DD | maxDD_full | Y4 R/DD (ONCE) |
|---|---|---|---|---|---|
| D13BF_S5 | 4.492/1.945/16.00 [1.945/9.88*, 2.889/16.00, 4.054/15.98, 9.228/7.57] | 4.482/1.945 | 15.95 | 16.00 | 4.443/10.75 (new) |
| D13BF+C2_S5 | 4.889/1.887/15.67 [1.887/10.06*, 2.847/15.64, 5.617/15.67, 9.363/7.62] | 4.795/1.887 | 15.61 | 15.67 | 4.422/10.91 (new, -0.021 vs D13BF_S5) |

\* SHORT window. C2 adds +0.397 dev4 / +0.313 5y on Bybit but the clean-year gap is
-0.021 (same non-transfer lesson as oc_chronos dev pick). Y4 all-win: 0.6285 vs 0.6282.

## 4. Frontier table (5y R %/mo, full-path DD) vs known points

| row | 5y | full DD | source |
|---|---|---|---|
| D13BF | 4.971 | 14.86 | v424 quoted + reproduced here |
| D13BF+C2 (Binance) | 5.222 | 14.91 | NEW |
| G2 | 5.410 | 16.82 | oc_chronos quoted |
| G2+C2 (Binance) | 5.542 | 15.42 | oc_chronos quoted |
| G2K20+C2 (Binance) | 5.983 | 16.24 | NEW (base v422 G2K20: 5.874/17.69) |
| D13BF_S5 (Bybit) | 4.482 | 15.95 | NEW |
| D13BF+C2_S5 (Bybit) | 4.795 | 15.61 | NEW |
| v409_D15B08 (known) | 4.626 | 14.94 | frontier_table.csv |
| v423_X45 (known) | 5.118 | 15.81 | frontier_table.csv |

On Binance the frontier DOES shift outward: D13BF+C2 (5.222/14.91) beats the old
DD<15 corner (D13BF 4.971/14.86, v409 4.626/14.94) with full-path DD still < 15
(max yearly DD 15.62 noted). But the assignment question is on Bybit prices: NO —
D13BF+C2_S5 is 4.795/15.61, short of both thresholds.

## 5. Leakage / causality checks (how verified)

- Feature timing: Chronos forecast for bar open T uses ONLY the 512 closes ending at the
  bar closing at T on that shift's grid (inherited Part A); tilt reads only (coin,
  holding-bar T) ch_q10. `test_c2_truncation_causal_on_frozen_features` recomputes C2
  multipliers from a truncated frozen feature table — identical on the kept prefix;
  multiset in {0.75, 1.0, 1.25}. `anchor_of` boundaries tested.
- Label windows: fits.json reused frozen (harness rows t_exit < A - 7d, shift-0 only);
  year y uses anchor-y fit only, never a later anchor.
- Fit windows: no refit here; S5 is a price-source switch, not a fit.
- Fill timing: win_start=5 asserted in `test_row_configs_match_plan` (S5 live0 2021-11-15 +
  Bybit dir in source); engine fills only on 1m trade-through with stop-first (inherited
  harness). kd/G/F constants asserted (D13BF 1.3/no-cap, G2K20_C2 2.0/2.0, F 2.5).
- Gate costs inside the engine (maker 0.0002 / taker 0.00055 / longs pay 0.0001 per 8h).
- `tests/test_oc_c2frontier.py` 4/4 pass.

## 6. Post-hoc log

- No PLAN definition changed after outcomes. All 5 rows scored as pre-registered;
  reproduction gates passed to the digit (G2==v421, D13BF==v424).

## Vietnamese verdict (3 lines)

- Trên giá Binance, C2 đẩy frontier ra ngoài: D13BF+C2 đạt 5,22%/tháng với full-path DD 14,91 (< 15), hơn hẳn D13BF gốc (4,97/14,86); G2K20+C2 đạt 5,98/16,24 (hơn G2K20 gốc 5,87/17,69).
- Nhưng trên giá Bybit (S5) thì KHÔNG: D13BF+C2 chỉ 4,80%/tháng với full-path DD 15,61 (D13BF gốc 4,48/15,95), năm sạch còn thua nhẹ -0,02; không có hàng nào vừa 5y >= 5 vừa full-path DD < 15.
- Kết luận: REJECT cho mục tiêu DD < 15 của BOT — tilt C2 dịch frontier trên Binance nhưng bay hơi trên giá Bybit, cần thêm bằng chứng prospective trước khi dùng.
