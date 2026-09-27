# v210 blind audit (read AGENTS.md (2026-09-27/28 user rules), .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v210_audit/` and `tests/test_v210_audit.py`. Use
relative paths without quoting. Do NOT open v210/ until part A is saved (`replication.json`). Base: your v205/v208 replications.

A: re-implement the discrete TRADE MODE independently (do not import `_trade_bar`; you may reuse engine_user's data
preparation, 1m cubes, fees, funding, governor and sleeve). Books, sizing target, sleeve and costs = v205. Per asset:
- flat + no resting order + |target| >= 0.05 at decision i (and the min-notional check) -> issue ONE limit order:
  price = open(i+1 bar minute 0) * (1 - side * max(0.001, 0.25 * sigma_4h[i])), size = |target| (weight), valid for bars
  i and i+1 (expires when i >= issue + 2), sigma_d of the issuing bar stored for the SL/TP.
- a NEW order may fill only from minute 5 of its first bar; a resting order from minute 0 of later bars; fill on a strict
  1m trade-through (low < price for longs, high > price for shorts) at the limit, maker 0.0002.
- a resting order is cancelled when the signal falls below 0.05 or reverses (a reversal may issue the opposite order in
  the same bar); no fill of a new order in the cancelling bar before minute 5.
- in a position: never resized; SL = entry -/+ 4 sigma_d, TP = entry +/- 8 sigma_d (issuing-bar sigma); scan minutes in
  order, stop first on ties, stop fills at min(SL, minute open) for longs (max for shorts), taker 0.00055; TP maker.
- T2: once the minute high (long) reaches entry*(1 + 2 sigma_d) the stop moves to entry*(1 + 0.001) from the NEXT minute;
  at a decision with |target| >= 0.05 against the position the stop moves to open*(1 - side*1.5*sigma_d[current bar]) if
  that is tighter and still on the right side of the open.
- T3: T2 plus at entry*(1 + side*4 sigma_d) sell 50% (maker) and move the stop to break-even.
Report for ref_v205, ref_v205_min5 (continuous mode, first fill minute 5), T1, T2, T3: dev4, worst first-four-year
monthly, gate DD, fills, stops, tps, orders issued/cancelled/expired, and dev trade statistics (win rate, avg win/loss).
Selection = robust criterion over T1..T3 only; most recent year ONLY for the selected row. Check causality: signals at
close i, orders act in bar i+1, no fill before minute 5 for new orders, stop moves effective from the next minute.
Save `replication.json`.
B: compare with `v210/v210_result.json` (return > 0.01pp/month, DD > 0.05pp, counts exact or explain). Write COMPARISON.md
with a PASS/FAIL verdict. Do not report the most recent year of non-selected rows. Do not edit leader files.
