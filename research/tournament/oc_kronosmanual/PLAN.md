# oc_kronosmanual PLAN (pre-registered, frozen before any run, 2026-10-07)

Ex-ante (bar-open) substitute for corr-aware dip sizing in the MANUAL
product, from Kronos drop forecasts (assignment
docs/opencode/OPENCODE_W_oc_kronosmanual.md + common header
docs/opencode/OPENCODE_W_COMMON_20261007.md + AGENTS.md).

## Reference (must reproduce exactly or STOP)

M5_human = deployed MANUAL M5 (v367) on the human schedule, exactly as
research/diagnostics/manual_human/manual_human.py runs it and as scored in
research/diagnostics/oc_manualcap (reset metric + v388.mix full-path DD),
copied as oc_manualsplit did (compute_manualsplit.py pattern):
- pipe v367 via pof.pipe_setup (sleeve_risk_budget 0.26, m_sleeve_sl 8.0,
  size_mult 4.375, rungs (3.0, 4.0), book_mult 0.75, tighten on
  flat-signal losers, M3_R2_RUNG mapped agents ON with per-phase
  v376/tables_hidden R2 tables).
- human schedule on EVERY row: 15-min reaction (book orders from minute 15
  via win_start=15, dip limits from minute 16 via sleeve_start=16) + night
  bar skipped: on the holding bar starting at (20+s) UTC no new book order
  (flat -> wait, in position -> hold) and no new dip limit
  (sleeve_filter 0); resting orders, SL, TP stay on the exchange.
- gate costs maker 0.0002 / taker 0.00055, longs pay 0.0001 per 8h
  settlement, shorts nothing; limit fills only on 1m trade-through, no fill
  minutes 0..15 (stricter than the minute-5 user rule); stop-first if
  SL+TP touch the same 1m bar; dip exits: TP limit (maker) / touch stop
  8.0sg market (taker) / timeout at next 4h open (taker); book SL 5.0 /
  TP 10.0 sigma_d per v362/v367.
- 4 phases s=0..3, live window [2021-09-24+sh, 2026-09-23+sh), anchors
  2021-09-24..2025-09-24 (+sh per phase), each year [a0, min(a0+365d,
  live1)).
- scoring: reset_metric.year_reset per anchor + v388.mix full-path DD
  (v421/v422 convention); per-year %/month, yearly DD, full-path DD, win
  rates (book episodes via v213.trade_stats dev+_hidden, dip rung exits
  via ret>0 on rung_tp/sl/timeout, all = book+dip), trade counts.
- reproduction gate: this study's M5_human rerun must be BIT-EXACT vs
  research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl
  (max abs d(eq,eq_min) <= 1e-12 over 4 phases) AND equal
  R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 / book_win .6482.
  Else STOP and report the mismatch (no KM1/KM2/CTRL numbers are used).
- NOTE on the common header G2 line: this assignment is the MANUAL
  product, so the reference is M5_human (3.728 / 17.94 / 17.79), NOT the
  BOT G2 baseline. Everything else in the common header applies.

## Kronos input (fixed)

`research/tournament/oc_kronoshidden/kronos_features_4shift.parquet`
(columns sym, shift, T, pdrop2 + others; syms like BTCUSDT). Wait until
all 20 (shift, sym) groups exist (poll every 10 minutes, at most 2 hours
from the start of this task); if the file never reaches 20 groups, STOP
and report blocked (no substitution, no partial E_n).
- Clock shift s uses its own rows: the holding bar opening at
  T = idx[i]+4h on phase s joins the Kronos row
  (sym = cols[a], shift = s, T). Bar-open ex-ante only.
- Contamination CAVEAT (assignment): Kronos released 2025-08, so dev
  years are likely inside its pretraining -> every dev number is an UPPER
  BOUND; the most recent year (2025-09-24..2026-09-23) is the clean test.
  Stated next to every dev number in REPORT.md.
- Missing-data rule (fixed, neutral): E_n needs the 4 OTHER majors at the
  same (T, s). If fewer than 3 of the 4 others have finite pdrop2 there,
  mult = 1.0 (neutral). Else E_n = sum_avail * 4 / n_avail (mean-imputed
  scaling; missing treated as the average of the available others, never
  as 0). T before the feature start -> mult 1.0.

