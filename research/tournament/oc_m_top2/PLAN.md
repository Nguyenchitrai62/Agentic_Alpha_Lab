# oc_m_top2 PLAN (pre-registered, frozen before any outcome, 2026-10-08)

IDEAS9 #4 (docs/opencode/IDEAS9_20261008.md): Max-2 bracket priority
(attention cap by conviction) on the MANUAL product. Assignment
docs/opencode/OPENCODE_W_oc_m_top2.md + common header
docs/opencode/OPENCODE_W_COMMON_20261007.md + AGENTS.md + OPENCODE_VF_COMMON.md.

MANUAL = book + bracket dip limits with native TP/SL + book, 15-min reaction,
night bar skipped (M5_human 5y 3.728 %/mo, DD 17.94, ~1.272 pp short of the
5 % floor). Mech: gross cap is what contains crash exposure (oc_b7frontier:
D13BF+B7 breaches, G2+B7 capped holds); a human cannot run it but CAN cap
count by conviction. Prior 9 %. Effect pre-registered by the idea:
~0 return (+-0.08 %/mo), DD -0-0.5 pp.

## Reference (must reproduce exactly or STOP)

M5_human = deployed MANUAL M5 (v367) on the human schedule, exactly as
research/diagnostics/manual_human/manual_human.py runs it and as scored in
research/diagnostics/oc_manualcap (reset metric + v388.mix full-path DD),
copied as oc_manualsplit / oc_kronosmanual / oc_k2manual / oc_c2manual /
oc_m_btceth did (same harness lines, this study copies oc_m_btceth's harness
exactly and changes ONLY the per-bar coin gate below):
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
- Bybit order types (idea #4): resting GTC limits + attached TP/SL
  (OCO-like pair), reduce-only SL; GTC limits only for the ranked coins; a
  human places them once per bar, no re-pegging; checklist a few times/day.
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

Idea rule (frozen ex-ante): if >2 coins signal on the same bar, place only
the top-2 by |w| (V1); V2 top-3. Rank frozen from close-known |w|, ties
BTC>ETH>SOL>BNB>XRP. K frozen integers; no intraday re-rank.
- M5_human (reference, all 5 majors, identity filter line identical to
  oc_k2manual / oc_c2manual / oc_m_btceth).
- V1_TOP2: K = 2. At each bar, rank the 5 majors by |w[i,a]| and place new
  brackets ONLY on the top-2; the other 3 get nothing new that bar.
- V2_TOP3: K = 3. Same, keep the top-3, skip the other 2.

Interpretation (frozen, disclosed): "brackets" = BOTH sleeves (book orders
AND dip bracket limits), because the idea says "place only top-2" with
"GTC limits only for ranked coins" (both order types are GTC limits), and
"keeps all depths/SL/TP" refers to the kept coins' dip structure staying
exactly M5_human (no x1.5 rescale, unlike the CLOSED dip-only oc_manual2).
Concretely, on a skipped coin c at bar i: book policy returns wait-if-flat
/ hold-if-in-position (same hold semantic as the night skip and oc_m_btceth:
resting SL/TP stay, no new order is placed) and sleeve_filter returns 0.0
(no new dip limit). Kept coins are completely unchanged M5_human (all
depths/SL/TP, size x1.0). The "if >K signal" condition binds on every
non-night bar: all 5 majors are ranked every bar (no invented signal
threshold exists in the idea; the only frozen numbers are K = 2 / 3), so
each non-night bar places at most K coins. The night skip applies FIRST on
every row, identically on both legs (leak note: human schedule identical
both legs). Rank key w[i,a] = close-known ffill'd research book
(fw.research_books_d2 ffill'd to idx, same w as oc_m_conflict) at idx[i];
non-finite treated as 0.0; ties broken by canonical MAJORS order
(BTC>ETH>SOL>BNB>XRP), independent of the phase's column permutation.

Closest CLOSED (disclosed, not this idea): oc_manualcap (G15/G10 pure gross
caps) caps notional, this caps count; oc_manual2 (top-2 by DIP-depth with
x1.5 rescale) ranks by depth, this ranks by BOOK conviction |w| with no
rescale and keeps all depths/SL/TP.

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

- feature timing: rank key is the close-known book target w[i,a] = ffill'd
  research book at idx[i] only (no 1m/minute/fill data); R2 size/TP tables
  keyed by holding-bar time T (bar-open lookup only, never minute/fill
  data); no 1m data enters any decision; no intraday re-rank (kept set
  cached per bar).
- label windows: no new labels; no outcome enters any placement decision.
- fit windows: no fits/thresholds/quantiles of any kind; K = 2 / 3 frozen
  integers ex-ante, never picked per-year; sigma/TP distances frozen
  (M5_human); human schedule identical both legs.
- fill timing: no fill minutes 0..15 (win_start=15 books, sleeve_start=16
  dips, stricter than the minute-5 user rule); limits fill only on 1m
  trade-through; stop-first on same-bar SL+TP touch; dip timeout at next
  4h open.

## Outputs

research/tournament/oc_m_top2/{PLAN.md,compute_m_top2.py,
results.json,REPORT.md,tmp/} + tests/test_oc_m_top2.py only.
results.json: per-row years_R/years_DD/book wins/rung wins/fills,
R5/W/maxDD/fullDD/Rdev4/Wdev4/DDdev4/losing_dev4/Rlast, pick + eligibility,
costs, baseline, K values + per-year top-K skip rates. REPORT.md ends with
a 3-line Vietnamese verdict (adopt / reject / needs prospective evidence)
+ one-line MANUAL-gap verdict with gap in pp. MANUAL gate: R5 >= 5 %/month
AND fullDD < 20 AND pooled book win >= 55 %. Heavy run in ONE heavy_slot
process (tag oc_m_top2), heartbeat progress at least every 10 minutes,
nohup + log under tmp/.
