# oc_carryhurdle PLAN (frozen BEFORE any outcome — 2026-10-08)

Question: IDEAS11 #1 — quarterly cash-carry entered only if the (annualised)
basis covers H x the round-trip fees. Does a fee-hurdle add anything on top
of the frozen oc_cashcarry filter?

## Frozen inputs (read-only, no refit, no tuning)

- Carry pair list: `research/tournament/oc_cashcarry/results.json` — 33 entered
  trades (threshold 0.04/yr frozen), 13 skipped (basis < 0.04), 2 incomplete.
  Pair economics verbatim: fees spot 0.001/side + fut 0.00055 entry + 0.0002
  delivery; entry/settlement/MtM exactly as `analyze_cashcarry.py`.
- Overlay: `research/tournament/oc_carrycompound/analyze_carrycompound.py`
  verbatim — ONE compounding account A(t)=A(t-1)*(1+r_bot(t))+dU(t) (UTA: BOT
  sizes on TOTAL equity), carry notional N=f x A at each entry, held to
  delivery, causal hourly marks (last CLOSED hourly strictly before t, 0 before
  entry-close, locked to frozen ret_alloc at settlement), per-anchor-year reset
  to 1.0 (reset_metric.year_reset), spanning carry rebased to 0 at each anchor,
  full-path DD continuous from grid start with the v421 formula (max of
  marked/close DD). f=0.25 ONLY (plus f=0.0 reproduction gate).
- BOT legs: G2 Binance (`v421/v421_runs.pkl` strat R2B1D17BFG2, 4-phase mix)
  and G2 Bybit-S5 (`oc_k2bybit/tmp/runs_S5.pkl` REF, 4-phase mix; Bybit live
  from 2021-11-15 so y2021 is SHORT — labelled). No engine reruns, no 1m reads,
  hourly grid only (GRID0 2021-09-24 04:00 UTC .. g1 = v388.Y1+12h), CPU, small RAM.
- Gate costs inside stored BOT paths (inherited, not recomputed): maker 0.0002,
  taker 0.00055, longs pay 0.0001/8h, shorts 0. Limit fills trade-through only,
  no fill in first 5 min after a 4h close, stop-first in same 1m bar (inherited).

## Pre-registered variants (ONLY these three — H from the fee schedule, never tuned)

- Round-trip cost C = 2*0.001 (spot both sides) + 0.00055 (perp taker entry)
  + 0.0002 (perp maker delivery) = 0.00275 per alloc unit.
- REF = frozen oc_cashcarry (ann_basis >= 0.04), f=0.25 compounding overlay.
- V1 = frozen AND ann_basis >= H*C with H=2.0 → threshold T1 = 0.0055/yr (0.55%/yr).
- V2 = frozen AND ann_basis >= H*C with H=1.5 → threshold T2 = 0.004125/yr.
- Rule applied LITERALLY as written in the assignment (annualised basis number
  compared directly to H*C). Note frozen in advance: since 0.04 >> T1 > T2, the
  hurdle is strictly weaker than the frozen filter, so the EXPECTED outcome is
  zero additional skips (V1 = V2 = REF exactly) — this is the pre-registered
  "hurdle rarely binds" trap. No other threshold, no gross-cover or
  net-profit re-interpretation; any such re-interpretation would be a NEW
  disclosed extra row, not a replacement.
- Skipped-pair report: for V1/V2 list every pair skipped by the hurdle beyond
  frozen (expected: none) with its frozen realised ret_alloc; PLUS per-year the
  13 frozen-skipped contracts (recomputed verbatim by re-running the
  cashcarry entry rule to recover ann_basis/DTE) with their hypothetical
  realised P&L (gross − 0.00275) for context, labelled hypothetical.

## Reproduction gates (STOP and report if any fails)

1. f=0.0 Binance == v421_result G2 to the digit (5.41 / W 2.588 / DD 16.91 /
   full 16.82; per-year R/DD rows).
2. f=0.25 Binance REF == oc_carrycompound G2_f0.25 (5.634 / W 2.778 /
   DDmax 16.75 / full 16.66; per-year rows 2.778/10.86, 3.353/16.75,
   6.590/15.69, 10.956/8.20, recent 4.698/12.66).
3. Bybit S5 REF (f=0.25, same carry MtM, Bybit BOT leg) == oc_c2carry
   G2_carry_bybit_S5 (5.111 / W 2.321 / DDmax 17.95 / full 17.93).

## Selection + scoring protocol (frozen)

- Anchors: 2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24 = dev4 (selection
  universe); 2025-09-24..2026-09-23 = post-release year (scored ONCE, only for
  the robust pick and for REF, labelled).
- Robust criterion on dev4 ONLY: eligible iff DDmax(dev4) <= 20 and no losing
  dev year; prefer dev4 mean >= 5%/mo, then highest dev4 WORST-year R, ties →
  higher dev4 mean. Tie V1=V2 → pick V1 (larger H = more conservative, frozen
  tie-break). Dev4 stats are computed from the same reset-metric year rows
  (geometric mean of (1+R/100) over the 4 dev years, minus 1, x100).
- Post-release year is NEVER a selection input. It is computed once, after the
  pick is frozen on dev4, for PICK and REF on both venues.
- Leakage: carry entries use only 4h closes <= entry close (frozen); MtM uses
  last CLOSED hourly strictly before t; no fit here (hurdle constants from the
  fee schedule); fill timing inherited. Checks stated in REPORT.md.

## Deliverables (only these paths)

- `research/tournament/oc_carryhurdle/`: THIS PLAN.md, `analyze_carryhurdle.py`,
  `results.json`, `REPORT.md` (per-year R/DD tables both venues, skipped-pair
  tables with realised/hypothetical P&L, dev4/5y/full-path DD, robust pick,
  3-line Vietnamese verdict). `tests/test_oc_carryhurdle.py` (≥1 causality /
  truncation test + ≥1 hand-checked synthetic case). No other writes. No commits.
- Run: `.venv/Scripts/python.exe research/tournament/oc_carryhurdle/analyze_carryhurdle.py`
  (light, one process, hourly only). Test:
  `.venv/Scripts/python.exe -m pytest tests/test_oc_carryhurdle.py -q`.

(End of PLAN — frozen before outcomes.)
