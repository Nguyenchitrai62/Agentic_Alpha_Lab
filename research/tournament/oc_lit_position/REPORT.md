# oc_lit_position REPORT — literature book gates H6 (OI throttle) + H8 (MVRV-z timing)

PLAN.md was written BEFORE any engine run; no threshold/multiplier/window was changed after
outcomes (only a pytest synthetic-window fix before the first real-data check). Gate costs: maker
0.0002, taker 0.00055, longs pay 0.0001/8h (00/08/16 UTC), shorts nothing; limits fill only on 1m
trade-through, no fill in the first 5 min after a 4h close (`win_start=5`); stop-first in the same
1m bar.

## Data (binding IDEAS4 C sources; span verified 2026-10-07, no outcomes)

- H6: `data/raw/um_metrics_20260926/*USDT_metrics.parquet` (`sum_open_interest`, 5-min). BTC
  2020-09-01..2026-09-24; ETH/SOL/BNB/XRP 2021-12-01..2026-09-24 (456d missing). First ~68d of
  anchor year 2021 + warmup default to NO gate for non-BTC (multiplier 1), never imputed.
  `metrics_ext_20260924` is a redundant BTC-only 2026 subset, UNUSED (same as `oc_i2_oiguard`).
- H8: `data/raw/onchain_20260924/btc.csv` (CoinMetrics free, daily). 2019-01-01..2026-09-23, so
  all anchors covered; no skipped anchor year for M1/M2. `CapMVRVCur` (0.75..3.96, mean 1.76) is
  the MVRV ratio itself, used directly as MVRV(D). No ETH MVRV history exists in the folder, so
  M3 (ETH analogue) is SKIPPED, disclosed, never imputed.
- Signals: H6 `d7 = ln(OI_now/OI_7d)` (5-min-lag as-of), `z = (d7-mean)/std` over trailing <=2190
  prior 4h bars (min 540, strictly pre-T); O1 longs x0.5 if z>2.0, O2book if z>1.5. H8
  `zM = (MVRV-mean)/std` over trailing <=365d (min 180, ending at D inclusive), day D usable from
  D+1 02:00 UTC; M1 longs x0.5 if z>2.0; M2 adds x1.1 if z<0 (gross cap G=2.0 still enforced).
  M1/M2 gate ALL majors' longs (BTC cycle signal); O1/O2 gate per-coin longs.

## Baseline reproduction (read-only + harness, else stop)

PASS. Cached G2 (`v421_runs.pkl` + `v421_result.json`) via `reset_metric.year_reset` + `v388.mix`:
5.41 %/mo, W 2.588, max yearly DD 16.91, full-path DD 16.82, yearly rows
[2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27, 4.648/12.9] — to the digit. The engine
harness re-ran G2 bit-exact (same triple), so overlays are comparable. Dip base reproduced exactly:
22312 fills, 5y 4-phase-mean sum 7.718304 (0.9113/0.8326/2.0998/3.1974/0.6772).

## Leg 0 — O2 dip leg (gates the O2 engine row; FAILED, so no O2 engine)

O2dip = skip new dip bids where H6-O2 fires (z>1.5 at bar open). Fires ~4-6% of (phase,coin) bars
(BTC ~570-584, ETH ~448-458, SOL ~557-562, BNB ~597-608, XRP ~447-456 per phase); removed 2389
fills (10.7%). Screen vs placebo gate (+0.273, full PROMISING legs):

| year | base S/DD | O2dip S/DD |
|---|---|---|
| 2021-22 | 0.9113 / 0.856 | 0.6721 / 0.862 |
| 2022-23 | 0.8326 / 0.951 | 1.0282 / 0.851 |
| 2023-24 | 2.0998 / 0.800 | 1.8805 / 0.848 |
| 2024-25 | 3.1974 / 0.355 | 2.6111 / 0.358 |
| 2025-26 | 0.6772 / 0.607 | 0.5160 / 0.643 |

sum>=base 1/5, DD ok 3/5, dSum5y -1.010 (dev4 -0.849) vs gate +0.273 → NOT PROMISING. The skip deletes
net-winning rungs in 3/5 years (same failure mode as `oc_i2_oiguard` and `oc_velocity`). Per PLAN,
NO O2 engine row was run (combined rejected at the screen).

## Leg 1 — book gates (4-phase engine; selection ONLY on dev 2021-2024)

Mechanism = v426 copy (multiplier on STANDARD book rows with bear-filtered weight>0, after the bear
filter, before shifted-clock ffill; pre-2021-09-24 rows not gated). Controls = per-year constant
long multiplier equal to the variant's realised mean over long rows (exposure-matched, no timing).

