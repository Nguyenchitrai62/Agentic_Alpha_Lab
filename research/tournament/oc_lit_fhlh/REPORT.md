# oc_lit_fhlh REPORT — H3 first-half-hour -> rest-of-day intraday momentum gate on the book

Signal: BTC FH(D) = close(00:29 1m)/open(00:00 1m)-1 per calendar day D (00:00 UTC anchor),
from `data/raw/btc_intraday_20260924/klines_1m_*.parquet` (gap-free, 2020-01-01..2026-09-23,
so dev + median lookback fully covered; no skip, NaN -> mult 1).
FH(D) known at D+00:30; T in [D 00:00, D 00:30) uses D-1 (searchsorted right-1).
M3 medians per anchor on |FH| over [A-372d, A-7d): 2021 0.004229, 2022 0.002754,
2023 0.001315, 2024 0.001760, 2025 0.001561. BTC FH gates all symbols (paper is
BTC-only; disclosed). PLAN.md written before any outcome; no threshold/multiplier
changed after numbers. Gate costs: maker 0.0002, taker 0.00055, longs 0.0001/8h
(00/08/16 UTC), shorts nothing; limits fill only on 1m trade-through, no fill in
first 5 min (win_start=5), stop-first in same 1m bar.

## G2 reproduction (STOP gate passed)

Cached `v421_runs.pkl` via `reset_metric.year_reset` + `v388.mix`: 5.41 %/mo,
W 2.588, max yearly DD 16.91, full-path DD 16.82, yearly rows
[2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27, 4.648/12.9] — exact to the
digit. Engine harness re-ran G2 bit-exact (same triple), so overlays are comparable.
Mechanism = v426 copy: multiplier on STANDARD book rows with bear-filtered weight
on the affected side, after the bear filter, before the shifted-clock ffill;
rows before 2021-09-24 not gated. M1: longs 1.0 if FH>0 else 0.6. M2: M1 longs +
shorts 1.0 if FH<0 else 0.6 (FH==0 -> 0.6 both sides). M3: M1 unless |FH|<med(A).
CTRL_M1/M3: per-year constant long mult = realised M1/M3 mean over long cells;
CTRL_M2: same longs + per-year constant short mult = realised M2 mean over short cells.

## Selection (ONLY dev4 2021-2024; template rule: mean > 5.601, worst > 2.588, DD <= 17.41, beats control)

| dev year | G2 R/DD | M1 R/DD | M2 R/DD | M3 R/DD | CTRL_M1 R/DD | CTRL_M2 R/DD | CTRL_M3 R/DD |
|---|---|---|---|---|---|---|---|
| 2021-22 | 2.588 / 10.86 | 2.920 / 12.36 | 2.278 / 12.42 | 2.472 / 11.89 | 2.899 / 10.39 | 2.569 / 10.70 | 2.781 / 10.85 |
| 2022-23 | 3.282 / 16.91 | 3.025 / 16.87 | 3.232 / 17.07 | 2.947 / 17.34 | 2.893 / 16.50 | 2.976 / 16.75 | 3.209 / 16.86 |
| 2023-24 | 6.045 / 15.81 | 6.697 / 16.48 | 7.037 / 16.40 | 6.190 / 17.05 | 6.701 / 15.98 | 7.433 / 15.84 | 6.554 / 16.09 |
| 2024-25 | 10.677 / 8.27 | 10.623 / 8.62 | 10.725 / 8.58 | 10.678 / 8.06 | 10.691 / 9.78 | 10.652 / 9.78 | 10.645 / 8.88 |
| dev4 mean / worst / DD | 5.601 / 2.588 / 16.91 | 5.769 / 2.920 / 16.87 | 5.766 / 2.278 / 17.07 | 5.522 / 2.472 / 17.34 | 5.747 / 2.893 / 16.50 | 5.855 / 2.569 / 16.75 | 5.751 / 2.781 / 16.86 |

