# oc_idea5_manualrest REPORT: MANUAL 4h-rest brackets (IDEAS_20261007 §5)

## 0. PRE-REGISTRATION (frozen before any run, 2026-10-07; no other variants)

Idea: MANUAL 4h-rest brackets. Keeps 4h DECISIONS; rests the human book bracket
to the next 4h close (GTC 4h) instead of 60-min expiry. Not a repeat of
oc_cadence (8h/12h BOT decisions) or v335 daily MANUAL. Data: no new data;
existing 1m + M5_human schedule. Harness: MANUAL 4-phase with human schedule
(oc_manualcap copy: M5 pipe v367, 15-min reaction win_start=15, dip from
sleeve_start=16, night bar skipped, agents ON, gate costs maker 0.0002 /
taker 0.00055 / longs pay 0.0001 per 8h).

- H1_rest4h: rest-to-next-close at base size. Book ENTRY limit (pullback
  0.75 sigma_4h off the issuing bar minute-0 open, min 10 bps) fills minutes
  15..239 of its issuing bar only (single-bar validity, n_valid=1 for entries;
  unfilled expires at bar end; next decision re-issues at the fresh price).
  Signal-flip cancel unchanged. Dip sleeve unchanged.
- H2_rest4h_x2dip: H1 with dip bracket size x2.0 (size_mult 4.375 -> 8.75;
  sleeve_risk_budget stays 0.26; no chasing/re-peg). Human-load compensation,
  cf. v340 RA2 (size_mult-only move).
- B0_60min (idea-specified comparator, NOT a selectable candidate): M5_human
  with book ENTRY orders expiring 60 min after placement (fill minutes 15..74;
  unfilled -> order_expire; next decision re-issues). Tests the idea's stated
  mechanism (recovered near-miss fills in minutes 75..239).
- References (not candidates): M5_human deployed (must reproduce
  oc_manualcap R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 bit-exact or the
  study STOPS); G2 (v421 R2B1D17BFG2 5.41 / 2.588 / 16.91 / full 16.82,
  reproduced via reset_metric or STOP); G2+carry f=0.25 (oc_carrycompound
  5.634 / 2.778 / 16.75 / full 16.66, confirmed from the frozen artifact).

Selection (AGENTS.md): H1 vs H2 ONLY, on dev years 2021-2024 (robust
criterion: DD <= 20 and no losing dev year; prefer dev4 mean >= 5, then the
highest dev4 WORST-year monthly; ties -> higher mean). Most-recent year
2025-09-24..2026-09-23 scored once, labelled POST-HOC (all years were seen
when the rule was frozen), never used to choose. Metric: reset_metric
year_reset per anchor + v388.mix full-path DD (v421/v422 convention).
Leak audit: rest price uses only the issuing bar minute-0 open (no re-peg);
minute-15 fill ban kept (stricter than the minute-5 user rule); H2 sizing
scored separately.

Caveat pre-registered: the deployed 4-phase trade-mode engine has NO 60-min
book expiry (entries rest n_valid=3 bars ~12h with flip-cancel); "60-min
expiry" describes the live-bot window (docs/BOT_EXECUTION.md) / continuous
engine. B0 implements the idea's stated counterfactual; M5_human is the
deployment reference. Judged in the 4-phase engine, never a vector screen.

## 1. Baseline reproduction (all exact, else the study would have stopped)

- G2 (v421 R2B1D17BFG2) recomputed through this study's own metric path
  (reset_metric.year_reset + v388.mix): 5.41 / W 2.588 / DD 16.91 /
  full 16.82 — to the digit.
- G2+carry f=0.25 confirmed from frozen oc_carrycompound/results.json:
  5.634 / 2.778 / 16.75 / full 16.66 (+0.224).
- M5_human rerun in this study's harness is BIT-EXACT vs
  oc_manualcap_runs.pkl (max abs d(eq) = 0.000e+00 over 4 phases x 2 paths):
  R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 / book_win .6482.
  (One harness bug was caught by this gate: a first run without the night
  dip-skip sleeve_filter drifted; fixed, cache wiped, rerun — see §4.1.)

## 2. Method (entry-order patches only; SL/TP/scale orders untouched)

- B0: flat-branch entry fill window cut to La[15:75] for orders issued this
  bar; unfilled -> order_expire at minute 75 (same-bar expiry, no cross-bar
  resting). Price rule, flip-cancel, win_start=15 unchanged.
- H1/H2: entry T["exp"] = i+1 (single-bar validity; unfilled expires at bar
  end; next bar re-issues at the fresh O0-based pullback price). In-position
  scale orders keep n_valid=3. H2 adds size_mult 8.75 (budget 0.26 binds).
- 4 phases x 4 rows sequential in one heavy_slot process; scoring =
  reset_metric per anchor + v388.mix full-path DD from 2021-09-24; book/rung
  wins pooled over phases (v213.trade_stats dev+_hidden). Gate costs are the
  engine defaults (maker 0.0002 / taker 0.00055 / long funding 0.0001 per 8h).

## 3. Results (reset metric R %/mo / DD %; last year POST-HOC, not for choice)

