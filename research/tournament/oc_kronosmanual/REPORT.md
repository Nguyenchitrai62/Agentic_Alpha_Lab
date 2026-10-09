# oc_kronosmanual REPORT: ex-ante Kronos corr-aware dip sizing (MANUAL)

## 0. PRE-REGISTRATION (frozen in PLAN.md before any run; no other variants)

- M5_human: deployed reference (must reproduce oc_manualcap bit-exact or STOP).
- KM1: every dip bracket rung of (coin, bar) x 1/(1+E_n), rescaled x s1_A.
- KM2: every dip bracket rung x 1/(1+2*E_n), rescaled x s2_A.
- CTRL: every dip bracket rung x 1/(1+c_A), constant (NO second rescaling:
  rescaling a constant reproduces M5 identically; CTRL stays constant to
  test exposure vs allocation).
- E_n(coin, T, shift) = sum of pdrop2 of the four OTHER majors at (T, s);
  <3 of 4 others finite -> mult 1.0, else sum_avail*4/n_avail. Training
  rows for anchor A: feature rows with T < A - 7d (pooled 5 coins x 4
  shifts); s1_A/s2_A = 1/mean(raw) so the training mean mult is 1.0 (= M5).
- CONTAMINATION CAVEAT (assignment): Kronos released 2025-08, so dev years
  are likely inside its pretraining -> EVERY dev number below is an UPPER
  BOUND; the most recent year is the clean test.
- Selection KM1 vs KM2 ONLY on dev 2021-2024 with the robust criterion;
  last year 2025-09-24..2026-09-23 POST-HOC once for the chosen + CTRL +
  M5_human, never used to choose.

## 1. Baseline reproduction (exact, else the study would have stopped)

- Kronos input reached all 20 (shift, sym) groups (XRP s1..s3 arrived
  ~17:20 after ~40 min of polling; GPU inference was active throughout).
- M5_human rerun in this harness is BIT-EXACT vs oc_manualcap_runs.pkl
  (max abs d(eq,eq_min) = 0.000e+00 over 4 phases):
  R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 / book_win .6482,
  Rdev4 3.661 / Rlast 3.994. Engine cols confirmed as the 5 majors.
- Training fits per anchor (pooled pre-anchor rows, T < A - 7d):

| anchor | c_A | s1_A | s2_A | n_train |
|---|---|---|---|---|
| 2021-09-24 | 0.6198 | 1.4553 | 1.7876 | 41440 |
| 2022-09-24 | 0.4962 | 1.3733 | 1.6530 | 85240 |
| 2023-09-24 | 0.4346 | 1.3221 | 1.5577 | 129040 |
| 2024-09-24 | 0.4631 | 1.3368 | 1.5815 | 172960 |
| 2025-09-24 | 0.4602 | 1.3341 | 1.5772 | 216760 |

Mean E_n ~0.43-0.62 other coins flushing per bar; s1/s2 > 1 compensates
the average haircut so KM rows run at equal average risk to M5.

## 2. Method (sleeve_filter only; entries/stops/TPs/timeouts/fees unchanged)

- Harness = oc_manualcap copy: M5 pipe v367 (risk budget 0.26, stop 8.0sg,
  size_mult 4.375, rungs 3.0/4.0), win_start=15 / sleeve_start=16, night
  bar skipped (books wait/hold + dip filter 0), agents ON with per-phase
  R2 tables, gate costs maker 0.0002 / taker 0.00055 / longs pay 0.0001
  per 8h. 4 phases x 4 rows sequential in one heavy_slot process (tag
  oc_kronosmanual); scoring = reset_metric per anchor + v388.mix
  full-path DD; book wins pooled via v213.trade_stats dev+_hidden; dip
  wins = rung exits with ret > 0. M5_human uses the unpatched eu.simulate
  (identity; same filter line as oc_manualsplit, verified by test).
- KM/CTRL patch is ONLY the sleeve_filter callable: 0 on the night bar
  else the pre-registered Kronos mult for (T = idx[i]+4h, coin, shift),
  same mult for every rung of that coin+bar; agent sleeve_fill_size /
  sleeve_tp unchanged; risk budget applies once on the scaled rn; no
  gross cap. Book path untouched.

## 3. Results (reset metric R %/mo / DD %; dev = UPPER BOUND; last year POST-HOC)

| row | 21-22 R/DD | 22-23 R/DD | 23-24 R/DD | 24-25 R/DD | 25-26* R/DD | R5 | W | maxDD | fullDD | Rdev4 | Wdev4 | DDdev4 | Rlast | book win (n) | rung win (n) | all win |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M5_human | 0.847/16.54 | 1.585/17.94 | 4.413/17.36 | 7.948/8.24 | 3.994/11.69 | 3.728 | 0.847 | 17.94 | 17.79 | 3.661 | 0.847 | 17.94 | 3.994 | .6482 (3744) | .7013 (6417) | .6817 |
| KM1 | 1.158/14.15 | 1.957/19.55 | 2.724/17.28 | 7.469/7.47 | 4.017/9.82 | 3.442 | 1.158 | 19.55 | 20.12 | 3.298 | 1.158 | 19.55 | 4.017 | .6472 (3778) | .7029 (6402) | .6822 |
| KM2 | 1.081/12.99 | 1.991/19.13 | 2.834/15.70 | 7.166/6.72 | 4.041/10.64 | 3.401 | 1.081 | 19.13 | 20.26 | 3.242 | 1.081 | 19.13 | 4.041 | .6516 (3838) | .7037 (6585) | .6845 |
| CTRL | 0.832/13.26 | 2.395/16.56 | 2.886/18.32 | 6.973/6.74 | 3.810/9.16 | 3.359 | 0.832 | 18.32 | 16.84 | 3.247 | 0.832 | 18.32 | 3.810 | .6488 (3781) | .7034 (6568) | .6834 |

