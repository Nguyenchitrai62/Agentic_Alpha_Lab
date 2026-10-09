# audit_d1 — COMPARISON (Part B, opened ONLY after replication.json was saved)

Blind replication of oc_downshare D1 vs their frozen outputs.
Thresholds (pre-registered): R diff > 0.10 pp, DD diff > 0.5 pp,
fit params relative diff > 1e-6, feature max abs diff > 1e-9.
replication.json sha256 da04fe011b6fc9fe2dc12f9a0bdc3254da2499c6f77d8d37cf74bf811f9106fd
(saved BEFORE opening any oc_downshare output).

## Features (risk_D1, trailing-6d downside-RV share)

Our `downshare_D1_4shift.parquet` (rebuilt from
oc_kronoshidden/bars_4h_4shift.parquet) vs their
`downshare_features_4shift.parquet` risk_D1, inner-joined on (sym, shift, T):
rows 268325, max abs diff 5.27e-12, mean 1.07e-13, 0 rows over 1e-9;
NaN positions identical (740/740 burn-in E<37 both sides).
Method note (no value impact): theirs loops windows with direct
`np.sum(w*w)` per bar (build_downshare.py:42-47), ours uses prefix cumsums
(build_d1.py); both float64, summation-order noise only (~5e-12).

## Fits (per-anchor direction / q20 / q80, D1 only)

| anchor | ours dir/q20/q80 | theirs dir/q20/q80 | match |
|---|---|---|---|
| 2021-09-24 | +1 / 0.2516994146945099 / 0.6849373922456844 | +1 / 0.2516994146945108 / 0.6849373922456837 | YES |
| 2022-09-24 | -1 / 0.32188067723682284 / 0.7600235422668715 | -1 / 0.32188067723682434 / 0.7600235422669483 | YES |
| 2023-09-24 | -1 / 0.315985274921492 / 0.7666629928944176 | -1 / 0.31598527492147055 / 0.7666629928943725 | YES |
| 2024-09-24 | +1 / 0.2961339599860018 / 0.752779763163313 | +1 / 0.2961339599860011 / 0.7527797631632824 | YES |
| 2025-09-24 | +1 / 0.29028932792670686 / 0.742014838363016 | +1 / 0.2902893279268819 / 0.7420148383630151 | YES |
n_train / n_joined identical (2338/2338, 4147/4147, 6002/6002, 8345/8345,
10056/10056). Spearman rho agrees to their 4dp rounding
(0.0127/-0.0200/-0.0051/0.0011/0.0026). Method note (no value impact): theirs
uses np.quantile on the joined array (make_fits.py:57), ours pandas
Series.quantile (fit_d1.py / run_engine.py) — both linear interpolation,
identical outputs (max rel diff 6.0e-13).

## Engine (4-phase reset %/mo, yearly DD)

| year | REF ours | REF theirs | D1 ours | D1 theirs (dev/last_year) |
|---|---|---|---|---|
| 2021 | 2.588 (10.86) | 2.588 (10.86) | 2.921 (12.59) | 2.921 (12.59) |
| 2022 | 3.282 (16.91) | 3.282 (16.91) | 3.604 (16.09) | 3.604 (16.09) |
| 2023 | 6.045 (15.81) | 6.045 (15.81) | 6.541 (15.74) | 6.541 (15.74) |
| 2024 | 10.677 (8.27) | 10.677 (8.27) | 10.191 (8.19) | 10.191 (8.19) |
| 2025-09-24..2026-09-23 | 4.648 (12.90) | 4.648 (12.90) | 4.591 (13.38) | 4.591 (13.38) |
dev4: REF 5.601 / D1 5.776 (theirs 5.601 / 5.776). 5y: REF 5.41 / D1 5.538.
Full-path DD: REF 16.82 / D1 15.98 (theirs identical).
Max R diff 0.000 pp, max DD diff 0.00 pp — all far inside thresholds.

## Multiplier vectors

2000 sampled (sym, shift, T) keys: our assign_mult (audit_d1/run_engine.py)
vs their tilt_rule.assign_mult with their fits.json D1 — 2000/2000 agree.
Same-input determinism: re-run assign on the 2000 keys twice -> identical.

## Look-ahead audit (each with a test in tests/test_audit_d1.py)
1. Feature timing: PASS. D1 share at bar open T uses ONLY the 36 returns
   r[E-36..E-1] of bars closing <= T on that shift's grid
   (oc_downshare/build_downshare.py:42-47 `w = r[e-36:e]`, `e >= 37`;
   ours build_d1.py `E >= 37`, window `[E-36, E-1]`). Independent recompute
   of 200 random risk_D1 rows from bars truncated at T (check_truncation.py):
   200/200 match, max abs diff 2.5e-12 (tmp/truncation_check.json).
2. Training-row cut: PASS. Fits use harness majors rows with t_exit < A-7d
   joined to shift-0 features (fit_d1.py; n counts match; truncation test
   asserts max t_exit < cut; 2025 fit cut = 2025-09-17).
3. Shift/phase mapping: PASS (note below). Executed path maps holding bar H
   to the latest anchor <= H (theirs: searchsorted on ANCH5, run_engine.py:
   124-126; ours: anchor_for, identical); per-shift feature tables keyed
   by (sym, T) on that shift's grid.
4. Multiplier application point: PASS. `mult * 1.7 * tilt(i, a) *
   base_size(i, a, r, f)` inside sleeve_fill_size (holding-bar decision),
   budget 0.26*1.7 unchanged, sleeve_gross_cap 2.0, win_start=5 (both).

Note (no score impact): tilt_rule.anchor_of() (shift-aware year edges) is
defined and unit-tested but never called by run_engine.py or make_fits.py;
the executed mapping is the standard-anchor one audited above. Same class
of dead-helper note as audit_c2.

## Verdict: PASS-WITH-NOTES

Fits agree to ~1e-13, features to 5.3e-12, engine numbers identical to the
digit, multiplier vectors 2000/2000 agree, no look-ahead found; the only
note is the dead anchor_of() helper (unused, same as audit_c2).

## Nhận xét tiếng Việt (3 dòng)
D1 tái tạo khớp từng chữ số, 200 hàng đặc trưng tính lại đều khớp nên kết luận PASS-WITH-NOTES.
Ghi chú duy nhất là hàm anchor_of() chết không được dùng, giống audit_c2.
D1 năm sạch 4,59%/tháng, không qua cổng nên đồng ý REJECT của oc_downshare.
