# OpenCode task oc_bookband - book turnover and fee drag; does a no-trade band on target changes help?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_bookband/` and `tests/test_oc_bookband.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Engine via heavy_slot (RAM tight: one engine job at a time).

## Why
The G2 book re-targets every 4h (four clocks); its skill lives at h = 1..18 bars (oc_bookichorizon, confirmed by oc_horizonfix) and the
book alone earns ~2.5 %/month with ~51 % episode win. Small target changes still cost fees (limit entries maker 0.0002, exits / closes
taker 0.00055) and add stop exposure. No program row has measured book turnover or tested a no-trade band.
## Part A (descriptive, no selection)
From the G2 engine (v421 R2B1D17BFG2, reproduce 5.41 / 16.91 / 16.82 first): per year book turnover (sum |delta weight|), fee drag of the book
leg, share of target changes smaller than 10 % / 25 % of the coin's typical weight, and the P&L of those small changes.
## Part B (exactly two pre-registered variants)
NB10 / NB25: a book target change is executed only if |new target - current position| > 10 % / 25 % of that coin's trailing-90d mean |target|
(computed causally), else the position is kept (protection and exits unchanged; direction flips are always executed). Engine dev4 per year /
mean / WORST / DD, robust pick among REF / NB10 / NB25 on dev4 ONLY, post-release year scored ONCE for the pick and REF, 5y, full-path DD,
fees saved, book win rate. Vietnamese 3-line verdict.
