# oc_k2manual PLAN (pre-registered, frozen before any run, 2026-10-07)

Can the MANUAL product use the Kronos K2 multiplier (a human reads it at the
bar open)? Assignment docs/opencode/OPENCODE_W_oc_k2manual.md + common header
docs/opencode/OPENCODE_W_COMMON_20261007.md + AGENTS.md.

MANUAL (human-placeable bracket dip limits + book, research/diagnostics/
manual_human, M5_human 3.728 %/month, floor 5) cannot use the minute-level
corr sizing. K2's multiplier (research/tournament/oc_kronoshidden: per
(coin, clock, bar) x1.25 / x0.75 / x1 from Kronos low1) is known at the bar
open, so a human could scale the bracket sizes before placing them
(published on the web plan).

LABEL: new product variant; dev years are inside Kronos pretraining (upper
bound). Every dev number in REPORT.md carries the UPPER-BOUND caveat; the
post-release year 2025-09-24 .. 2026-09-23 is the clean test, scored ONCE
for the frozen rows, never used to choose (there is only one candidate, so
no dev-based choice exists; the last year is POST-HOC context).

## Reference (must reproduce exactly or STOP)

M5_human = deployed MANUAL M5 (v367) on the human schedule, exactly as
research/diagnostics/manual_human/manual_human.py runs it and as scored in
research/diagnostics/oc_manualcap (reset metric + v388.mix full-path DD),
copied as oc_manualsplit / oc_kronosmanual did (same harness lines):
- pipe v367 via pof.pipe_setup (book_mult 0.75, tighten on flat-signal
  losers, M3_R2_RUNG mapped agents ON with per-phase v376/tables_hidden R2
  tables; sleeve_risk_budget 0.26, m_sleeve_sl 8.0, size_mult 4.375,
  rungs (3.0, 4.0); no gross cap; book SL 5.0 / TP 10.0 sigma_d).
- human schedule on EVERY row: 15-min reaction (book orders from minute 15
  via win_start=15, dip limits from minute 16 via sleeve_start=16) + night
  bar skipped: on the holding bar starting at (20+s) UTC no new book order
  (flat -> wait, in position -> hold) and no new dip limit
  (sleeve_filter 0); resting orders, SL, TP stay on the exchange.
- gate costs maker 0.0002 / taker 0.00055, longs pay 0.0001 per 8h
  settlement, shorts nothing; limit fills only on 1m trade-through, no fill
  minutes 0..15 (stricter than the minute-5 user rule); stop-first if
  SL+TP touch the same 1m bar; dip exits: TP limit (maker) / touch stop
  8.0sg market (taker) / timeout at next 4h open (taker).
- 4 phases s=0..3, live window [2021-09-24+sh, 2026-09-23+sh), anchors
  2021-09-24..2025-09-24 (+sh per phase), each year [a0, min(a0+365d,
  live1)).
- scoring: reset_metric.year_reset per anchor + v388.mix full-path DD
  (v421/v422 convention); per-year %/month, yearly DD, full-path DD, win
  rates (book episodes via v213.trade_stats dev+_hidden, dip rung exits
  via ret>0 on rung_tp/sl/timeout, all = book+dip), trade counts, mean
  multiplier diagnostics (decision mean pre-registered, engine-sized mean
  diagnostic only).
- reproduction gate: this study's M5_human rerun must be BIT-EXACT vs
  research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl
  (max abs d(eq,eq_min) <= 1e-12 over 4 phases) AND equal
  R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 / book_win .6482.
  Else STOP and report the mismatch (no KM_K2/CTRL numbers are used).
- NOTE on the common header G2 line: this assignment is the MANUAL
  product, so the reference is M5_human (3.728 / 17.94 / 17.79), NOT the
  BOT G2 baseline. Everything else in the common header applies.

## Kronos K2 input (fixed)

`research/tournament/oc_kronoshidden/kronos_features_4shift.parquet`
(columns sym, shift, T, low1; syms BTCUSDT/ETHUSDT/SOLUSDT/BNBUSDT/XRPUSDT;
20 (shift, sym) groups, frozen) + `research/tournament/oc_kronoshidden/
fits.json` (per-anchor direction + q20/q80 of risk, fixed below; NO
refitting in this study).
- Clock shift s uses its own rows: the holding bar opening at
  T = idx[i]+4h on phase s joins the Kronos row (sym = cols[a], shift = s,
  T). Bar-open ex-ante only; a human reads the published multiplier at the
  bar open and scales the bracket sizes before placing them.
- KM_K2 rule (oc_kronoshidden K2, fixed): risk = -low1. Per anchor A with
  fits.json direction d_A and edges q20_A/q80_A:
  d_A > 0 (all five anchors are +1): risk >= q80 -> 1.25,
  risk <= q20 -> 0.75, else 1.0 (d_A < 0 would mirror; never occurs with
  these fits but coded symmetrically). Missing feature row or non-finite
  low1 -> 1.0 (neutral).
