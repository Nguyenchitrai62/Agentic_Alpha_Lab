# OpenCode task oc_dipdaily - a SLOWER dip sleeve on the daily grid (big, rare flushes) next to G2
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_dipdaily/` and `tests/test_oc_dipdaily.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Heavy 1m work via heavy_slot (RAM tight: one coin at a time,
float32). Majors only. Long jobs: nohup + log under tmp/.

## Why
The 4h dip sleeve is the program's robust edge (positive in every pre-sample year, oc_presample2 / oc_presampleg2); a 1h sleeve failed
(oc_dipdip1h: small TPs vs 4-sigma stops, correlated with G2's sell-offs). A daily-grid sleeve catches larger, rarer capitulations with wider
TPs; it may be less correlated with the 4h sleeve's losses and has fewer, larger fills (fees matter less).
## Rules (pre-registered; exactly two variants; gate costs maker 0.0002, taker 0.00055, longs pay 0.0001 per 8h)
Bars: 1d, opening 00:00 UTC; sigma1d = std of the last 120 daily log returns (causal). At each daily open: resting limit bids at open x
(1 - k x sigma1d) for k in G2's ladder depths in sigma units, live minutes 5 .. 1439, maker fill only on a 1m trade-through, TP limit at
fill x (1 + G2's TP sigma multiple x sigma1d), stop market at G2's stop depth x sigma1d, exit by market at the next daily open; stop-first.
Rung size = G2's rung size_frac x 0.5 (D05) or x 0.25 (D025).
## Evaluation
Standalone per year (dev4 + post-release year scored ONCE, labelled) and on the clean pre-sample 2017-2020 (data of oc_presample2):
%/month on own capital, DD, trades, win rate, fee share; then combined with G2 on one account under the gross cap 2.0 (skip rungs that would
breach it): dev4 per year / mean / WORST / DD, robust pick among G2 / G2+D05 / G2+D025 on dev4 ONLY, 5y, full-path DD, daily return
correlation daily-sleeve vs G2. Vietnamese 3-line verdict.
