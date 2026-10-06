# oc_tpfill REPORT (2026-10-06; PLAN pre-registered before any outcome)

Realism check #79 = IDEAS3 idea 7 (native TP attached at fill minute, BOT).
BASE = oc_dipexit D0 replica (TP 1-sigma limit live from f+1, STRICT high>tp).
FIX = same except the TP may also fill in the fill minute f itself iff
close(f) >= tp (conservative proxy), exit at tp 2*maker, x=f; else BASE race.
Majors x R2 depths (2.5/3/3.5/4/5) x 5 anchor years (bar-open keyed) x 4 clock
phases, B1 sizes w=1/(1+n), paired rungs (both nets finite). All five years are
research data: findings need prospective validation (disclosed vs RULES.md
hidden-year rule).

## Setup / replica validation

22,312 paired rungs (phase-0 fills/coin 1067/1126/952/1179/1174 = oc_dipexit's
5498 exactly; per-phase totals 5498/5615/5610/5529). Ledger checksum
849fe7889b793868. Same-minute TPs (FIX how=tp_same): 669 (3.0% of fills, 5.5%
of all TPs; 0 with same-minute deep low <= backstop). Year totals (4 phases):
Y21 52, Y22 158, Y23 320, Y24 61, Y25 78. Every one of the 669 exits at f while
BASE exits at f+1 (dx=1 for all 669); exit-date calendar day identical for all.

## Per-year 4-phase means (S=sum w*y raw; win=equal-weight net>0; W=worst exit-day sum; DD=cumulative-path maxDD>=0)

| year | sameTP (tot/mean4) | BASE S / win / W / DD | FIX S / win / W / DD | delta S (FIX-BASE) |
|---|---|---|---|---|
| 2021 | 52 / 13.0 | 0.9113 / .660 / -0.7398 / 0.8560 | 0.9113 / .660 / -0.7398 / 0.8560 | +0.000000 |
| 2022 | 158 / 39.5 | 0.8326 / .699 / -0.7258 / 0.9506 | 0.8326 / .699 / -0.7258 / 0.9506 | +0.000000 |
| 2023 | 320 / 80.0 | 2.0998 / .748 / -0.7352 / 0.8000 | 2.0998 / .748 / -0.7352 / 0.8000 | +0.000000 |
| 2024 | 61 / 15.2 | 3.1974 / .734 / -0.2736 / 0.3545 | 3.1974 / .734 / -0.2736 / 0.3545 | +0.000000 |
| 2025 | 78 / 19.5 | 0.6772 / .661 / -0.5084 / 0.6073 | 0.6772 / .661 / -0.5084 / 0.6073 | +0.000000 |
| 5y sum of means | 669 | BASE 7.7183 | FIX 7.7183 | dSum5y = +0.000000 |

Per-phase sums are identical arm-to-arm in every (phase, year) cell (20/20).
Win rate, worst day and maxDD identical to 4 decimals in every year (net diff
exactly 0.0 on all 669 same-minute rungs; all 669 are BASE-TP at the same tp
price, so 2*maker round-trips coincide).

## What the 669 same-minute TPs became under BASE

BASE how on the 669: tp 669 (100%), stop 0, backstop 0, timeout 0. Net
(FIX-BASE) = 0 exactly (min/max 0). Mechanism: close(f)>=tp puts the next
minute's open at/above tp, so STRICT high(f+1)>tp fires at the same tp price
one minute later, same calendar exit date. FIX front-runs the booking by one
minute and changes nothing economic.

## Default-rule context (NOT a selection)

delta(Y)>=0 in 5/5 years (all exact zeros; strict > in 0/5). LOO sum>=0 in
5/5 (all zeros; strict > in 0/5). The >= form passes vacuously on zeros; there
is no sign, no magnitude, and no tradable effect, so no PROMISING verdict is
drawn by design (assignment: "Not a selection").

## Notes

- Rung-y sums are B1 size-weighted raw units, not portfolio %/month.
- The proxy is deliberately conservative (close>=tp, not high>tp); a looser
  high-based proxy would book more same-minute TPs but is NOT tested here
  (would need its own pre-registration).
- Repro: `research/tournament/oc_tpfill/{PLAN.md,tpfill.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_tpfill.py` (10 pass); one
  process, one coin H/L at a time, O/C float32, via heavy_slot tag oc_tpfill.

## Verdict

VERDICT: the engine's next-minute TP convention is NOT conservative by any
amount -- attaching the TP in the fill minute (close>=TP proxy) converts zero
non-TPs into TPs and leaves every yearly sum, win rate, worst day and maxDD
exactly unchanged (dSum5y = 0 on 22,312 paired rungs; 669 same-minute TPs all
TP at the same price one minute later under BASE), so the delay is a one-minute
booking shift only.
