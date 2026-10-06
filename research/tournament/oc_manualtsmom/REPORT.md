# oc_manualtsmom REPORT: M5_human MANUAL + oc_tsmom 30d-TSMOM sleeve

Method (frozen in PLAN.md): base = honest MANUAL M5_human (15-min reaction,
night bar skipped, agents ON) from `oc_manualcap_runs.pkl`, scored with the
official reset convention (`reset_metric.year_reset` mirrors: per-shift
F(a0)=1.0, mean of 4 segments; DD from combined eq_min vs peak of eq, hourly
grid G0=2021-09-24 04:00 .. g1=2026-09-23 12:00). Sleeve = `oc_tsmom` exact
reuse (BTC+ETH 30d TSMOM, 10% vol target, cap 1.0x, next-day-open, taker
0.00055, longs 0.0003/d) with `oc_tsmom_official` hourly worst-case marking
(long->hour low, short->hour high; day-boundary eq == daily sleeve).
Weights w in {0.25, 0.50, 1.00} x (a) overlay (base + w*sleeve on top of the
full MANUAL account) and (b) split ((1-w) MANUAL / w sleeve). Win metric =
(book_wb + sleeve_w)/(book_nb + sleeve_n); sleeve trade = holding day with a
non-zero position, win iff net r_s > 0. One process, hourly only, RAM < 1 GB.
All five years are research data; any finding needs prospective validation.
Repro: `research/tournament/oc_manualtsmom/{PLAN.md,run_manualtsmom.py,
results.json}`; test `tests/test_oc_manualtsmom.py` (7 passed).

## Base proof / cross-checks (must hold — all PASS)

- Recomputed M5_human yearly R/DD EQUAL `oc_manualcap/results.json`
  (0.847/1.585/4.413/7.948/3.994 %/mo; DD 16.54/17.94/17.36/8.24/11.69).
- Book pool 3744 trades / win 0.6482 reproduces oc_manualcap exactly.
- Sleeve daily r_s equals oc_tsmom r_sleeve to 5e-09; day-boundary gap 4e-16;
  eq_min never above eq; monthly/total residual < 1e-6.
- Sleeve pool: 1824 holding-day trades, win 0.4918 (trend: positive return on
  <50% day-win — a few big trend days pay for many small losses).

## Main table (per row: 5y %/mo, worst year, max yearly DD | full-path DD, pool win)

| row | 5y R | worst | maxDD | fullDD | win | excess +/5 | LOYO | PROMISING | BASE_HIT |
|---|---|---|---|---|---|---|---|---|---|
| base M5_human | 3.73 | 0.85 | 17.94 | 17.79 | .648 | — | — | — | NO (return) |
| overlay 0.25 | 3.90 | 1.16 | 19.33 | 18.74 | .597 | 5/5 | 5/5 | YES | NO (3.90 < 5) |
| overlay 0.50 | 4.06 | 1.45 | 20.71 | 19.65 | .597 | 5/5 | 5/5 | YES | NO (ret + DD) |
| overlay 1.00 | 4.38 | 1.69 | 24.87 | 22.29 | .597 | 5/5 | 5/5 | YES | NO (ret + DD) |
| split 0.25 | 3.16 | 0.96 | 15.89 | 15.69 | .597 | 1/5 | 5/5 | NO | NO (return) |
| split 0.50 | 2.53 | 0.88 | 13.56 | 13.39 | .597 | 1/5 | 5/5 | NO | NO (return) |
| split 1.00 (sleeve) | 0.99 | 0.12 | 19.70 | 23.75 | .597 | 1/5 | 5/5 | NO | NO (return + DD) |

(BASE_HIT = R5 >= 5.0 AND maxDD < 20 AND fullDD < 20 AND win >= .55.)

Per-year monthly (combined vs base; overlay 0.25): 21-22 1.16 vs 0.85 (+0.31);
22-23 1.61 vs 1.59 (+0.03); 23-24 4.58 vs 4.41 (+0.16); 24-25 8.14 vs 7.95
(+0.20); 25-26 4.14 vs 3.99 (+0.15) — excess positive 5/5 but DD worse 5/5
(+0.01/+1.39/+0.43/+0.07/+1.31pp). Year win (book+sleeve) overlay rows:
.581/.565/.592/.605/.632 (book .643/.626/.640/.640/.684, sleeve day-win
.48/.46/.48/.53/.51). Split rows dilute the MANUAL edge (only 2021 excess
positive) while cutting DD (split 0.50 maxDD 13.6) — return falls to 2.5.

## Caveats / post-hoc log

1. Win is w-independent by construction (same book + sleeve trade counts in
   every row); the sleeve day-win 0.49 drags the book 0.65 down to 0.60 —
   still above the 0.55 floor, so return (not win or DD at 0.25x) is the
   binding miss.
2. DDs use the official hourly+eq_min convention (conservative); no 1m
   marking, so gate 1m-marked DD is unevaluated and live DD would read worse.
3. No post-hoc changes (none): fixed rule, one run; 6 rows are
   assignment-fixed, not tuned.

## One-line verdict

NO row reaches the MANUAL base: the 0.25x overlay adds return in 5/5 years
(+0.17pp to 3.90 %/mo) but also DD in 5/5 (19.3) and higher weights breach
DD<20 while still short of 5 %/mo — a correlated add-on, not the missing edge.
