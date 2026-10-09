# oc_m_btceth PLAN (pre-registered, frozen before any outcome, 2026-10-08)

IDEAS9 #1 (docs/opencode/IDEAS9_20261008.md): BTC+ETH-only bracket focus
(liquid-pair concentration) on the MANUAL product. Assignment
docs/opencode/OPENCODE_W_oc_m_btceth.md + common header
docs/opencode/OPENCODE_W_COMMON_20261007.md + AGENTS.md + OPENCODE_VF_COMMON.md.

MANUAL = book + bracket dip limits with native TP/SL + book, 15-min reaction,
night bar skipped (M5_human 5y 3.728 %/mo, DD 17.94, ~1.272 pp short of the
5 % floor). Mech: human bleed (~0.6 pp) spreads over 5 coins; Bybit costs
concentrate in BNB/XRP. Concentrate scarce attention on the cheapest-to-trade
pair. Prior 14 %. Effect pre-registered by the idea: +0.1-0.3 %/mo via fill
quality, DD flat/down, win +0-1 pp.

## Reference (must reproduce exactly or STOP)

M5_human = deployed MANUAL M5 (v367) on the human schedule, exactly as
research/diagnostics/manual_human/manual_human.py runs it and as scored in
research/diagnostics/oc_manualcap (reset metric + v388.mix full-path DD),
copied as oc_manualsplit / oc_kronosmanual / oc_k2manual / oc_c2manual did
(same harness lines, this study copies oc_k2manual's harness exactly and
changes ONLY the coin universe below):
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
- Bybit order types (idea #1): resting GTC limits + attached TP/SL
  (OCO-like pair), reduce-only SL; a human places them once per bar, no
  re-pegging; checklist a few times/day.
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

Idea rule (frozen ex-ante, never picked per-year): place brackets only on
the named coins; others flat.
- M5_human (reference, all 5 majors, identity filter line identical to
  oc_manualsplit / oc_k2manual / oc_c2manual).
- V1_BTCETH: brackets ONLY on BTCUSDT + ETHUSDT. All other coins flat.
- V2_BTCETHSOL: brackets ONLY on BTCUSDT + ETHUSDT + SOLUSDT (drop BNB/XRP
  only). All other coins flat.

Interpretation (frozen, disclosed): "brackets" = BOTH sleeves (book orders
AND dip bracket limits), because the idea says "Others flat" (a dip-only
filter would leave book positions on the dropped coins, not flat; the
CLOSED dip-only precedent oc_manual2coin kept the book on all five coins
and is therefore NOT this idea). Concretely, on an excluded coin c:
book policy returns wait-if-flat / hold-if-in-position (same hold semantic
as the night skip: resting SL/TP stay, no new order is placed; the run
starts flat and never opens c, so c stays flat), and sleeve_filter returns
0.0 (no new dip limit). Allowed coins are completely unchanged M5_human.
Coin sets are frozen string constants (V1_COINS, V2_COINS below); no fit,
no threshold, no per-year choice. The human schedule (night skip) applies
FIRST on every row, identically on both legs (leak note: human schedule
identical both legs).

## Selection (AGENTS.md robust criterion, dev years ONLY)

Compare V1 vs V2 ONLY on dev years 2021-2024 (anchors 2021-09-24..2024-09-24):
eligible = DDdev4 <= 20 and no losing dev year; prefer dev4 mean >= 5
%/month if any; among the pool pick the highest dev4 WORST-year monthly;
ties -> higher dev4 mean. If neither is eligible, PICK = none-eligible.
The most recent year 2025-09-24..2026-09-23 is scored ONCE, only for the
chosen variant (and M5_human), labelled POST-RELEASE, never used to choose.
If anything changes after seeing an outcome, the original row stays and the
change is added as a disclosed extra row (not planned). 5-year R5/W/maxDD/
fullDD are context only. Verdict question: how much of the MANUAL gap to
5 %/month (M5_human R5 3.728, gap 1.272 pp) does the pick close?

## Leakage audit (to be stated in REPORT.md)

- feature timing: coin allow-list is a frozen string constant (no data);
  book policy wrapper keys only on (bar index i, coin index a, position
  state) plus the night hour; dip sleeve_filter keys only on (bar index i,
  coin index a); R2 size/TP tables keyed by holding-bar time T (bar-open
  lookup only, never minute/fill data); no 1m data enters any decision.
- label windows: no new labels; no outcome enters any placement decision.
- fit windows: no fits/thresholds/quantiles of any kind; coin sets frozen
  ex-ante; sigma/TP distances frozen (M5_human); human schedule identical
  both legs.
- fill timing: no fill minutes 0..15 (win_start=15 books, sleeve_start=16
  dips, stricter than the minute-5 user rule); limits fill only on 1m
  trade-through; stop-first on same-bar SL+TP touch; dip timeout at next
  4h open.

## Outputs

research/tournament/oc_m_btceth/{PLAN.md,compute_m_btceth.py,
results.json,REPORT.md,tmp/} + tests/test_oc_m_btceth.py only.
results.json: per-row years_R/years_DD/book wins/rung wins/fills,
R5/W/maxDD/fullDD/Rdev4/Wdev4/DDdev4/losing_dev4/Rlast, pick + eligibility,
costs, baseline, coin sets. REPORT.md ends with a 3-line Vietnamese verdict
(adopt / reject / needs prospective evidence) + one-line MANUAL-gap verdict
with gap in pp. MANUAL gate: R5 >= 5 %/month AND fullDD < 20 AND pooled
book win >= 55 %. Heavy run in ONE heavy_slot process (tag oc_m_btceth),
heartbeat progress at least every 10 minutes.
