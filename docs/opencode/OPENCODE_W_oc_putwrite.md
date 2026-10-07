# OpenCode task oc_putwrite - weekly cash-secured put-writing sleeve (volatility risk premium), BTC + ETH
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_putwrite/` and `tests/test_oc_putwrite.py`.

## Why (new structural source, never tested here)
The dip ladder earns by providing liquidity in flushes. Selling out-of-the-money puts is the option-market version of the same service and is
paid up front (implied vol is usually above realised vol in crypto). Options were only used here as FEATURES (v150/v337, skew, DVOL), never
traded. Question: is a simple weekly put-write sleeve profitable after costs in every dev year, and does it add return per unit of DD on top
of G2 (or make a MANUAL product possible: one human action per week)?

## Data (as-of only)
- Implied vol: `data/raw/deribit_opt_20260926/{BTC,ETH}_options_4h.parquet` columns `bar` (4h bar start, UTC), `iv_otm_put`, `iv_otm_call`
  (volume-weighted traded IV of OTM puts / calls in that 4h bar, in vol points). A 4h bar's IV is known at bar start + 4h. Fallback when NaN:
  Deribit DVOL hourly (`data/raw/deribit_dvol_20261005`, BTC/ETH monthly JSON; an hourly candle is known at its close).
- Underlying: Binance USD-M 1m klines (find the files: data/raw/majors_intraday_20260924, btc_intraday_20260924, btc_1m_hidden_20260924,
  majors_1m_oos_20261006). Use the perp 1m close as the price.

## Rule (fixed before running)
- Cycle: every Friday. Entry at 08:05 UTC (after the 08:00 weekly expiry), expiry the next Friday 08:00 UTC (7 days).
- sigma_e = iv_otm_put of the last 4h bar whose close <= 08:05 (i.e. the bar starting 04:00) / 100; fallback DVOL / 100.
- S = 1m close of the minute 08:04. Strike K = S * exp(-z * sigma_e * sqrt(7/365)), rounded DOWN to the strike grid (BTC 1000, ETH 50).
- Premium received per unit = BlackScholes put (r = 0, q = 0, T = 7/365 at entry) with sigma_sell = 0.95 * sigma_e (bid-side haircut).
- Fee per side = min(0.0003 * S, 0.125 * option price) per unit (Deribit-style taker cap; conservative for Bybit). Settlement fee if ITM at expiry
  = min(0.00015 * S, 0.125 * intrinsic).
- Exits (user rule: every trade carries SL and TP):
  * TP: buy back when the mark <= 0.2 * premium; check on every 4h close with mark = BS put at sigma_mark = 1.05 * (latest known 4h
    iv_otm_put) / 100, remaining T; buy back at that mark + fee.
  * SL: buy back when the mark >= 3 * premium; check on every 1h close (same sigma_mark rule, latest KNOWN 4h IV at that hour), buy back at the
    mark computed with the 1h close price + fee.
  * Otherwise expire: payoff to the seller = -max(K - S_settle, 0), S_settle = mean of the 1m closes 07:30..07:59 Friday (Deribit delivery is
    a 30-minute index average).
- Sizing: cash-secured. Each coin gets half of the sleeve equity; units q = 0.5 * f * E / K (collateral q*K = 0.5 f E). Standalone f = 1.
- Variants (choose on dev4): P1 z = 1.0, P2 z = 1.5, P3 z = 2.0, P4 = put credit spread: P2's short put plus a LONG put of the same expiry
  at z = 3.0 (bought at BS with sigma_buy = 1.05 * sigma_e + 0.05 skew add-on, same fee rule; the long leg is closed together with the short
  leg on TP / SL at its own mark sigma 0.95 * latest IV + 0.05). Collateral for P4 = q * (K_short - K_long) (defined risk), q sized so that
  collateral = 0.5 f E per coin.
- Sensitivity rows for the chosen variant only (labelled): sigma_sell haircut 0.90; fees x2.

## Evaluation
1. Standalone per year (dev4; the most recent year once for the chosen variant): %/month geometric on sleeve equity, max DD (hourly marked),
   worst week, trades, TP / SL / expiry counts, win rate, mean premium yield per week.
2. Overlay on G2 (secondary, labelled): put-write on TOTAL equity with f = 0.25 and f = 0.5 (q sized on the current total equity at each entry),
   4-phase reset metric per year, yearly DD and full-path DD vs G2 alone, daily-P&L correlation with G2, and the worst 5 weeks of the combo with
   dates (are they the same crash weeks as the dip sleeve?). State that a Bybit UTA in portfolio margin would be needed (no margin model here).
3. MANUAL view (secondary): if a stored equity series of the honest MANUAL M5_human / book-only product exists (search
   research/tournament/oc_manualcarry, oc_manualtsmom, oc_manual*), overlay the chosen put-write the same way and report it; else write that it
   was not found.
4. Caveat paragraph: aggregated 4h OTM IV is not a strike-level quote (skew, spread, liquidity); results are a screen, a strike-level check
   needs data/raw/deribit_strike_20261007 (being fetched by another worker; do not wait for it).
