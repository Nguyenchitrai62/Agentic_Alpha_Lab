# audit_c2 — COMPARISON (Part B, opened ONLY after replication.json was saved)

Blind replication of oc_chronos C2 vs their frozen outputs.
Thresholds (pre-registered): R diff > 0.10 pp, DD diff > 0.5 pp,
fit params relative diff > 1e-6.

## Fits (per-anchor direction / q20 / q80)

| anchor | ours dir/q20/q80 | theirs dir/q20/q80 | match |
|---|---|---|---|
| 2021-09-24 | +1 / 1.110054237503456 / 2.8608138206510407 | +1 / same to all 16 digits | YES |
| 2022-09-24 | +1 / 1.1847269503398057 / 3.0250640748629083 | +1 / same | YES |
| 2023-09-24 | +1 / 1.0735691511209666 / 2.773698097596179 | +1 / same | YES |
| 2024-09-24 | +1 / 1.0644316852926394 / 2.65023108446202 | +1 / same | YES |
| 2025-09-24 | +1 / 1.0742922959916594 / 2.5976577907281015 | +1 / same | YES |
n_train / n_joined identical (2338/2017, 4147/3826, 6002/5681, 8345/8024,
10056/9735). Spearman rho agrees to their 4dp rounding
(0.0364/0.0760/0.1287/0.1187/0.1126). Method note (no value impact): theirs
uses np.quantile on the joined array (make_fits.py:53), ours pandas
Series.quantile (fit_c2.py) — both linear interpolation, identical outputs.

## Engine (4-phase reset %/mo, yearly DD)

| year | REF ours | REF theirs | C2 ours | C2 theirs (dev/last_year) |
|---|---|---|---|---|
| 2021 | 2.588 (10.86) | 2.588 (10.86) | 2.711 (11.52) | 2.711 (11.52) |
| 2022 | 3.282 (16.91) | 3.282 (16.91) | 3.460 (15.48) | 3.460 (15.48) |
| 2023 | 6.045 (15.81) | 6.045 (15.81) | 6.250 (15.07) | 6.250 (15.07) |
| 2024 | 10.677 (8.27) | 10.677 (8.27) | 10.721 (8.29) | 10.721 (8.29) |
| 2025-09-24..2026-09-23 | 4.648 (12.90) | 4.648 (12.90) | 4.754 (12.86) | 4.754 (12.86) |
dev4: REF 5.601 / C2 5.739 (theirs 5.601 / 5.739). 5y: REF 5.41 / C2 5.542.
Full-path DD: REF 16.82 / C2 15.42 (theirs identical).
Max R diff 0.000 pp, max DD diff 0.00 pp — all far inside thresholds.

## Multiplier vectors

2000 sampled (sym, shift, H) keys: our assign_mult (audit_c2/run_engine.py)
vs their tilt_rule.assign_mult with their fits.json — 2000/2000 agree.

## Look-ahead audit (each with a test in tests/test_audit_c2.py)
1. Feature timing: PASS. Context = log closes of the 512 bars closing <= T
   on that shift's grid (run_chronos_4shift.py:95 `logc[e-512:e]`); sigma
   from opens <= T only (loc. cit.:84-85). Independent recompute of 200
   random ch_q10 rows from bars truncated at T (check_truncation.py):
   200/200 match, max abs diff 4.2e-05 (float32 batching noise).
2. Training-row cut: PASS. Fits use harness majors rows with t_exit < A-7d
   joined to shift-0 features (fit_c2.py; n counts match; truncation test
   asserts max t_exit < cut; 2025 fit cut = 2025-09-17).
3. Shift/phase mapping: PASS (note below). Executed path maps holding bar H
   to the latest anchor <= H (theirs: searchsorted on ANCH5, run_engine.py:
   134-136; ours: anchor_for, identical); per-shift feature tables keyed
   by (sym, T) on that shift's grid.
4. Multiplier application point: PASS. `mult * 1.7 * tilt(i, a) *
   base_size(i, a, r, f)` inside sleeve_fill_size (holding-bar decision),
   budget 0.26*1.7 unchanged, sleeve_gross_cap 2.0, win_start=5 (both).

Note (no score impact): tilt_rule.anchor_of() (shift-aware year edges) is
defined and unit-tested but never called by run_engine.py or make_fits.py;
the executed mapping is the standard-anchor one audited above. Same class
of dead-helper note as audit_k2.

## Contamination (summary; detail in REPORT.md)
Chronos-Bolt-small (released 2024-11-26 on HF): model card states training
on ~100B time-series observations; corpus = public datasets + synthetic
(KernelSynth/TSMixup) per the Chronos paper (arXiv:2403.07815) and the
public autogluon/chronos_datasets list (67 subsets). That list contains NO
crypto or crypto-exchange price series; the only exchange-rate data is
`exchange_rate` (8 daily TradFi FX series) plus M4 finance (pre-2016
traditional). So 2021-2024 crypto 4h bars cannot be memorised; dev stays an
UPPER BOUND only in the weak sense (generic financial dynamics transfer).
The post-release year is clean.

## Verdict: PASS-WITH-NOTES
Fits bit-identical, engine numbers identical to the digit, multiplier
vectors 2000/2000 agree, no look-ahead found; the only note is the dead
anchor_of() helper with a divergent convention (unused).

## Nhận xét tiếng Việt (3 dòng)
C2 tái tạo khớp từng chữ số, 200 hàng đặc trưng tính lại đều khớp nên kết luận PASS-WITH-NOTES.
Ghi chú duy nhất là hàm anchor_of() chết khác quy ước nhưng không được dùng.
C2 năm sạch 4,75%/tháng, không qua cổng nên đồng ý REJECT của oc_chronos.