## Pre-registered rows (ONLY these, no other variants)

Majors = BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT. At each bar open T
(phase shift s, coin c): E_n(c, T, s) = sum of pdrop2 of the four OTHER
majors at (T, s) (with the missing-data rule above). Book orders
unchanged on every row; ONLY dip bracket rung sizes scale:
- M5_human (reference, mult 1.0, unpatched eu.simulate).
- KM1: every bracket rung of (c, T) x w1 = 1 / (1 + E_n), then x s1_A
  (training-anchored rescaling below).
- KM2: every bracket rung of (c, T) x w2 = 1 / (1 + 2 E_n), then x s2_A.
- CTRL: every bracket rung of (c, T) x 1 / (1 + c_A) with
  c_A = mean of E_n over the training rows of anchor A (constant scaling,
  exposure control, NO second rescaling: rescaling a constant reproduces
  M5 identically, so CTRL stays constant to test exposure vs allocation).
Training-anchored rescaling (equal average risk, fixed): for each anchor
A, training rows = all (coin, T, shift) feature rows with computable E_n
and T < A - 7 days (UTC, pooled over the 5 coins x 4 shifts; pre-anchor
only). m1_A = mean(w1) and m2_A = mean(w2) over those rows;
s1_A = 1/m1_A, s2_A = 1/m2_A. Final KM mults above. By construction the
training mean mult is 1.0 for KM1/KM2 (= M5's), so the comparison is at
equal average risk, not just less exposure. State s1_A, s2_A, c_A per
anchor and the training row counts in results.json.
Engine mapping (fixed): sleeve_filter(i,a,r) = 0 on the night bar else the
row's Kronos mult for (T = idx[i]+4h, coin = cols[a], shift) (same mult
for every rung r of that coin+bar); agent sleeve_fill_size / sleeve_tp
from pof.pipe_setup unchanged (bar-open T lookup); risk budget 0.26
applies once on the scaled rn as the engine does; no gross cap (M5_human
has none). Night dip skip applies before any scaling.

## Selection (AGENTS.md robust criterion, dev years ONLY)

Compare KM1 vs KM2 ONLY on dev years 2021-2024 (anchors
2021-09-24..2024-09-24): eligible = DDdev4 <= 20 and no losing dev year;
prefer dev4 mean >= 5 %/month if any; among the pool pick the highest
dev4 WORST-year monthly; ties -> higher dev4 mean. Most-recent year
2025-09-24..2026-09-23 is scored ONCE, only for the chosen variant (and
CTRL + M5_human), labelled POST-HOC, never used to choose. If neither is
eligible, PICK = none-eligible. 5-year R5/W/maxDD/fullDD are context only.

## Leakage audit (to be stated in REPORT.md)

- feature timing: Kronos row for bar open T uses only the 400 4h bars
  closing <= T on that shift's grid (oc_kronoshidden PLAN); E_n at T uses
  only pdrop2 values known at T; R2 size/TP tables keyed by holding-bar
  time T (bar-open lookup only, never minute/fill data).
- label windows: no new labels; no outcome enters any sizing decision.
- fit windows: c_A / s1_A / s2_A use only feature rows with T < A - 7d;
  fits of anchor A apply to year [A, A+365d); no statistic from any test
  year feeds any choice.
- fill timing: no fill minutes 0..15 (win_start=15 books,
  sleeve_start=16 dips); limits fill only on 1m trade-through; stop-first
  on same-bar SL+TP touch; timeout at next 4h open.

## Outputs

research/tournament/oc_kronosmanual/{PLAN.md,compute_kronosmanual.py,
results.json,REPORT.md,tmp/} + tests/test_oc_kronosmanual.py only.
results.json: per-anchor c_A/s1_A/s2_A + training counts; per-row
years_R/years_DD/book wins/rung wins/fills; R5/W/maxDD/fullDD/Rdev4/
Wdev4/DDdev4/losing_dev4/Rlast, pick, costs, baseline, contamination
caveat. REPORT.md ends with a 3-line Vietnamese verdict (adopt / reject /
needs prospective evidence) + one-line MANUAL-gap verdict with gap in pp.
MANUAL gate: R5 >= 5 %/month AND fullDD < 20 AND pooled book win >= 55 %.
