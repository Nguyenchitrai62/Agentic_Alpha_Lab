# Audit COMPARISON — oc_eventstress (crash-week anatomy G2 + carry f=0.25)

Blind: `replicate_eventstress.py` (independent code from the
`compute_eventstress.py` header spec + frozen inputs only) wrote
`replication.json` BEFORE `oc_eventstress/REPORT.md` + `results.json` were
opened. Heavy run via `scripts/heavy_slot.py --tag audit_eventstress`
(slot_1, free RAM 6.92 GiB). Tolerances per assignment: 0.1 pp P&L,
0.2 pp DD, 1 day recovery.

## Gated metrics (replication vs results.json, 3 events)

| event (anchor UTC) | pnl_comb repl / REPORT | d | pnl_g2 repl / REPORT | d | dd_close repl / REPORT | d | dd_mark repl / REPORT | d | rec_days repl / REPORT | d | status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| LUNA 2022-05-11 | -6.05 / -6.05 | 0.00 | -6.03 / -6.03 | 0.00 | 9.66 / 9.66 | 0.00 | 10.38 / 10.38 | 0.00 | 35.79 / 35.79 | 0.00 | PASS |
| FTX 2022-11-08 | -2.47 / -2.47 | 0.00 | -2.47 / -2.47 | 0.00 | 8.41 / 8.41 | 0.00 | 9.78 / 9.78 | 0.00 | 13.83 / 13.83 | 0.00 | PASS |
| AUG24 2024-08-05 | +5.06 / +5.06 | 0.00 | +5.02 / +5.02 | 0.00 | 6.43 / 6.43 | 0.00 | 9.56 / 9.56 | 0.00 | 0.33 / 0.33 | 0.00 | PASS |

Max |dP&L| = 0.00 (tol 0.10), max |dDD| = 0.00 (tol 0.20),
max |dRec| = 0.00 d (tol 1 d). Trough hour and dip-gross hour exact all
three events (LUNA 2022-05-12 04:00, FTX trough 2022-11-10 08:00 /
dip at window open 2022-11-07 00:00, AUG24 trough 2024-08-05 07:00 /
dip 2024-08-05 01:00). v421==v422 identical: true. 1m coverage OK all
windows. REPORT.md owner table matches results.json (P&L/DD/rec to its
printed precision; dip rounded to 2dp: 0.45x / 0.77x / 0.54x).

## Non-gated note: dip-gross level (no P&L impact)

| event | dip repl | dip results.json | diff | hour match? |
|---|---|---|---|---|
| LUNA | 0.461 | 0.446 | +0.015 | exact |
| FTX | 0.790 | 0.767 | +0.023 | exact |
| AUG24 | 0.565 | 0.539 | +0.026 | exact |

Same hour, same shape, level +0.015..+0.026. Cause (methodology note, NOT
tuned post-hoc — replication.json left as written): the replication values
hourly marks with strict `<` (`searchsorted left - 1`, last bar strictly
before t), while `compute_eventstress.build_hourly_state` values them with
`<=` (`searchsorted right - 1`, last bar at or before U-1h). At an hourly
grid the two differ by exactly one hourly close when a mark lands on the
boundary (e.g. LUNA dip hour: strict picks BTC 28789.5, inclusive picks
28380.9). Both are causal (the inclusive bar closed 1h before valuation).
Carry MtM (strict) and all P&L/DD/recovery match to the digit either way.
Not gated by the assignment tolerances; recorded here for precision.

## Look-ahead / leakage checks (all pass)

- G2 legs: frozen stored runs only (`v421_runs.pkl`, v422 identity
  asserted); hourly via `v388.hourly` verbatim wiring (eq_min = stored
  1m-marked low); no refit, no threshold/margin choice from test years.
- Carry: frozen `oc_cashcarry` 33 trades; entries effective at
  entry_open+4h (`tc`), settlement locked to frozen `ret_alloc` from `ts`;
  MtM uses last-CLOSED hourly marks (0 before entry-close, frozen after
  settlement); notionals F x live A at entry (spanning fixed at grid start).
- Dip gross: `oc_kpi_g2` events/barsum rebuild, book flats zero, dip FIFO,
  Hedge gross; marks lagged 1h behind valuation (causal either convention).
- Recovery searched forward from anchor to grid end only; windows fixed
  anchor-24h..+7d; grid capped 2021-09-24 04:00..2026-09-23 12:00.
- 1m klines used for coverage confirmation only (no P&L input).
- Replication script never imports `oc_eventstress/compute_eventstress.py`
  and references no REPORT/results path (asserted in test).

## Verdict line

PASS — G2+carry P&L, 1m-marked DD and recovery replicate to the digit on
all three crash events (LUNA, FTX, 2024-08-05) within the 0.1 pp / 0.2 pp /
1-day gates; trough/dip hours exact; the only delta is a +0.015..+0.026
level shift on the non-gated dip-gross from a strict-vs-inclusive 1h mark
convention, same hour and shape.
