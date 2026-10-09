# oc_downshare — REPORT (2026-10-08; PLAN frozen before any outcome)

Downside-share dip tilt (IDEAS5 #3, rank 3): same K2/C2 quintile tilt form
(x1.25/x0.75 outer quintiles) but on downside-RV share (composition, not level).
D1 = trailing-6d downside share; D2 = HAR-RS daily/weekly downside blend 0.6/0.4
(frozen). Existing 4h closes only (no new data). Disclosed as 1 of ~6 vol-tilt
family members (multiplicity).

STATUS: DONE. Features 268,325 rows (D1 cov 0.9972, D2 0.9977); fits 10/10;
replica+placebo gate complete (base sum5y 7.718304 exact, n = 22312); D1 PASSED
the gate -> full 4-phase engine dev + scored-once last complete (REF reproduction
to the digit, determinism OK); D2 FAILED the gate -> no engine (negative leg, valid).

## Fits (harness rows only, shift-0, 7d embargo)

| anchor | D1 dir/rho | D2 dir/rho |
|---|---|---|
| 2021 | +1 / 0.0127 | +1 / 0.0428 |
| 2022 | -1 / -0.0200 | +1 / 0.0595 |
| 2023 | -1 / -0.0051 | +1 / 0.0679 |
| 2024 | +1 / 0.0011 | +1 / 0.0475 |
| 2025 | +1 / 0.0026 | +1 / 0.0548 |

D2 is sign-stable +1 (all five anchors, rho 0.04-0.07 — weaker than RV6/GARCH
0.08-0.15 but same direction). D1 flips sign (2022/2023 -1, else +1, |rho| <= 0.02):
the 6d composition carries no stable harness association — a warning flag before
any outcome. Coverage: majors shift-0 rows 10,100/10,100 both variants.

## Replica + placebo gate (reused D0+B1 ledger)

| year x variant | n | base | tilt | norm | timing pct | block pct |
|---|---|---|---|---|---|---|
| 2021 D1 / D2 | 4171 | 0.911273 | 1.080628 / 1.109281 | 0.9678 / 1.0278 | 99.7 / 100.0 | 99.6 / 100.0 |
| 2022 D1 / D2 | 4059 | 0.832599 | 1.211615 / 0.546969 | 1.2138 / 0.5484 | 100.0 / 0.1 | 100.0 / 0.1 |
| 2023 D1 / D2 | 5352 | 2.099814 | 2.403130 / 1.800842 | 2.3180 / 1.8291 | 100.0 / 0.1 | 100.0 / 0.1 |
| 2024 D1 / D2 | 3958 | 3.197390 | 2.985523 / 3.126334 | 3.1150 / 3.1490 | 0.1 / 90.1 | 0.1 / 88.2 |
| 2025 clean D1 / D2 | 4772 | 0.677229 | 0.690691 / 0.709420 | 0.6514 / 0.6716 | 67.0 / 92.7 | 64.0 / 90.5 |

- dSum5y (4-phase-mean w*y): D1 +0.653 (>= +0.273 PASS); D2 -0.425 (FAIL).
  Sum-half: D1 4/5 (fails only 2024: tilt 2.9855 < base 3.1974) PASS; D2 2/5 FAIL.
  Gate (both legs): D1 PASS -> engine; D2 FAIL -> no engine.
- D1 timing is 99.7-100.0 in 2021-2023, 0.1 in 2024 (tilt significantly WORSE than
  random there), 67.0 clean (insignificant). D2 timing is 100.0 only in 2021 and
  0.1 in 2022-2023 (significantly worse than random) — the HAR-RS blend points the
  wrong way on the replica outside 2021.

## Engine (REF + gate-passing D1 only; D2 not run per the gate rule)

REF reproduces v421 G2 to the digit (dev [2.588/10.86, 3.282/16.91, 6.045/15.81,
10.677/8.27], Y4 4.648/12.90, full-path DD 16.82; determinism dev == last dev
segments). Per-year 4-phase reset %/mo + DD:

| row | y0 R/DD | y1 R/DD | y2 R/DD | y3 R/DD | dev4 mean | WORST | DDmax |
|---|---|---|---|---|---|---|---|
| REF | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 5.601 | 2.588 | 16.91 |
| D1 | 2.921/12.59 | 3.604/16.09 | 6.541/15.74 | 10.191/8.19 | 5.776 | 2.921 | 16.09 |

Robust pick on dev4 ONLY: D1 (both DD <= 20, no losing year, both mean >= 5;
highest WORST: D1 2.921 > REF 2.588). D1 lifts dev4 mean +0.175 AND the worst year
+0.333 with lower DDmax (16.09 vs 16.91, fullDDdev 15.98 vs 16.82).

Most-recent year 2025-09-24..2026-09-23, scored ONCE for the dev4 pick + reference:

| row | %/mo | DD | full-path DD | book win | rung win | all win | sized mult |
|---|---|---|---|---|---|---|---|
| REF | 4.648 | 12.90 | 16.82 | 0.5365 | 0.6478 | 0.6267 | 1.0000 |
| D1 | 4.591 (-0.057) | 13.38 | 15.98 | 0.5375 | 0.6487 | 0.6276 | 1.0626 |

5y geo mean: REF 5.410 / D1 5.538; no losing year anywhere; full-path DD <= 20.
The dev4 robust pick does NOT transfer: D1 loses -0.057 on the clean year and stays
below the 5.0 gate (4.591 < 5.0), same dev-mean-vs-robustness lesson as v189-v197 and
oc_voltilt (whose dev-mean edge also came without robustness). Win rates are flat
(D1 all-win 0.6276 vs REF 0.6267 clean; dev all-win within +-0.004 every year).

## Leakage checklist

- Feature timing: D1 uses 36 closes <= T, D2 30 closes <= T (weekly leg binds);
  truncation-tested in tests/test_oc_downshare.py (dropping later bars cannot change
  kept-prefix shares); exact (sym, shift, T) join, tz-aware UTC; ledger join missing
  0/22,312 (parquet cov 0.997 — the 0.3 % burn-in never fills).
- Label windows: harness y_dep at the deployed TP; no test labels in any fit.
- Fit windows: shift-0 only + 7d embargo (t_exit < A - 7d), anchor-y fit for year y;
  windows (36/6/30) and weights (0.6/0.4) frozen ex-ante, never scanned; D1 sign flips
  are the frozen Spearman outcome, not a choice.
- Fill timing: replica live 16..238 strict trade-through + stop-first inherited;
  engine win_start=5 + 1m trade-through + stop-first; perms reassign mults within-year
  only (seeds 20261007+y / 20261008+y).
- Coverage: 4h closes cover every anchor year — no skipped year, nothing imputed.
- DISCLOSED (pre-registered): the k2placebo ledger carries no exit-date/daily path, so
  the replica DD-half cannot be scored at the replica stage; the binding DD check is the
  4-phase engine above (yearly DD + full-path DD <= 20 both rows).
- Gate costs: inside replica outcomes and the engine (maker 0.0002 / taker 0.00055 /
  longs pay 0.0001 per 8h, shorts 0).

## What failed and why

D2 failed outright at the screen (dSum5y -0.425, sum-half 2/5, timing 0.1 in 2022-2023):
the HAR-RS 0.6/0.4 daily/weekly downside blend has no replica edge and points the wrong
way outside 2021 despite sign-stable harness fits. D1 passed the screen (+0.653, 4/5)
and even won dev4 on robustness (+0.333 worst-year, -0.8 pp DDmax), yet lost the clean
year (-0.057, timing 67.0 insignificant) and missed the 5.0 gate there (4.591) — the
composition axis adds dev4 robustness but no transferable return, exactly the family
pattern (vol tilts: dev-mean +0.02..+0.04, worst-year dent, clean year < 5 %).

## Vietnamese verdict

D1 qua cửa replica (+0,653, 4/5) và thắng dev4 về worst-year (+0,333, DDmax 16,09),
nhưng THUA năm sạch -0,057 (4,591 so với 4,648, timing 67%) nên không qua cổng 5%;
D2 rớt ngay từ screen (-0,425, timing 0,1 ở 2022-2023).
Kết luận: REJECT cả hai biến thể downside-share ở dạng đăng ký trước; không chọn D1
dù là dev4 robust pick, không cần bằng chứng prospective.