| row | 21-22 | 22-23 | 23-24 | 24-25 | 25-26* | R5 | W | maxDD | fullDD | Rdev4 | Wdev4 | DDdev4 | book_win | fills/expires |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M5_human | 0.847/16.54 | 1.585/17.94 | 4.413/17.36 | 7.948/8.24 | 3.994/11.69 | 3.728 | 0.847 | 17.94 | 17.79 | 3.661 | 0.847 | 17.94 | .6482 | 3801/3698 |
| B0_60min | 0.504/15.67 | 0.888/18.08 | 4.159/17.44 | 7.820/9.32 | 3.586/12.39 | 3.358 | 0.504 | 18.08 | 18.01 | 3.301 | 0.504 | 18.08 | .6427 | 3022/24107 |
| H1_rest4h | 0.540/15.98 | 1.482/17.34 | 4.488/17.36 | 8.013/8.93 | 4.182/11.22 | 3.708 | 0.540 | 17.36 | 17.14 | 3.590 | 0.540 | 17.36 | .6520 | 3854/9452 |
| H2_x2dip | 0.046/20.69 | 0.561/21.32 | 4.593/19.91 | 8.731/10.00 | 4.322/17.05 | 3.603 | 0.046 | 21.32 | 25.21 | 3.424 | 0.046 | 21.32 | .6484 | 3455/8594 |

Deltas on dev years 2021-2024 (the only selection ground):
- H1 vs B0 (the idea's mechanism): Rdev4 +0.289, Wdev4 +0.036,
  DDdev4 -0.72; +617 book fills over dev4 (2956 vs 2339) at 24107-9452
  fewer expiries. Resting to the close recovers the near-miss fills exactly
  as hypothesised (+0.1-0.3pp/mo, DD flat-to-better).
- H1 vs M5_human (the deployment question): Rdev4 -0.071, R5 -0.020,
  Wdev4 -0.307 (2021: 0.540 vs 0.847), DDdev4 -0.58, fullDD -0.65.
  The deployed 3-bar resting earns back what single-bar GTC gives up late;
  net a wash on return, small DD gift.
- H2 vs H1: Rdev4 -0.166, Wdev4 -0.494, DDdev4 +3.96 (21.32 > 20 gate),
  fullDD 25.21. Dip x2 at a fixed 0.26 budget takes FEWER rungs
  (4969 vs 6422, budget binds) and breaks the DD gate. Ineligible.

Selection: H2 fails DD<=20 on dev4 -> excluded. PICK = H1_rest4h
(higher Wdev4 too). MANUAL gate for H1: R5 3.708 < 5 (FAIL), fullDD 17.14
< 20 (pass), book_win .652 >= .55 (pass) — return shortfall only, same as
the M5_human reference. No losing year anywhere (all rows, all years).

## 4. Caveats / post-hoc log

1. No post-hoc change to H1/H2/B0 definitions, prices, windows, budgets, or
   the dev4-only selection rule. §0 above is untouched since before the run.
2. All five years were simulated in one pass (oc_manualcap precedent); the
   last year (*) is POST-HOC context — seen years, never used to choose.
   B0 is a synthetic counterfactual (the deployed engine has no 60-min
   expiry); H1-vs-M5_human is the deployment comparison.
3. A per-fill "late fill" (minute>=75) counter was collected but DROPPED
   from results.json: its minute arithmetic used 4h-floor timestamps, which
   wrap on shifted phases (s=1..3) — biased, non-monotonic. Fills/expires
   kind counts (no timing) are exact and carry the fill-rate evidence.
4. Deterministic engine (no RNG in path); M5_human bit-identity is the proof.
   4.1 First heavy run lacked the night dip-skip sleeve_filter on all rows
   (caught by the bit-identity gate: phase nets drifted vs oc_manualcap);
   fixed, cache wiped, full rerun. No numbers from the bad run are reported
   (its log showed the same qualitative ordering, not used).
5. MANUAL book+dip only (no carry sleeve); costs are gate costs; DD is
   max(4h-close, 1m-marked) full-path like v421/v422. Needs no new data.

## 5. One-line verdict

REJECT for adoption: the mechanism is real (H1 beats a 60-min expiry by
+0.29pp/mo dev4 with better DD) but the deployed MANUAL already rests book
entries ~12h, so single-bar GTC (H1) gains nothing vs M5_human (-0.07pp dev4,
-0.31pp worst year, -0.6pp DD), and dip x2 (H2) breaks the DD gate (21.3 dev
/ 25.2 full-path) — close the 4h-rest direction; MANUAL still needs +1.3pp/mo
of entry edge, not order-validity tweaks.

H1 giu lenh toi dong 4h thang B0 han 60 phut (+0,29 diem %/thang, DD giam), nhung thua M5_human dang chay (nghi 3-bar, -0,07 diem, nam te nhat kem hon).
H2 nhan doi dip vo DD (21,3 dev / 25,2 full-path, vuot nguong 20) ma loi nhuan giam: loai.
Tu choi dua y tuong vao san xuat: MANUAL con thieu ~1,3 diem %/thang, huong nghi-do-dai-lenh da can, can edge vao lenh chu khong phai chinh sua han lenh.
