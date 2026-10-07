# OpenCode task ops_bybitoptions - can the weekly short-straddle sleeve be executed on Bybit (bot and human)? Facts only.
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/ops_bybitoptions/` (probe JSONs, notes) and
`docs/opencode/BYBIT_OPTIONS_20261007.md`. Public, keyless GETs and public documentation pages only; no authenticated endpoint, no orders,
never read .env.

## Context
A research screen (research/tournament/oc_vrpstraddle, still under validation) sells one weekly ATM straddle per coin (BTC, ETH) every Friday
08:05 UTC, expiry next Friday 08:00, with a stop-loss (buy back when the loss reaches 1 x premium, checked hourly) and a take-profit (buy back at
30 % of the premium), alongside the G2 perp bot in ONE Bybit unified trading account (UTA). We need hard facts before any decision.

## Questions (answer each with a source URL + the probe file, or "not found")
1. Instruments: Bybit option underlyings (BTC, ETH, SOL, others?), settle coin (USDT / USDC), weekly expiries and their time (08:00 UTC?),
   strike grid near ATM, min order qty / qty step, tick size. Probe: GET https://api.bybit.com/v5/market/instruments-info?category=option&baseCoin=BTC
   (and ETH, SOL); GET https://api.bybit.com/v5/market/tickers?category=option&baseCoin=BTC (bid / ask / mark IV / underlying price) - from the
   tickers snapshot compute the bid-ask spread in vol points and in % of price for the ATM weekly call and put of BTC and ETH right now.
2. Fees (maker / taker / delivery, fee cap as % of premium) for VIP0, from Bybit's fee page.
3. Margin: can a UTA (regular margin, not portfolio margin) SELL options? Initial / maintenance margin formula for short options; is portfolio
   margin required or optional; minimum equity for portfolio margin; do short-option margins share collateral with USDT perps.
4. Order types for options: limit only or market too? Post-only? Reduce-only? Conditional / stop orders or TP/SL attachments for options
   (needed for the stop-loss rule)? Order expiry (GTC / IOC)? API endpoints (v5/order/create with category=option) and rate limits.
5. Testnet: are options available on Bybit testnet (api-testnet.bybit.com instruments-info category=option)?
6. Delivery: how settlement price is computed (TWAP window), whether positions are cash-settled automatically.
7. Human (MANUAL) workflow: can a human sell a straddle and attach a stop in the app/web? If not, what is the closest manual equivalent?

## Deliverable
`docs/opencode/BYBIT_OPTIONS_20261007.md` (Vietnamese + English terms, <= 70 lines): a facts table per question, the current BTC / ETH ATM
weekly spreads, and a feasibility verdict for (a) the bot, (b) a human, including anything that would change the research cost model
(e.g. wider spread than the screen's 3 % vol haircut, fee cap, margin).
