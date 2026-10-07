# OpenCode task oc_vrpstraddle - delta-hedged short ATM straddles (pure volatility risk premium), BTC + ETH
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_vrpstraddle/` and `tests/test_oc_vrpstraddle.py`.

## Why
Implied vol (Deribit DVOL, 30-day ATM) is usually above the vol that is later realised (the volatility risk premium). A delta-hedged short
straddle earns roughly 0.5 * Gamma * S^2 * (IV^2 - RV^2) dt and is market-neutral in direction, so it could diversify G2 (a long-rebound book).
Options were never traded in this program (only used as features, which diluted). This screen asks whether the premium survives realistic
costs and the crash weeks.

## Data (as-of only)
- DVOL hourly: `data/raw/deribit_dvol_20261005` (BTC/ETH monthly JSON; an hourly candle is known at its close). sigma = DVOL / 100.
- Sensitivity IV: 0.5 * (iv_otm_put + iv_otm_call) / 100 from `data/raw/deribit_opt_20260926/{BTC,ETH}_options_4h.parquet` (4h bar values known
  at bar start + 4h).
- Binance USD-M 1m klines for BTC / ETH (find the files).

## Rule (fixed before running)
- Entry every Friday 08:05 UTC: sell one ATM straddle (strike = S rounded to the grid, BTC 1000, ETH 50; S = 1m close 08:04), expiry next
  Friday 08:00 (V1, V2) or 4 weeks later (V3, entered every 4th Friday, non-overlapping). Premium = BS call + put (r = q = 0) at
  sigma_sell = 0.97 * latest known DVOL / 100. Option fee per leg per side min(0.0003 * S, 0.125 * leg price); settlement fee per ITM leg
  min(0.00015 * S, 0.125 * intrinsic). Size q = 0.5 * E / S units per coin (E = sleeve equity at entry; both coins => notional 1.0 x E).
- Delta hedge (V1, V3): at every 4h bar close of the standard grid (00/04/.. UTC) set the perp position to -q * BS delta (sigma_mark = latest
  known DVOL / 100, remaining T); hedge trades filled at the bar close price + 2 bps adverse, maker 0.0002 on the traded notional (a limit
  order resting from minute 5 would be the real implementation - say so). Long hedge pays 0.0001 per 8h settlement, short hedge receives nothing.
- V2 = V1 without any hedge (pure short straddle; control that shows what hedging buys).
- Risk exits (user rule: every position has SL + TP): SL = close everything when (straddle mark loss + hedge P&L) <= -1.0 x premium received,
  checked on every 1h close (buy back at BS with sigma = 1.05 * latest known DVOL / 100 + fees; hedge closed as taker). TP = buy back when the
  straddle mark <= 0.3 x premium (checked on 4h closes, maker). Otherwise settle at expiry vs the mean of the 1m closes 07:30..07:59.
- Sensitivity rows for the chosen variant (labelled): sigma from the OTM-IV average instead of DVOL; option fees x2; hedge slippage 5 bps.

## Evaluation
- Standalone per year (dev4; the most recent year once for the chosen variant): %/month on sleeve equity, max DD (hourly marked), worst week
  (dates), SL / TP / expiry counts, mean IV - realised vol gap at entries, P&L split option premium vs hedge.
- Overlay on G2 4-phase hourly equity at sleeve weight 0.25 and 0.5 of total equity (A(t) = A(t-1)(1 + r_bot) + dSleeve): reset metric,
  yearly and full-path DD vs G2, daily-P&L correlation with G2 (overall and in G2's worst 20 days).
- Caveat paragraph: DVOL is a 30-day index; a 7-day straddle has its own term-structure IV (usually lower in calm, higher in stress); no
  strike-level quotes (a strike-level check needs data/raw/deribit_strike_20261007, being fetched by another worker).
