# OpenCode task oc_dip1h - a FASTER dip sleeve on 1h bars as an extra, possibly uncorrelated return source next to G2
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_dip1h/` and `tests/test_oc_dip1h.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Heavy 1m work via heavy_slot (RAM tight: load one coin at a time,
float32). Majors only.

## Why
All dip work so far uses the 4h decision grid (4 clocks). A 1h-grid sleeve with the same mechanism (resting limit bids below the bar open,
maker fills only on a 1m trade-through, take-profit limit, stop market, exit by market at the next bar open) has never been tested. If it
earns after fees with low correlation to G2, it adds return without new data.

## Rules (pre-registered; exactly two variants; costs = gate: maker 0.0002, taker 0.00055, longs pay 0.0001 per 8h)
Bars: 1h, opens on the hour, data from data/raw majors 1m (the same files the 4h replica uses). sigma1h = std of the last 720 hourly log
returns (causal). Ladder at each 1h open: rungs at open x (1 - k x sigma1h) for k in G2's dip-ladder depths (read them from the v421 / R2
config in sigma units; keep the same k values), rung size = G2's rung size_frac x 0.5 (H05) or x 0.25 (H025); orders live minutes 5..59 of
the bar (5-minute pipeline delay like the 4h rule); TP limit at the fill price x (1 + G2's TP sigma multiple x sigma1h); stop market at
G2's stop depth in sigma1h units; anything open at the next 1h open exits by market (taker). Stop-first when both are hit in one 1m bar.
## Evaluation
Standalone 1h sleeve per year (dev4 2021-09-24..2025-09-23 + post-release year scored ONCE, labelled): %/month on its own capital, DD,
trades, win rate, fee share of gross. Then a simple combined account: G2 hourly equity (v421 runs) with the 1h sleeve run on the same equity
under the cross-margin budget (gross <= 2 x equity incl. G2 exposure; skip rungs that would breach it): dev4 per year / mean / WORST / DD,
robust pick among G2 / G2+H05 / G2+H025 on dev4 ONLY, post-release year once, 5y, full-path DD, and the correlation of daily returns
1h-sleeve vs G2. Vietnamese 3-line verdict.