Gated share of long cells (M1/M3) and short cells (M2 shorts): Y0 46.9%/13.3%/52.7%,
Y1 47.8%/9.2%/51.6%, Y2 50.8%/31.7%/49.5%, Y3 51.4%/23.8%/46.3% (mean mult M1
0.79-0.81, M3 0.88-0.96, M2-shorts 0.79-0.81). Full-span gated: M1 13698/27652 longs,
M3 6035, M2-shorts 12341/24543. CTRL constants (long M1 / short M2 / long M3):
Y0 0.812/0.789/0.947, Y1 0.809/0.794/0.963, Y2 0.797/0.802/0.873, Y3 0.795/0.815/0.905.

Dev4 verdict: M1 PASSES all four template gates (+0.168 over G2, worst 2.920>2.588,
DD 16.87<=17.41, +0.022 over CTRL_M1). M2 FAILS (worst 2.278<2.588 and 5.766<CTRL 5.855).
M3 FAILS (mean 5.522<5.601 and <CTRL 5.751, worst 2.472<2.588). M1 is the sole candidate.

## Most recent year (scored ONCE for the candidate M1 + G2/CTRL_M1 only)

| 2025-26 | G2 | M1 | CTRL_M1 |
|---|---|---|---|
| R (%/mo) | 4.648 | 3.888 (-0.760 vs G2, -0.300 vs CTRL) | 4.188 |
| DD | 12.90 | 15.90 | 13.99 |

Full-5y context (engine byproduct, NOT selection): G2 5.41/16.91/full 16.82;
M1 5.390/16.87/16.81; M2 5.322/17.07/17.05; M3 5.338/17.34/17.30;
CTRL_M1 5.434/16.50/16.43; CTRL_M2 5.472/16.75/16.67; CTRL_M3 5.498/16.86/16.83.
M1's dev4 edge (+0.168, of which +0.146 is pure exposure level vs CTRL) reverses
out-of-selection: -0.76 vs G2 and -0.30 vs CTRL in 2025-26, worse DD, full-5y below
both G2 and its control. Timing value is +0.022 pp/mo on dev4 — noise against a
~50%-gated 0.6x exposure cut — and negative full-span (-0.044).

## Leakage / causality checks (how verified)

- Feature timing: FH uses 1m bars open_time in [D 00:00, D 00:29] only;
  `test_signal_truncation_causal` rebuilds FH(D0) from 1m truncated to <=D0 00:29
  (matches to 1e-12) and checks D0+00:30 +-1s exposes exactly D0 vs D0-1;
  medians recomputed by hand on [A-372d, A-7d).
- Label windows: none fitted (engine uses realised 1m path).
- Fit windows: M3 medians on FH days ending 7d before each anchor (no returns, no
  test-year data); signs/thresholds fixed in PLAN; CTRL means realised-exposure only.
- Fill timing: v426 harness verbatim (`win_start=5` + 1m trade-through + stop-first),
  proven by the bit-exact G2 re-run; `test_handchecked_synthetic` checks FH math,
  strict >0/<0 ties (0 -> 0.6 both sides), |FH|<med filter, NaN->1, and the
  D+00:30 availability mapping.

## Post-hoc log

- No definition changes after outcomes (variants, thresholds, multipliers, windows,
  median rule, tie rule identical to PLAN). One infra choice: daily FH cached to
  `tmp/daily_fh.parquet` so Pool workers load 2.5k rows instead of 3M 1m rows —
  no economic effect.

## Vietnamese verdict (3 lines)

- M1 đạt đủ 4 cửa template trên dev4 (+0,168 so với G2, worst 2,920, DD 16,87, hơn CTRL_M1 +0,022) nên là ứng viên duy nhất; M2/M3 bị loại ngay trên dev4 (worst thấp hơn G2 và thua CTRL).
- Năm gần nhất chấm một lần duy nhất cho M1 lại đảo chiều: 3,888 so với G2 4,648 (-0,76) và thua cả CTRL_M1 (4,188), DD tệ hơn (15,90 so với 12,90); full-5y M1 cũng dưới cả G2 và CTRL.
- Từ chối hướng gate FH->LH này: giá trị timing chỉ +0,022 điểm trên dev4 (nhiễu so với cú cắt exposure 0,6x trên ~50% lệnh long) và âm trên full-span; đóng H3, không cần thêm prospective cho dạng gate này.
