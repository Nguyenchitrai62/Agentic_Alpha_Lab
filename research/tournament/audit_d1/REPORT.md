# audit_d1 — REPORT (blind replication of the downside-share D1 dip tilt on G2)

## What was done
Independent blind implementation of D1 (risk = trailing-6d downside-RV
share, direction = sign Spearman, q20/q80 edges, mult 1.25/0.75/1,
missing -> 1) on G2 (v421 rule inv k1.0 kd1.7 bear G2.0, per-(coin,
holding-bar) tilt copied from v414 via audit_c2, budget unchanged),
feature rebuilt from raw 4h closes, 4-phase engine via heavy_slot. REF from
v421_runs.pkl bit-exact (reproduced 5.41/16.91/16.82). replication.json
saved BEFORE opening any oc_downshare output; comparison after. PLAN.md
pre-registered before any outcome.

## Results (4-phase reset %/mo, yearly DD in brackets)

| row | 2021 | 2022 | 2023 | 2024 | dev4 | 2025-09-24..2026-09-23 (clean, ONCE) | 5y | full-path DD |
|---|---|---|---|---|---|---|---|---|
| REF (G2) | 2.588 (10.86) | 3.282 (16.91) | 6.045 (15.81) | 10.677 (8.27) | 5.601, W 2.588, DD 16.91 | 4.648 (12.90) | 5.410, W 2.588 | 16.82 |
| D1 (blind) | 2.921 (12.59) | 3.604 (16.09) | 6.541 (15.74) | 10.191 (8.19) | 5.776, W 2.921, DD 16.09 | 4.591 (13.38) | 5.538, W 2.921 | 15.98 |

No losing year in dev4 or 5y for either row; DD <= 20 everywhere.
D1 vs REF: dev4 +0.175 pp/mo, worst-year +0.333 pp/mo, full-path DD -0.84 pp;
clean year -0.057 pp/mo.
D1 clean year 4.591 < 5.0 gate (b) — fails the gate despite winning dev4
on the robust criterion.

## Comparison to oc_downshare
Features agree (max abs diff 5.27e-12, 0 rows over 1e-9, NaN positions
identical); fits agree to ~1e-13 (all 5 anchors dir +1/-1/-1/+1/+1);
engine R/DD identical to the digit in all 5 years; multiplier vectors
2000/2000 agree; full-path DD identical. Verdict: PASS-WITH-NOTES
(see COMPARISON.md; only note is the unused anchor_of() helper).

## What failed / why
Nothing failed in the replication itself. The D1 tilt replicates exactly
but does not pass the user gate on the clean year (4.591 < 5.0, -0.057 vs
REF), agreeing with oc_downshare's own REJECT. No prospective evidence is
created by this audit.

## Leakage checks
- Feature timing: D1 share for bar open T uses ONLY the 36 returns
  r[E-36..E-1] of bars closing <= T on that shift's grid
  (oc_downshare/build_downshare.py:42-47; ours build_d1.py); 200 random
  risk_D1 rows recomputed from bars truncated at T match stored values
  (max diff 2.5e-12; research/tournament/audit_d1/check_truncation.py +
  tmp/truncation_check.json).
- Label windows: harness t_exit < A-7d only (test asserts truncation per anchor).
- Fit windows: shift-0 join only; 2025 fit uses rows t_exit < 2025-09-17; no
  test-year statistic feeds any fit.
- Fill timing: engine win_start=5, 1m trade-through only, stop-first
  (inherited from v421/v414 path; asserted in source).
- Costs: gate maker 0.0002 / taker 0.00055, longs 0.0001/8h, shorts 0.

## Vietnamese verdict (3 lines)
D1 tái tạo khớp hoàn toàn, thắng dev4 về worst-year nhưng năm sạch chỉ 4,59%/tháng nên không qua cổng 5%/tháng.
Không phát hiện leakage: đặc trưng chỉ dùng 36 close <= T, fit chỉ dùng hàng t_exit < A-7d, fill win_start=5 trade-through stop-first.
Kết luận: PASS-WITH-NOTES — đồng ý REJECT của oc_downshare, không cần bằng chứng prospective.