| dev year | G2 R/DD | O1 R/DD | CTRL_O1 R/DD | M1 R/DD | CTRL_M1 R/DD | M2 R/DD | CTRL_M2 R/DD |
|---|---|---|---|---|---|---|---|
| 2021-22 | 2.588 / 10.86 | 2.552 / 11.25 | 2.613 / 10.88 | 2.588 / 10.86 | 2.588 / 10.86 | 2.480 / 11.17 | 2.535 / 10.94 |
| 2022-23 | 3.282 / 16.91 | 3.239 / 17.02 | 3.299 / 17.01 | 3.367 / 16.26 | 3.264 / 17.00 | 3.520 / 16.20 | 3.141 / 17.02 |
| 2023-24 | 6.045 / 15.81 | 5.673 / 15.80 | 6.149 / 15.82 | 7.824 / 13.73 | 6.836 / 16.01 | 7.843 / 13.73 | 6.749 / 15.97 |
| 2024-25 | 10.677 / 8.27 | 10.610 / 8.68 | 10.661 / 8.36 | 11.218 / 9.99 | 10.436 / 8.46 | 11.440 / 9.87 | 10.520 / 8.31 |
| dev4 mean / worst / DD | 5.601 / 2.588 / 16.91 | 5.472 / 2.552 / 17.02 | 5.634 / 2.613 / 17.01 | 6.192 / 2.588 / 16.26 | 5.735 / 2.588 / 17.00 | 6.261 / 2.480 / 16.20 | 5.688 / 2.535 / 17.02 |

Full-5y context (engine byproduct for the no-candidate case; NOT a selection input — the most
recent year was not scored for gated variants): G2 5.41/16.91/full 16.82; O1 5.328/17.02/16.98;
M1 5.881/16.26/16.22; M2 5.939/16.20/16.14; CTRL_O1 5.421/17.01/16.95; CTRL_M1 5.519/17.00/16.95;
CTRL_M2 5.523/17.02/16.95. M1/M2 2025 rows equal G2 (4.648; gate never fires in 2025) — byproduct only.
Gated share of book long cells (standard index): O1 1.0-3.1%/yr; M1 0% in 2021+2025, 3.3% in 2022,
45.4% in 2023, 6.4% in 2024; M2 29-92%/yr (x1.1 add fires most bars). Mean mults: O1 0.984-0.995;
M1 1.0/0.984/0.773/0.968; M2 level-dominated (see per-year table in engine run).

Strict TEMPLATE verdict (dev4; candidate iff mean>5.601 AND worst>2.588 AND DD<=17.41 AND beats
control): O1 FAILS mean (5.472<5.601), worst (2.552<2.588) and control (5.472<5.634). M2 FAILS worst
(2.480<2.588) despite mean/control/DD passes. M1 passes mean (6.192), DD (16.26) and control
(6.192>5.735) but TIES worst (2.588==2.588 — the gate never fires in the 2021 worst year, so it
cannot lift it) → NOT a strict candidate (3/4). Robust view: M1 is the best leg (mean>=5, tied-best
worst, DD ok, beats control) but the gains concentrate in 2023 (+1.78pp) with a DD cut there
(15.81→13.73) at the cost of higher 2024 DD (8.27→9.99). Chosen variant: NONE. No adoption.

## Leakage / causality checks (how verified)

- Feature timing: H6 OI as-of `<= T-5min` (searchsorted right-1), H8 daily as-of `D+1 02:00 <= T`;
  `test_h6_truncation_causal` recomputes z after causal truncation (matches to 1e-12);
  `test_h8_truncation_and_availability` checks the D+1 02:00 boundary (±1s) and truncated-window z;
  `test_handchecked_synthetic_h6` checks flat-OI NaN (no false fires) and the ln2 doubling.
- Label windows: none fitted (engine uses realised 1m path; dip uses realised exits).
- Fit windows: no fits — rolling norms are causal features (windows end at/before T, all inputs at
  their own availability); thresholds (2.0/1.5/0) and multipliers frozen in PLAN; CTRL means are
  realised-exposure only per year.
- Fill timing: engine `win_start=5` + 1m trade-through + stop-first (v426 harness, G2 bit-exact);
  dip live 16..238 strict `low<level`, stop-first race, timeout at next-bar open (verbatim replica).

## Post-hoc log

- No definition changes after outcomes (thresholds, multipliers, windows, rules identical to PLAN).
- pytest synthetic fix before the first real-data check (H6 test grid 30d→130d: 60 bars cannot meet
  the 540-obs minimum — test-only, no signal change). O2 engine skipped per PLAN (dip failed), not
  a change. M3 skipped per PLAN (no ETH history), not a change.

## Vietnamese verdict (3 lines)

- Từ chối áp dụng cả hai cửa sổ book H6/H8: O1 thua G2 và thua cả control trên dev4, chân dip O2 bị loại ở màn hình replica (dSum -1,01 so với ngưỡng +0,273) nên không chạy engine, M2 cải thiện trung bình nhưng làm tệ đi năm xấu nhất.
- M1 (MVRV-z halving) là chân tốt nhất theo nghĩa robust (dev4 6,19 so với G2 5,60, DD 16,26, vượt control 5,74) nhưng hòa năm xấu nhất (2,588) nên không đạt chuẩn strict và hiệu quả dồn vào 2023 — chưa đủ để adopt, chỉ đáng ghi paper-log prospective.
- Đóng hướng gate ngưỡng cố định dạng này; nếu muốn cứu M1 thì chỉ bằng bằng chứng prospective ngoài mẫu, không tinh chỉnh thêm trên dữ liệu cũ.