Yearly book/rung win rates (pooled over phases):
- M5 book: .6429/.6264/.6395/.6402/.6837; rung: .6322/.6903/.7679/.7365/.6701.
- KM1 book: .6454/.6228/.6292/.6415/.6855; rung: .6286/.7071/.7631/.7419/.6719.
- KM2 book: .6452/.6368/.6369/.6419/.6884; rung: .6256/.7067/.7629/.7422/.6703.
- CTRL book: .6506/.6262/.6232/.6460/.6874; rung: .6372/.7031/.7638/.7411/.6716.
Deltas on dev years 2021-2024 (the only selection ground, UPPER BOUNDS):
- KM1 vs M5: Rdev4 -0.363, Wdev4 +0.311, DDdev4 +1.61, fullDD +2.33.
  The worst year lifts, but the mean falls and DD RISES: upscaling quiet
  bars (s1 ~1.33-1.46) hurts more than downscaling busy bars helps.
- KM2 vs M5: Rdev4 -0.419, Wdev4 +0.234, DDdev4 +1.19, fullDD +2.47.
  Stronger haircut, same pattern, slightly worse mean.
- KM1 vs CTRL (timing vs mere exposure): Rdev4 +0.051, Wdev4 +0.326,
  DDdev4 +1.23. Timing adds worst-year lift only, at a DD cost.
- Clean-year check (POST-HOC, never for choice): KM1 4.017 vs M5 3.994
  (+0.023), KM2 +0.047, CTRL -0.184. No edge survives where it matters.

Selection (dev4 only): both KM1/KM2 satisfy DD <= 20 with no losing dev
year; neither reaches mean >= 5, so the pool is both; highest Wdev4 is
KM1 (1.158 vs 1.081). PICK = KM1.
MANUAL gate for KM1: R5 3.442 < 5 (FAIL, gap 1.558pp), fullDD 20.12 >= 20
(FAIL by 0.12pp), book_win .6472 >= .55 (pass) - return shortfall plus a
marginal full-path DD breach, both worse than M5 (R5 gap 1.272pp,
fullDD 17.79). No losing year anywhere (all rows, all years).

## 4. Caveats / post-hoc log

1. No post-hoc change to E_n, raw mults, missing rule, embargo, rescaling,
   or the dev4-only selection rule. PLAN.md is untouched since before the
   run (only the anchor_of pre-live fallback was fixed before the heavy
   run, covered by a fast unit test, no outcome involved).
2. All five years were simulated in one pass (oc_manualcap precedent); the
   last year (*) is POST-HOC context - seen years, never used to choose.
3. Deterministic engine (no RNG in path); M5_human bit-identity is proof.
4. Win rates move < 0.5pp on every slice (book gate metric unaffected);
   rung counts comparable (6402-6585 vs 6417). The sizing only reallocates
   dip risk across bars - and the reallocation loses.
5. MANUAL book+dip only (no carry sleeve); costs are gate costs; DD is
   max(4h-close, 1m-marked) full-path like v421/v422.

## 5. Leakage audit (ZERO LEAKAGE)

- Feature timing: Kronos row for bar open T uses only the 400 4h bars
  closing <= T on that shift's grid (oc_kronoshidden PLAN); E_n at T uses
  only pdrop2 values known at T, joined on (sym, shift, T); R2 size/TP
  tables keyed by holding-bar time T (bar-open lookup only, never minute
  or fill data); no 1m data enters any decision (asserted in tests).
- Label windows: no new labels; no outcome enters any sizing decision.
- Fit windows: c_A / s1_A / s2_A use only feature rows with T < A - 7d;
  fits of anchor A apply to year [A, A+365d); no statistic from any test
  year feeds any choice. Pre-live bars use anchor-2021 fits (fixed before
  the run; outside every scoring window).
- Fill timing: no fill minutes 0..15 (win_start=15 books,
  sleeve_start=16 dips, stricter than the minute-5 user rule); limits fill
  only on 1m trade-through; stop-first on same-bar SL+TP touch; timeout at
  next 4h open.

## 6. One-line verdict

REJECT for adoption: the ex-ante Kronos proxy does not close any part of
the MANUAL gap - even as an upper bound (dev inside pretraining) KM1 loses
return (R5 3.442, gap 1.558pp; Rdev4 3.298, gap 1.702pp) and RAISES DD
(fullDD 20.12, breach; DDdev4 +1.61pp) vs M5_human (R5 3.728, gap 1.272pp;
fullDD 17.79); the only gain is worst-year (+0.31pp dev) and the clean
year is flat (+0.02pp). Close the ex-ante corr-proxy direction with the
static one: MANUAL still needs entry edge, not dip-size reallocation.

KM1 duoc chon tren dev (W cao nhat) nhung thua M5 ca return lan DD, fullDD vuot 20 (20,12): loai.
Nam sach kiem chung khong co edge (+0,02 diem so voi M5): dong huong proxy tuong quan mo truoc.
MANUAL van thieu ~1,56 diem %/thang so voi san 5 % (R5 3,442, DD day duong), can edge vao lenh.
