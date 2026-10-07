# OpenCode task oc_vrpstrangle - weekly short STRANGLE priced from traded OTM IV (second, independent VRP structure)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_vrpstrangle/` and `tests/test_oc_vrpstrangle.py`.
You may READ research/tournament/oc_vrpstraddle/PLAN.md and copy its mechanics (entry clock, BS, fees, SL / TP / settlement, overlay); do not
read its REPORT / results (avoid anchoring) and do not edit it.

## Why
oc_vrpstraddle: a weekly ATM short straddle priced at 0.97 x DVOL failed alone (DD 25.8) but as an overlay on G2 (f = 0.25) gave 6.41 %/month
with LOWER DD than G2. The main doubt is pricing (DVOL = 30-day ATM index, not a 7-day quote). A different structure priced from a different,
TRADED input gives independent evidence: a strangle sells OTM options whose IV we observe in data/raw/deribit_opt_20260926 (iv_otm_put,
iv_otm_call = notional-weighted traded IV of OTM puts / calls with expiry <= 60 days, per 4h bar, known at bar start + 4h).

## Rule (fixed before running; only the variants below)
- Every Friday 08:05 UTC, BTC and ETH: S = Binance perp 1m close 08:04; expiry next Friday 08:00 (T = (7 d - 5 min) / 365).
- sigma_p = iv_otm_put / 100, sigma_c = iv_otm_call / 100 of the last 4h bar with close <= 08:05 (bar starting 04:00); fallback DVOL / 100.
- Strikes: K_p = S exp(-z sigma_p sqrt(T)) rounded DOWN to the grid (BTC 1000, ETH 50); K_c = S exp(+z sigma_c sqrt(T)) rounded UP.
- Premium = BS put(K_p, 0.97 sigma_p) + BS call(K_c, 0.97 sigma_c). Marks / SL buy-back at 1.05 x the latest known sigma of each leg; TP
  marks at 1.0 x. Fees per leg per side min(0.0003 S, 0.125 price); settlement fee per ITM leg min(0.00015 S, 0.125 intrinsic).
- SL: at every 1h close, if mark loss <= -1.0 x premium received -> buy back both legs. TP: at 4h closes (TP first), if mark <= 0.3 x premium
  -> buy back (maker fee). Else settle vs the mean of 1m closes 07:30..07:59 on expiry day. No hedge.
- Size: q = 0.5 f E / S per coin (notional f x E in total), standalone f = 1.0.
- Variants: Z1 z = 0.5; Z2 z = 1.0. Standalone selection on dev4 with the robust criterion (fallback to the highest worst year if none
  qualifies, as oc_vrpstraddle did); most recent year once for the chosen one.

## Evaluation
- Standalone per dev year: %/month, hourly-marked DD, worst week, trades, TP / SL / expiry counts, mean premium % of S, mean (IV - realised).
- Overlay on G2 at f = 0.25 and 0.5 exactly with the A(t) = A(t-1)(1 + r_bot) + dSleeve convention of research/tournament/oc_carrycompound
  (the open option liability MUST be marked at every hourly point in the combined equity used for DD); reproduce G2 5.41 / 16.91 / 16.82 first.
- Daily-P&L correlation with G2 overall and in G2's worst 20 days; worst 5 combo weeks with dates.
- Caveat: aggregated OTM IV mixes strikes and tenors <= 60 d; no bid / ask.
