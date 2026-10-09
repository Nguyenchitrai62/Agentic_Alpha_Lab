# oc_manualsplit REPORT: MANUAL split-TP bracket ladder (IDEAS_20261007c B8)

## 0. PRE-REGISTRATION (frozen in PLAN.md before any run; no other variants)

- M5_human: deployed reference (must reproduce oc_manualcap bit-exact or STOP).
- H1_split75_150: every taken dip rung split into two halves rn/2 + rn/2 at
  TP ratios (0.75, 1.5) x deployed per-rung TP multiplier m0.
- H2_split50_100: same with ratios (0.5, 1.0) x m0.
- Deployed m0 is NOT fixed 1.0 sigma: with agents ON it comes from the
  walk-forward R2 table (values 0.5/1.0/1.5, median 1.0), so the split keeps
  RATIOS relative to m0 (TP = limit x (1 + ratio x m0 x sg)). Stop unchanged
  (8.0sg touch, shared level). Budget check (0.26) once on the full rn before
  the split; no gross cap; night dip skip before any split; book path
  untouched. Half below 5.0 USDT (Bybit default) merges to one order with the
  deployed TP (counted). Selection H1 vs H2 ONLY on dev 2021-2024 with the
  robust criterion; last year 2025-09-24..2026-09-23 POST-HOC once for the
  chosen row + M5_human, never used to choose.

## 1. Baseline reproduction (exact, else the study would have stopped)

- M5_human rerun in this harness is BIT-EXACT vs
  oc_manualcap_runs.pkl (max abs d(eq,eq_min) = 0.000e+00 over 4 phases):
  R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 / book_win .6482,
  Rdev4 3.661 / Rlast 3.994. Matches the published 4-phase mix 3.73 %/month,
  DD ~17.8, win ~64.8 %.
- R2 TP table confirmed: values {0.5, 1.0, 1.5}, so the ratio rule applies
  (stated in PLAN.md and §2). Merges: 0 on every row (halves 12674 H1 /
  13170 H2, all halves >> 5 USDT as expected).

## 2. Method (dip-exit patch only; entries/stops/timeouts/fees unchanged)

- Harness = oc_manualcap copy: M5 pipe v367, win_start=15 / sleeve_start=16,
  night bar skipped (books wait/hold + sleeve_filter 0), agents ON with
  per-phase R2 tables, gate costs maker 0.0002 / taker 0.00055 / longs pay
  0.0001 per 8h. 4 phases x 3 rows sequential in one heavy_slot process
  (tag oc_manualsplit, min-free 2 GB); scoring = reset_metric per anchor +
  v388.mix full-path DD; book wins pooled via v213.trade_stats dev+_hidden;
  dip wins = rung exits with ret > 0 (each half counts one rung trade).
- Patch (make_split_simulate, audited pattern cf. oc_manualnight): the engine
  risk-budget check runs on the full rn; then per fill _m0 = deployed TP
  mult, halves at _m0 x ratios (merge to single at _m0 if half < 5 USDT);
  each half runs the unmodified touch-mode exit block (TP limit maker /
  touch-stop taker stop-first / timeout at next 4h open taker) with its own
  TP, same stop, same fill minute and end bar; PnL/path/fees accumulate per
  half (rn/2 x ret). M5_human uses the unpatched eu.simulate (identity).

## 3. Results (reset metric R %/mo / DD %; last year POST-HOC, not for choice)

| row | 21-22 R/DD | 22-23 R/DD | 23-24 R/DD | 24-25 R/DD | 25-26* R/DD | R5 | W | maxDD | fullDD | Rdev4 | Wdev4 | DDdev4 | Rlast | book win (n) | rung win (n) | all win | merged/halves |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M5_human | 0.847/16.54 | 1.585/17.94 | 4.413/17.36 | 7.948/8.24 | 3.994/11.69 | 3.728 | 0.847 | 17.94 | 17.79 | 3.661 | 0.847 | 17.94 | 3.994 | .6482 (3744) | .7013 (6417) | .6817 | 0/0 |
| H1_split75_150 | 0.606/15.70 | 0.750/18.50 | 4.800/18.01 | 7.862/8.04 | 3.601/13.83 | 3.489 | 0.606 | 18.50 | 19.80 | 3.461 | 0.606 | 18.50 | 3.601 | .6492 (3683) | .6976 (12678) | .6867 | 0/12674 |
| H2_split50_100 | 0.873/13.87 | 2.063/17.44 | 3.463/17.30 | 7.240/7.03 | 4.011/10.31 | 3.508 | 0.873 | 17.44 | 17.24 | 3.382 | 0.873 | 17.44 | 4.011 | .6497 (3822) | .7563 (13174) | .7323 | 0/13170 |

