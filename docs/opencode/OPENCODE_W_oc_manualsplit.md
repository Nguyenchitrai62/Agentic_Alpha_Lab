# OpenCode task oc_manualsplit - MANUAL brackets split into a half banked fast + a half runner
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_manualsplit/` and `tests/test_oc_manualsplit.py`.
Spec source: docs/opencode/IDEAS_20261007c.md idea B8 (read it).

## Context
MANUAL (human-placeable, book + bracket dip limits with native TP + touch stop) is the product that still misses its floor
(>= 5 %/month, DD < 20, win >= 55 %): best honest = M5 on the human schedule ~3.73 %/month (docs/FINAL_REPORT_VI.md; harness
research/diagnostics/manual_human/manual_human.py, its SUMMARY.md and manual_human.json; audited by research/diagnostics/diag_20261005_audit).
Closed MANUAL variants: oc_manual2/3, oc_manualcap, oc_manualshallow, oc_manualtsmom, oc_manualbf, oc_manualcarry, oc_idea5_manualrest
(read docs/CLOSED_DIRECTIONS.md section 8 first; do not repeat them).

## Rule (fixed)
Start from the M5 human-schedule configuration exactly as manual_human.py runs it (reproduce its published M5 human numbers first - the
4-phase mix 3.73 %/month, DD ~17.8, win ~64.8 % - else stop and report the mismatch).
Every DIP bracket order (one limit buy per coin and depth, native TP limit + exchange-native touch stop) is split into two half-size limits at
the same price with the same stop; half A has TP at +a sigma, half B at +b sigma (both maker limits, placed with the entry as Bybit
TP/SL attachments - a human places them once). Book orders unchanged.
- H1: a = 0.75, b = 1.5.
- H2: a = 0.5, b = 1.0.
(The deployed bracket TP is the reference; if M5's dip TP is not 1.0 sigma, keep the same RATIOS relative to it: a = 0.75 x TP, b = 1.5 x TP
for H1 and 0.5 x / 1.0 x for H2, and say so.)
Same human schedule, same timeouts / exits / fees, minimum notional per half checked (a half below the Bybit minimum notional is merged into
one order with the original TP - count how often).

## Evaluation
4-phase mix per dev year: %/month, yearly DD, full-path DD, win rate (book trades, dip trades, all), trade counts. Choose H1 vs H2 on dev4 with
the robust criterion; most recent year once for the chosen one and M5. Verdict line: does the chosen row close any part of the MANUAL gap
(>= 5 %/month, DD < 20, win >= 55 %)? State the gap in pp.
