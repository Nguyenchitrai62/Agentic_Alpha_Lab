# oc_m_conflict PLAN (pre-registered, frozen before any outcome, 2026-10-08)

IDEAS9 #3 (docs/opencode/IDEAS9_20261008.md): Book-vs-dip conflict skip
(human netting-lite) on the MANUAL product. Assignment
docs/opencode/OPENCODE_W_oc_m_conflict.md + common header
docs/opencode/OPENCODE_W_COMMON_20261007.md + AGENTS.md + OPENCODE_VF_COMMON.md.

MANUAL = book + bracket dip limits with native TP/SL + book, 15-min reaction,
night bar skipped (M5_human 5y 3.728 %/mo, DD 17.94, ~1.272 pp short of the
5 % floor). Mech: worst MANUAL stretches hold short book + long dip on the
same coin into the same sell-off (oc_ddanat_g2 concentration). A human can
read two lines and skip the contradiction. Prior 10 %. Effect pre-registered
by the idea: +0.0-0.12 %/mo, DD -0-0.4 pp.

## Reference (must reproduce exactly or STOP)

M5_human = deployed MANUAL M5 (v367) on the human schedule, exactly as
research/diagnostics/manual_human/manual_human.py runs it and as scored in
research/diagnostics/oc_manualcap (reset metric + v388.mix full-path DD),
copied as oc_manualsplit / oc_kronosmanual / oc_k2manual / oc_c2manual /
oc_m_btceth did (same harness lines, this study copies oc_k2manual's harness
exactly and changes ONLY the dip placement gate below):
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
- Bybit order types (idea #3): no GTC placed on a skipped coin; resting
  TP/SL stay. A human reads two lines once per bar, no re-pegging.
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
  Else STOP and report the mismatch (no V1/V2 numbers are used).
- NOTE on the common header G2 line: this assignment is the MANUAL
  product, so the reference is M5_human (3.728 / 17.94 / 17.79), NOT the
  BOT G2 baseline. Everything else in the common header applies.

## Pre-registered rows (ONLY these, no other variants)

Idea rule (frozen ex-ante, dip sleeve ONLY, book orders untouched on every
row; night skip applies FIRST on every row):
- M5_human (reference, all 5 majors, identity filter line identical to
  oc_k2manual / oc_c2manual / oc_m_btceth).
- V1: if the close-known book target w[i,a] < 0 strictly (book SHORT) on
  coin c at bar i, skip the new long dip bracket on c that bar
  (sleeve_filter returns 0.0 for all rungs of (i,a)). Book policy,
  resting TP/SL, holds/exits unchanged.
- V2: same skip, but ONLY when the short is strong: w[i,a] < 0 AND
  |w[i,a]| > THR[c,A], where A is the anchor of the holding-bar open
  T = idx[i]+4h on that phase shift (anchor_of convention below) and
  THR[c,A] is the frozen per-coin pre-anchor median |w|:
  median of |std_books| for coin c over history rows with index < A - 7d
  (std_books = fw.research_books_d2(eu) before the ffill to idx; finite
  values only; < 100 values -> +inf, i.e. never skip, disclosed).
  THR is computed once per phase from data only (no outcomes), before the
  engine run, and frozen.

Closest CLOSED (disclosed, not this idea): oc_netting (BOT budget netting
N1 cut 39 % of dips) vetoes by the same contradictory sign but on the BOT
harness with bear-halved books and a gross cap; this study is MANUAL
M5_human with plain research books and no cap. oc_manual3 (static corr
proxy) never used the book sign.

## Selection (AGENTS.md robust criterion, dev years ONLY)

Compare V1 vs V2 ONLY on dev years 2021-2024 (anchors 2021-09-24..2024-09-24):
eligible = DDdev4 <= 20 and no losing dev year; prefer dev4 mean >= 5
%/month if any; among the pool pick the highest dev4 WORST-year monthly;
ties -> higher dev4 mean. If neither is eligible, PICK = none-eligible.
The most recent year 2025-09-24..2026-09-23 is scored ONCE, only for the
chosen variant (and M5_human), labelled POST-RELEASE, never used to choose.
Single frozen 4-phase pass over the full 5-year window (oc_k2manual /
oc_m_btceth precedent): the non-pick's last-year row is shown for
completeness from the same pass only, never used for any decision and not
re-scored. If anything changes after seeing an outcome, the original row
stays and the change is added as a disclosed extra row (not planned).
5-year R5/W/maxDD/fullDD are context only. Verdict question: how much of
the MANUAL gap to 5 %/month (M5_human R5 3.728, gap 1.272 pp) does the pick
close?

## Leakage audit (to be stated in REPORT.md)

- feature timing: skip keys only on (bar index i, coin a) via the
  close-known book target w[i,a] = ffill'd research book at idx[i]
  (oc_netting precedent; no 1m/minute/fill data); THR[c,A] from history
  rows with index < A - 7d only; R2 size/TP tables keyed by holding-bar
  time T (bar-open lookup only, never minute/fill data); no 1m data enters
  any decision.
- label windows: no new labels; no outcome enters any placement decision.
- fit windows: no fits; THR medians use only book weights (not returns)
  ending before anchor minus 7d embargo; fits/thresholds of M5_human frozen;
  anchor A's THR applies to year [A, A+365d); no statistic from any test
  year feeds any choice.
- fill timing: no fill minutes 0..15 (win_start=15 books, sleeve_start=16
  dips, stricter than the minute-5 user rule); limits fill only on 1m
  trade-through; stop-first on same-bar SL+TP touch; dip timeout at next
  4h open.

## Outputs

research/tournament/oc_m_conflict/{PLAN.md,compute_m_conflict.py,
results.json,REPORT.md,tmp/} + tests/test_oc_m_conflict.py only.
results.json: per-row years_R/years_DD/book wins/rung wins/fills,
R5/W/maxDD/fullDD/Rdev4/Wdev4/DDdev4/losing_dev4/Rlast, pick + eligibility,
costs, baseline, THR medians + skip rates. REPORT.md ends with a 3-line
Vietnamese verdict (adopt / reject / needs prospective evidence) + one-line
MANUAL-gap verdict with gap in pp. MANUAL gate: R5 >= 5 %/month AND
fullDD < 20 AND pooled book win >= 55 %. Heavy run in ONE heavy_slot process
(tag oc_m_conflict), heartbeat progress at least every 10 minutes, nohup +
log under tmp/.
