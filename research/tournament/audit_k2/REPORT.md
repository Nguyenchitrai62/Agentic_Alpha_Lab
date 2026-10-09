# audit_k2 — REPORT (blind replication of the Kronos K2 dip tilt on G2)

## What was done
Independent blind implementation of K2 (risk=-low1, direction=sign Spearman,
q20/q80 edges, mult 1.25/0.75/1, missing->1) on G2 (v421 inv k1.0 kd1.7 bear G2.0,
per-(coin,holding-bar) tilt copied from v414, budget unchanged), 4-phase engine
via heavy_slot. REF from v421_runs.pkl bit-exact (reproduced 5.41/16.91/16.82).
replication.json saved BEFORE opening any oc_kronoshidden output; comparison after.

## Results (4-phase reset %/mo, yearly DD in brackets; contamination: dev = UPPER BOUND)

| row | 2021 | 2022 | 2023 | 2024 | dev4 | 2025-09-24..2026-09-23 (clean, ONCE) | 5y | full-path DD |
|---|---|---|---|---|---|---|---|---|
| REF (G2) | 2.588 (10.86) | 3.282 (16.91) | 6.045 (15.81) | 10.677 (8.27) | 5.601, W 2.588, DD 16.91 | 4.648 (12.90) | 5.410, W 2.588 | 16.82 |
| K2 (blind) | 2.469 (11.78) | 3.478 (16.20) | 6.679 (15.69) | 10.653 (8.54) | 5.772, W 2.469, DD 16.20 | 4.801 (12.10) | 5.577, W 2.469 | 16.09 |

No losing year in dev4 or 5y for either row; DD <= 20 everywhere.
K2 vs REF: dev4 +0.171 pp/mo, clean year +0.153 pp/mo, full-path DD -0.73 pp.
K2 clean year 4.801 < 5.0 gate (b) — fails the gate despite beating REF.

## Comparison to oc_kronoshidden
Fits bit-identical (all 16 digits, all 5 anchors dir +1); engine R/DD identical
to the digit in all 5 years; full-path DD identical. Verdict: PASS-WITH-NOTES
(see COMPARISON.md; only note is the unused anchor_of() helper).

## What failed / why
Nothing failed in the replication itself. The K2 tilt replicates exactly but does
not pass the user gate on the clean year (4.801 < 5.0), agreeing with
oc_kronoshidden's own REJECT. No prospective evidence is created by this audit.

## Leakage checks
- Feature timing: tilt lookup (sym, shift, H=idx+4h) on that shift's table only;
  grids verified (hour-s)%4==0; forecast construction (400 bars <= T) taken as
  GIVEN from Part A features.
- Label windows: harness t_exit < A-7d only (test asserts truncation per anchor).
- Fit windows: shift-0 join only; 2025 fit uses rows t_exit < 2025-09-17; no test-year
  statistic feeds any fit.
- Fill timing: engine win_start=5, 1m trade-through only, stop-first (inherited
  from v421/v414 path; asserted in source).
- Costs: gate maker 0.0002 / taker 0.00055, longs 0.0001/8h, shorts 0.

## Vietnamese verdict (3 lines)
K2 tái tạo khớp hoàn toàn, năm sạch chỉ 4,80%/tháng nên không qua cổng 5%/tháng.
Dev là cận trên do Kronos đã thấy dữ liệu lúc pretrain, không adopt tilt này vào G2.
Kết luận: REJECT — cần bằng chứng prospective, đồng ý với oc_kronoshidden.