- Fits of anchor A apply to year [A, A+365d) on all four shifts
  (anchor_of with Y1 = 2026-09-23, same convention as tilt_rule.anchor_of
  and oc_kronosmanual; pre-live bars use anchor-2021 fits, outside every
  scoring window). Frozen fits:
  2021-09-24: dir +1, q20 0.8558, q80 2.9066;
  2022-09-24: dir +1, q20 0.5435, q80 2.3280;
  2023-09-24: dir +1, q20 0.5315, q80 2.1136;
  2024-09-24: dir +1, q20 0.5753, q80 2.1936;
  2025-09-24: dir +1, q20 0.5872, q80 2.1828.
- Contamination CAVEAT (assignment label): Kronos released 2025-08, so dev
  years are likely inside its pretraining -> every dev number is an UPPER
  BOUND; the most recent year is the clean test.

## Pre-registered rows (ONLY these, no other variants)

Majors = BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT. Book orders
unchanged on every row; ONLY dip bracket rung sizes scale via
sleeve_filter (0 on the night bar else the row multiplier for
T = idx[i]+4h, coin = cols[a], shift; same mult for every rung r of that
coin+bar); agent sleeve_fill_size / sleeve_tp from pof.pipe_setup
unchanged (bar-open T lookup); risk budget 0.26 applies once on the scaled
rn as the engine does; no gross cap (M5_human has none). Night dip skip
applies before any scaling.
- M5_human (reference, mult 1.0, unpatched eu.simulate; identity filter
  line identical to oc_manualsplit / oc_kronosmanual).
- KM_K2: every bracket rung of (coin, bar) x K2 multiplier above
  (1.25 / 0.75 / 1.0, per-anchor fits.json).
- CTRL: every bracket rung of (coin, bar) x C_y, where C_y = KM_K2's
  realised mean per year y. Pre-registered operationalisation (no outcome
  data, computable before any engine run, as oc_kronoshidden did): the
  feature-table DECISION mean of the KM_K2 rule over all (coin, shift, T)
  feature rows with year_of_feature(T, shift) == y (pooled 5 coins x 4
  shifts; year y covers [A+sh, min(A+365d, live1)) per shift; rows before
  the first anchor or at/after live1 are never simulated and are
  excluded, oc_kronoshidden precedent; fits of anchor A applied to year
  A; missing feature rows count as 1.0 exactly as the engine does). Engine-logged sized-means reported as
  diagnostic next to it. CTRL tests exposure vs allocation: KM_K2 must
  beat the constant to show timing skill.

## Selection (AGENTS.md robust criterion, dev years ONLY)

Single candidate (no K1/K2 choice exists here): KM_K2 is judged ONLY on
dev years 2021-2024 (anchors 2021-09-24..2024-09-24). Eligible =
DDdev4 <= 20 and no losing dev year; the robust preference (dev4 mean >=
5 %/month if any, then highest dev4 WORST-year monthly, ties -> higher
mean) is reported for context vs M5_human/CTRL but picks nothing. The
most recent year 2025-09-24..2026-09-23 is scored ONCE, for all three
frozen rows in the same single pass (oc_manualcap precedent), labelled
POST-HOC / new product variant, never used to choose or to change
anything. If anything changes after seeing an outcome, the original row
stays and the change is added as a disclosed extra row (not planned).
5-year R5/W/maxDD/fullDD are context only. Verdict question: how much of
the MANUAL gap to 5 %/month (M5_human R5 3.728, gap 1.272pp) does K2
close?

## Leakage audit (to be stated in REPORT.md)

- feature timing: Kronos row for bar open T uses only the 400 4h bars
  closing <= T on that shift's grid (oc_kronoshidden PLAN); the K2 mult at
  T uses only the low1 value known at T, joined on (sym, shift, T); R2
  size/TP tables keyed by holding-bar time T (bar-open lookup only, never
  minute/fill data); no 1m data enters any decision.
- label windows: no new labels; no outcome enters any sizing decision.
- fit windows: fits.json is pre-fit on harness rows with t_exit < A - 7d
  (shift-0 only, inherited from oc_kronoshidden); CTRL C_y uses only
  feature rows and fits, no outcomes; fits of anchor A apply to year
  [A, A+365d); no statistic from any test year feeds any choice.
- fill timing: no fill minutes 0..15 (win_start=15 books,
  sleeve_start=16 dips, stricter than the minute-5 user rule); limits fill
  only on 1m trade-through; stop-first on same-bar SL+TP touch; timeout at
  next 4h open.

## Outputs

research/tournament/oc_k2manual/{PLAN.md,compute_k2manual.py,
results.json,REPORT.md,tmp/} + tests/test_oc_k2manual.py only.
results.json: per-year CTRL C_y decision means + n; per-row
years_R/years_DD/book wins/rung wins/fills/decision+sized means;
R5/W/maxDD/fullDD/Rdev4/Wdev4/DDdev4/losing_dev4/Rlast, costs, baseline,
contamination caveat. REPORT.md ends with a 3-line Vietnamese verdict
(adopt / reject / needs prospective evidence) + one-line MANUAL-gap
verdict with gap in pp. MANUAL gate: R5 >= 5 %/month AND fullDD < 20 AND
pooled book win >= 55 %. Heavy run in ONE heavy_slot process (tag
oc_k2manual), heartbeat progress at least every 10 minutes.
