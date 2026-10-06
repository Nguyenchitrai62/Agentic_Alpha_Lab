# BOT soakfix (bot_soakfix): 24h re-soak after B1/B2/B3

Same window/flags/harness as BOT_SOAK_20261006.md (2025-10-10 00:00 +24h,
4320 cycles, corr-size + dip-mult 1.7 + bear-book + dip-gross-cap 2.0 +
adopt-fresh + carry-f 0.25). Workdir
research/tournament/bot_soakfix/tmp/soakfix25 (tag soakfix25, heavy_slot).

## Invariants before -> after

| invariant | before (bot_soak2) | after (soakfix25) |
|---|---|---|
| protection on every open piece | FAIL 9491 ev, 35 pcs, 3417/4320 cyc | 181 ev, 2 pcs, 181/4320 cyc |
| cycle exceptions | FAIL 264 (ZeroDivision b_limit=0) | 0 |
| duplicate / unknown links | 0 | 0 |
| majors only | 0 | 0 |
| dip gross <= 2x sub equity / phase | 0 | 0 |
| carry hedged within 2 cycles | 0 (vacuous offline) | 0 (vacuous offline) |
| restart mid-replay | ok | ok (ledger_equal, no dup entries) |

## Fix evidence (testnet_soakfix25/actions.jsonl)

- B3: harness clamps buy_limit to a positive tick (test-only); mirror skips
  non-positive/non-finite limit/TP/stop as op=plan_reject (3349x, fires once
  XRP sigma caps at 0.25); desired() never raises out of Runner.cycle.
- B1: EVERY open book piece per (phase, symbol) gets stop+TP (side-flip
  orphans gone); add/reduce/close stays on the first piece only.
- B2: dust entries skipped (op=dust_skip 204x); unprotectable open dust
  closed same-cycle reduce-only market (op=dust_close 616x, taker fee).

## Residual (honest; exit-logic change forbidden here)

- All 181 late events (cyc 4139-4319, from 23:00) are ONE XRP book piece
  whose synthetic plan TP flips to exactly 0.0 mid-position: B3 rejects
  tp=0 and cancels stale TP/stop, B2b skips (TP unknown), divergence does
  not own it (sub still in position). A real engine never emits tp=0.

## Tests

- tests/test_bot_*.py (excl. smoke): 181 passed (incl. test_bot_soakfix 8).
- tests/test_bot_soak_smoke.py: 1 passed in 194s, 0 violations in first 2h.
