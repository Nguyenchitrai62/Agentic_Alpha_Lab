# oc_m_settleskip PLAN (pre-registered, frozen before any outcome, 2026-10-08)

IDEAS9 #6 (docs/opencode/IDEAS9_20261008.md): Settlement-clock placement skip
(no-threshold funding clock) on the MANUAL product. Assignment
docs/opencode/OPENCODE_W_oc_m_settleskip.md + common header
docs/opencode/OPENCODE_W_COMMON_20261007.md + AGENTS.md + OPENCODE_VF_COMMON.md.

MANUAL = book + bracket dip limits with native TP/SL + book, 15-min reaction,
night bar skipped (M5_human 5y 3.728 %/mo, DD 17.94, ~1.272 pp short of the
5 % floor). Mech: crowded-settlement bleed + gap risk sits exactly at
00/08/16 UTC; predicted-funding thresholds drift (oc_bookfunding/fundclock).
Clock needs no fit. Prior 7 % return / 10 % DD. Effect pre-registered by the
idea: ~0 return (+-0.04 %/mo), DD -0-0.2 pp.

## Reference (must reproduce exactly or STOP)

M5_human = deployed MANUAL M5 (v367) on the human schedule, exactly as
research/diagnostics/manual_human/manual_human.py runs it and as scored in
research/diagnostics/oc_manualcap (reset metric + v388.mix full-path DD),
copied as oc_manualsplit / oc_kronosmanual / oc_k2manual / oc_c2manual /
oc_m_btceth / oc_m_conflict / oc_m_top2 did (same harness lines, this study
copies oc_m_top2's harness exactly and changes ONLY the per-bar placement
gate below):
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
- Bybit order types (idea #6): on a skipped bar place nothing (no GTC);
  resting TP/SL stay. A human reads the clock once per bar, no re-pegging;
  checklist a few times/day.
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

Idea rule (frozen ex-ante, clock-only, no threshold, no fit):
settle[i] = True when a funding settlement (00/08/16 UTC) lies in the
holding bar (idx[i]+4h, idx[i]+8h], i.e. exactly
phase_offset_full.settle_flags(idx): end=idx+8h, end.floor("8h") > idx+4h.
Each settlement falls in exactly one holding bar (engine funding
convention); pure UTC-clock function of the bar timestamp, no data.
- M5_human (reference, identity filter line identical to oc_k2manual /
  oc_m_top2; settle gate never applied).
- V1_SETTLE: skip NEW bracket placement on bars with settle[i] True.
- V2_SETTLE_NEXT: V1 + skip the bar after: skip[i] = settle[i] OR
  settle[i-1] (i-1 < 0 -> False; previous bar only, strictly causal).

Interpretation (frozen, disclosed): "brackets" = BOTH sleeves (book orders
AND dip bracket limits), because the idea says "place nothing on skipped
bars" with "Holds/exits unchanged" (a dip-only filter would still place
book orders, not "nothing"; the CLOSED dip-only precedents oc_fundclock-W1
dip cancel and oc_bookfunding level tilt are therefore NOT this idea).
Concretely, on a skipped bar i (settle and/or night): book policy returns
wait-if-flat / hold-if-in-position (same hold semantic as the night skip:
resting SL/TP stay, no new order is placed) and sleeve_filter returns 0.0
(no new dip limit). Kept bars are completely unchanged M5_human. The night
skip applies FIRST on every row, identically on both legs (leak note:
human schedule identical both legs).

Disclosed arithmetic (frozen, no outcome): on every phase shift the settle
bars alternate with non-settle bars (3 of 6 bars/day, ~50% of bars), so V1
skips ~50% of bars and V2 (settle OR previous-settle) skips ~100% of bars:
V2 is expected to place almost nothing and sit near-flat (~0 %/mo, ~0 DD).
That degenerate consequence is part of the pre-registered rule as written
("V1 + skip the bar after"); it is reported honestly, not repaired.

Closest CLOSED (disclosed, not this idea): oc_fundclock W2
(predicted-funding p90 threshold, dev 6.162 but clean 4.488) and
oc_bookfunding (7d LEVEL tilt) both fit a funding LEVEL threshold; this is
CLOCK-only skip, no level/threshold, no p90 refit.

## Selection (AGENTS.md robust criterion, dev years ONLY)

Compare V1 vs V2 ONLY on dev years 2021-2024 (anchors 2021-09-24..2024-09-24):
eligible = DDdev4 <= 20 and no losing dev year; prefer dev4 mean >= 5
%/month if any; among the pool pick the highest dev4 WORST-year monthly;
ties -> higher dev4 mean. If neither is eligible, PICK = none-eligible.
The most recent year 2025-09-24..2026-09-23 is scored ONCE, only for the
chosen variant (and M5_human), labelled POST-RELEASE, never used to choose.
Single frozen 4-phase pass over the full 5-year window (oc_k2manual /
oc_m_top2 precedent): the non-pick's last-year row is shown for
completeness from the same pass only, never used for any decision and not
re-scored. If anything changes after seeing an outcome, the original row
stays and the change is added as a disclosed extra row (not planned).
5-year R5/W/maxDD/fullDD are context only. Verdict question: how much of
the MANUAL gap to 5 %/month (M5_human R5 3.728, gap 1.272 pp) does the pick
close?

## Leakage audit (to be stated in REPORT.md)

- feature timing: skip keys only on the bar timestamp via the fixed UTC
  clock (settle_flags on idx+4h/idx+8h; V2 also uses settle[i-1], strictly
  past); R2 size/TP tables keyed by holding-bar time T (bar-open lookup
  only, never minute/fill data); no 1m data enters any decision; no
  intraday re-rank.
- label windows: no new labels; no outcome enters any placement decision.
- fit windows: no fits/thresholds/quantiles of any kind; settlements are
  the fixed public UTC schedule; human schedule identical both legs.
- fill timing: no fill minutes 0..15 (win_start=15 books, sleeve_start=16
  dips, stricter than the minute-5 user rule); limits fill only on 1m
  trade-through; stop-first on same-bar SL+TP touch; dip timeout at next
  4h open.

## Outputs

research/tournament/oc_m_settleskip/{PLAN.md,compute_m_settleskip.py,
results.json,REPORT.md,tmp/} + tests/test_oc_m_settleskip.py only.
results.json: per-row years_R/years_DD/book wins/rung wins/fills,
R5/W/maxDD/fullDD/Rdev4/Wdev4/DDdev4/losing_dev4/Rlast, pick + eligibility,
costs, baseline, per-year settle skip rates. REPORT.md ends with a 3-line
Vietnamese verdict (adopt / reject / needs prospective evidence) + one-line
MANUAL-gap verdict with gap in pp. MANUAL gate: R5 >= 5 %/month AND
fullDD < 20 AND pooled book win >= 55 %. Heavy run in ONE heavy_slot
process (tag oc_m_settleskip), heartbeat progress at least every 10
minutes, nohup + log under tmp/.
