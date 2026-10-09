# oc_cboostmanual PLAN (pre-registered, frozen before any outcome, 2026-10-08)

Can the MANUAL product use the cascade boost (a human scales bracket sizes
x1.5 for 7 days after a cascade)? Assignment
docs/opencode/OPENCODE_W_oc_cboostmanual.md + common header
docs/opencode/OPENCODE_W_COMMON_20261007.md + AGENTS.md +
docs/opencode/OPENCODE_VF_COMMON.md (all read in full).

MANUAL (human-placeable bracket dip limits + book, research/diagnostics/
manual_human, M5_human 3.728 %/month, floor 5) lacks ~1.1-1.3pp.
research/tournament/oc_cascadeboost: on the BOT, B7 (dip budget x1.5 for
7 days after a > 4 sigma 4h move) lifted dev4 from 5.60 to 6.74 with a
better worst year (2.96 vs 2.59). A cascade bar is known at its 4h close
and is a single checklist line for a human ("a 4h candle moved more than
4 sigma -> use 1.5x bracket sizes for 7 days").

LABEL: new product variant; CONTAMINATED like oc_cascadeboost (the idea
was formed after a replica that covered all five years) - the
post-release year 2025-09-24 .. 2026-09-23 is a LABELLED DIAGNOSTIC, not
clean evidence; only prospective paper could confirm. Select on dev4 ONLY
(anchors 2021-2024).

## Reference (must reproduce exactly or STOP)

M5_human = deployed MANUAL M5 (v367) on the human schedule, exactly as
research/diagnostics/manual_human/manual_human.py runs it and as scored in
research/diagnostics/oc_manualcap (reset metric + v388.mix full-path DD),
copied as oc_manualsplit / oc_kronosmanual / oc_k2manual / oc_c2manual did
(same harness lines; this study copies oc_k2manual's harness exactly and
swaps only the multiplier table to the frozen cascade-boost grid):
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
  multiplier diagnostics (parquet time-bar mean pre-registered, engine-sized
  mean diagnostic only).
- reproduction gate: this study's M5_human rerun must be BIT-EXACT vs
  research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl
  (max abs d(eq,eq_min) <= 1e-12 over 4 phases) AND equal
  R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 / book_win .6482.
  Else STOP and report the mismatch (no KM_B7/KM_B3 numbers are used).
- NOTE on the common header G2 line: this assignment is the MANUAL
  product, so the reference is M5_human (3.728 / 17.94 / 17.79), NOT the
  BOT G2 baseline. Everything else in the common header applies.

## Cascade trigger + boost window (frozen, causal, VERBATIM oc_cascadedelay)

- Source (read-only): research/tournament/oc_kronoshidden/
  bars_4h_4shift.parquet (5 majors x shifts 0..3 4h OHLCV; per (sym, shift)
  series sorted by T = bar open; bar close time = T + 4h). Only the close
  column is used. No new data; this study reuses the frozen output
  research/tournament/oc_cascadeboost/boost_mult_4shift.parquet
  (shift, T, boosted_B7, boosted_B3, mult_B7, mult_B3; 53,877 rows, same
  grid as the delay file; union triggers per shift identical to
  oc_cascadedelay by verbatim arithmetic).
- READING OF "range > 4sg" (frozen, disclosed, inherited): "range" =
  absolute close-to-close log move |r[i]| with r[i] = ln(C[i]/C[i-1])
  (r[0] = NaN). REJECTED alternative: (H-L)-based range - highs/lows are
  not closes, contradicting the twice-stated "from closes only".
- Sigma (frozen): SIG[i] = std(ddof=1) of r[i-540 .. i-1] (540 returns =
  90d x 6 bars/day), min_periods 120 (else NaN). SIG[i] uses only bars with
  close_time <= T[i] (r[i-1] resolves at close_time[i-1] = T[i]); the
  tested return r[i] resolves at close_time[i] = T[i]+4h and is NEVER in its
  own sigma window - causal by construction, no self-inclusion.
- TRIGGER: bar i of (sym, shift) fires iff SIG[i] finite > 0 AND
  |r[i]| > 4.0 * SIG[i] (strictly greater; 4.0 frozen). Trigger close time
  tc = T[i] + 4h (known at tc). NaN SIG or non-finite closes -> never fires
  (conservative; counted and disclosed in oc_cascadedelay/oc_cascadeboost).
- BOOST WINDOW (market-wide per shift, frozen): a dip decision at
  holding-bar open T on shift s is BOOSTED iff there EXISTS a trigger (ANY
  of the 5 majors, same shift s) with 0 < T - tc <= N days (strictly after
  the trigger close, up to and including +N days). Same boosted(T, s) for
  all 5 coins. On the 4h grid this is T in (tc, tc+Nd] = k = 1..42 bars
  (B7) / 1..18 bars (B3). The human acts from the NEXT bar after the
  cascade bar closes (k >= 1 by the strict inequality), respecting the
  M5_human schedule (15-min reaction via win_start=15/sleeve_start=16, no
  fill minutes 0..15; night bar skipped via sleeve_filter 0 before any
  scaling). REJECTED alternative: per-coin triggers - disclosed (inherited).
- MULT: boosted -> 1.5, else 1.0. Missing trigger history (T before first
  computable bar) -> 1.0 (never boosted; inert - history from 2020-08-01
  gives full 540-return windows for all of 2021-09-24.., disclosed with
  counts in oc_cascadedelay/oc_cascadeboost). No skipped anchor year
  expected (missing -> mult 1, counted).
- cboost_rule.py in this folder is a VERBATIM arithmetic copy of
  oc_cascadeboost/boost_rule.py (constants BOOST = 1.5, B7_DAYS = 7,
  B3_DAYS = 3) for unit tests; the engine joins the FROZEN parquet (no
  recomputation, no tuning).

## No fits (nothing estimated)

There are no fitted parameters here: trigger threshold 4.0, windows
(540/120/min), boost 1.5, N = 7/3 are all frozen ex-ante round numbers
(1.5 = inverted 0.5 of oc_cascadedelay; N from the assignment, never
scanned). No harness join, no quantiles, no embargo beyond strict causality
(trigger at tc uses only closes with close_time <= tc). No statistic from
any test year feeds any choice.

## Pre-registered rows (ONLY these, no other variants)

Majors = BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT. Book orders
unchanged on every row; ONLY dip bracket rung sizes scale via
sleeve_filter (0 on the night bar else the row multiplier for
T = idx[i]+4h on this shift, market-wide same mult for every coin and
every rung r of that bar); agent sleeve_fill_size / sleeve_tp from
pof.pipe_setup unchanged (bar-open T lookup); risk budget 0.26 applies once
on the scaled rn as the engine does; no gross cap (M5_human has none).
Night dip skip applies before any scaling. Engine join: exact match on the
shift grid, fallback to latest grid time <= T (causal ffill), missing ->
1.0 (counted).
- M5_human (reference, mult 1.0, unpatched eu.simulate; identity filter
  line identical to oc_manualsplit / oc_kronosmanual / oc_k2manual /
  oc_c2manual).
- KM_B7: every bracket rung of (coin, bar) x 1.5 iff T opens inside the
  7-day window after a cascade bar (frozen definition above), else x 1.0.
- KM_B3: the same with 3 days.

## Selection (AGENTS.md robust criterion, dev years ONLY)

Two candidates on the SAME frozen trigger family: KM_B7 vs KM_B3, judged
ONLY on dev years 2021-2024 (anchors 2021-09-24..2024-09-24). Eligible =
DDdev4 <= 20 and no losing dev year; the robust preference (dev4 mean >=
5 %/month if any, then highest dev4 WORST-year monthly, ties -> higher
mean) picks the winner; reported vs M5_human context. The most recent year
2025-09-24..2026-09-23 is scored ONCE, for all three frozen rows in the
same single pass (oc_k2manual/oc_c2manual precedent), labelled
CONTAMINATED / new product variant diagnostic (like oc_cascadeboost),
never used to choose or to change anything. If anything changes after
seeing an outcome, the original row stays and the change is added as a
disclosed extra row (not planned). 5-year R5/W/maxDD/fullDD are context
only. Verdict question: how much of the MANUAL gap to 5 %/month
(M5_human R5 3.728, gap 1.272pp) does the cascade boost close?
MANUAL gate: R5 >= 5 %/month AND fullDD < 20 AND pooled book win >= 55 %.

## Leakage audit (to be stated in REPORT.md)

- feature timing: trigger at tc uses only closes with close_time <= tc;
  SIG window excludes the tested bar (no self-inclusion); boost window
  strictly after tc (0 < T-tc <= Nd, k >= 1: the human acts from the next
  bar); the boost mult at T joins the frozen parquet on (shift, T) only;
  R2 size/TP tables keyed by holding-bar time T (bar-open lookup only,
  never minute/fill data); no 1m data enters any decision.
- label windows: no new labels; no outcome enters any sizing decision.
- fit windows: no fits; threshold/windows/N/boost frozen ex-ante, never
  scanned; no statistic from any test year feeds any choice.
- fill timing: no fill minutes 0..15 (win_start=15 books,
  sleeve_start=16 dips, stricter than the minute-5 user rule); limits fill
  only on 1m trade-through; stop-first on same-bar SL+TP touch; timeout at
  next 4h open; engine join exact-or-causal-ffill (latest grid <= T).

## Outputs

research/tournament/oc_cboostmanual/{PLAN.md (this file, frozen),
cboost_rule.py, compute_cboostmanual.py, results.json, REPORT.md, tmp/}
+ tests/test_oc_cboostmanual.py only. results.json: per-row
years_R/years_DD/book wins/rung wins/fills/parquet+sized means;
R5/W/maxDD/fullDD/Rdev4/Wdev4/DDdev4/losing_dev4/Rlast, costs, baseline,
contamination caveat. REPORT.md ends with a 3-line Vietnamese verdict
(adopt / reject / needs prospective evidence) + one-line MANUAL-gap
verdict with gap in pp. Heavy run in ONE heavy_slot process (tag
oc_cboostmanual), heartbeat print at least every 10 minutes
(HEARTBEAT_S = 600). Progress print every 10 minutes.

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason;
  the original row stays and the change is a disclosed extra row).
