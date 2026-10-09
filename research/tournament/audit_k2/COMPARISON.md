# audit_k2 — COMPARISON (Part B, opened ONLY after replication.json was saved)

Blind replication of oc_kronoshidden K2 vs their frozen outputs.
Thresholds (pre-registered): R diff > 0.10 pp, DD diff > 0.5 pp,
fit params relative diff > 1e-6.

## Fits (per-anchor direction / q20 / q80)

| anchor | ours dir/q20/q80 | theirs dir/q20/q80 | match |
|---|---|---|---|
| 2021-09-24 | +1 / 0.8558204344393865 / 2.906580504669537 | +1 / same to all 16 digits | YES |
| 2022-09-24 | +1 / 0.5434502272474168 / 2.3279528773566973 | +1 / same | YES |
| 2023-09-24 | +1 / 0.5315151213063407 / 2.113581813474562 | +1 / same | YES |
| 2024-09-24 | +1 / 0.5753234142572279 / 2.193634112385982 | +1 / same | YES |
| 2025-09-24 | +1 / 0.5872428352509342 / 2.182801599162049 | +1 / same | YES |
n_train / n_joined identical (2338/2069, 4147/3878, 6002/5733, 8345/8076, 10056/9787).

## Engine (4-phase reset %/mo, yearly DD)

| year | REF ours | REF theirs | K2 ours | K2 theirs (dev/last_year) |
|---|---|---|---|---|
| 2021 | 2.588 (10.86) | 2.588 (10.86) | 2.469 (11.78) | 2.469 (11.78) |
| 2022 | 3.282 (16.91) | 3.282 (16.91) | 3.478 (16.20) | 3.478 (16.20) |
| 2023 | 6.045 (15.81) | 6.045 (15.81) | 6.679 (15.69) | 6.679 (15.69) |
| 2024 | 10.677 (8.27) | 10.677 (8.27) | 10.653 (8.54) | 10.653 (8.54) |
| 2025-09-24..2026-09-23 | 4.648 (12.90) | 4.648 (12.90) | 4.801 (12.10) | 4.801 (12.10) |
dev4: REF 5.601 / K2 5.772 (theirs 5.601 / 5.772). 5y: REF 5.41 / K2 5.577.
Full-path DD: REF 16.82 / K2 16.09 (theirs identical).
Max R diff 0.000 pp, max DD diff 0.00 pp — all far inside thresholds.

## Look-ahead audit (each with a test in tests/test_audit_k2.py)
1. Feature timing per shift: PASS. Lookup is kron.get((coin, T=idx+4h)) from the
   same-shift table (run_engine.py: `T_arr = idx + 4h`, `kron.get((cols[a], T_list[i]))`).
   No future bar is read; per-shift grids verified hour%4==shift.
2. Training-row cut: PASS. Fits use harness majors rows with t_exit < A-7d joined
   to shift-0 features (n counts match; truncation test asserts max t_exit < cut).
3. Shift/phase mapping: PASS (note below). The used path maps holding bar H to the
   year via standard anchors (searchsorted on ANCH5), identical to the blind
   replication; per-shift feature tables keyed by (sym, T) on that shift's grid.
4. Multiplier application point: PASS. `mult * 1.7 * tilt(i,a) * base_size(...)`
   inside sleeve_fill_size (holding-bar decision), budget 0.26*1.7 unchanged,
   sleeve_gross_cap 2.0, win_start=5.

Note (no score impact): tilt_rule.anchor_of() uses shift-aware year edges
[ANCH+sh, min(+365d, live1)) but is never called by run_engine.py (only ANCH5
and assign_mult are imported); the executed mapping is the standard-anchor one.

## Verdict: PASS-WITH-NOTES
Fits bit-identical, engine numbers identical to the digit, no look-ahead found;
the only note is the dead anchor_of() helper with a divergent convention.

## Nhận xét tiếng Việt (3 dòng)
K2 tái tạo khớp từng chữ số, không phát hiện look-ahead nên kết luận PASS-WITH-NOTES.
Ghi chú duy nhất là hàm anchor_of() chết khác quy ước nhưng không được dùng.
K2 năm sạch 4,80%/tháng, không qua cổng nên đồng ý REJECT của oc_kronoshidden.