Yearly book/rung win rates (pooled over phases):
- M5 book: .6429/.6264/.6395/.6402/.6837; rung: .6322/.6903/.7679/.7365/.6701.
- H1 book: .6465/.6294/.6437/.6431/.6777; rung: .6276/.6832/.7717/.7255/.6659.
- H2 book: .6461/.6304/.6339/.6402/.6881; rung: .6967/.7556/.8095/.7859/.7274.
Deltas on dev years 2021-2024 (the only selection ground):
- H1 vs M5: Rdev4 -0.200, Wdev4 -0.241, DDdev4 +0.56, fullDD +2.01. Runner at
  1.5x m0 wins too rarely to pay for the banked half's smaller size.
- H2 vs M5: Rdev4 -0.279, Wdev4 +0.026, DDdev4 -0.50, fullDD -0.55. Faster
  bank lifts dip win +5.5pp (.7563 vs .7013) and all win +5.1pp, trims DD
  ~0.5pp, but return falls ~0.28pp dev4 (~0.22pp R5).
- H2 vs H1: Rdev4 -0.079, Wdev4 +0.267, DDdev4 -1.06, fullDD -2.56.

Selection (dev4 only): both H1/H2 satisfy DD <= 20 with no losing dev year;
neither reaches mean >= 5, so the pool is both; highest Wdev4 is H2 (0.873
vs 0.606). PICK = H2_split50_100.
MANUAL gate for H2: R5 3.508 < 5 (FAIL, gap 1.492pp), fullDD 17.24 < 20
(pass), book_win .6497 >= .55 (pass) - return shortfall only, same as M5.
No losing year anywhere (all rows, all years).

## 4. Caveats / post-hoc log

1. No post-hoc change to H1/H2 ratios, prices, windows, budgets, merge rule,
   or the dev4-only selection rule. PLAN.md is untouched since before the run.
2. All five years were simulated in one pass (oc_manualcap precedent); the
   last year (*) is POST-HOC context - seen years, never used to choose.
3. Deterministic engine (no RNG in path); M5_human bit-identity is the proof.
4. Dip halves double rung counts (each half one rung trade); book counts
   comparable (3744 vs 3683/3822); win_all shifts toward dip win by
   construction - reported transparently, book_win is the gate metric.
5. MANUAL book+dip only (no carry sleeve); costs are gate costs; DD is
   max(4h-close, 1m-marked) full-path like v421/v422. Needs no new data.

## 5. Leakage audit (ZERO LEAKAGE)

- Feature timing: 4h bar values known at its close; dip levels use bar-open
  O1/sigma4; R2 size/TP tables keyed by holding-bar time T (bar-open lookup
  only, never minute or fill data); no 1m data enters any decision.
- Label windows: no new labels; R2 agents fit per-bar open decisions only.
- Fit windows: no new fits/thresholds/quantiles; split ratios fixed in PLAN.md
  before any run; R2 tables are pre-fit walk-forward artifacts ending before
  each anchor + embargo (inherited from v321/v376).
- Fill timing: new orders never fill minutes 0..14 (win_start=15 books,
  sleeve_start=16 dips, stricter than the minute-5 user rule); limits fill
  only on 1m trade-through; stop-first on same-bar SL+TP touch; timeout at
  next 4h open.

## 6. One-line verdict

REJECT for adoption: the faster bank (H2) lifts dip/all win and trims DD
~0.5pp with zero merges, but return falls further from the floor (R5 3.508,
gap 1.492pp; Rdev4 3.382, gap 1.618pp) vs M5_human (R5 3.728, gap 1.272pp) -
the split does not close any part of the MANUAL return gap; close the
split-TP direction, MANUAL still needs entry edge, not exit splits.

H2 chia doi TP nhanh hon tang win dip/all va giam DD nhe nhung loi nhuan giam so voi M5 (R5 thieu ~1,49 diem %/thang).
H1 (runner 1,5x) te hon ca return lan DD/fullDD: loai.
Tu choi dua y tuong vao san xuat: MANUAL van thieu ~1,5 diem %/thang, can edge vao lenh.
