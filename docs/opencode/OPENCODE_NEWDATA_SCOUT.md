# New data C (tag scout): availability scan of other free historical sources (no bulk download)
For each source, determine with small test requests: endpoint, history start, granularity, coins covered (of BTC ETH SOL BNB XRP), rate limits,
licence / terms notes, and whether timestamps allow strict as-of joins. Sources: Hyperliquid public info API (fundingHistory, candles, user
liquidations / trades if any history), Deribit (DVOL already used - check BTC/ETH options 25-delta skew history, term structure, perpetual
funding history), OKX public (funding history, liquidation orders history, long/short account ratio history, margin lending ratio), Bybit public
(funding history, long-short ratio history, open interest history, public.bybit.com trading archives), Binance (top-trader long/short ratio,
taker long/short ratio - in data/futures/um/daily/metrics; options EOHSummary/BVOLIndex), Wikipedia pageviews API (daily, "Bitcoin", "Ethereum",
"XRP", "Solana", "BNB"), GDELT (crypto news tone, 15-min since 2015), blockchain.com charts API (BTC on-chain: hash rate, mempool, exchange
flows if any), mempool.space (fee history). Output research/diagnostics/newdata_scout/SOURCES.md: a table with the fields above and a ranked
shortlist (most promising for 4h dip reversion / 4h returns, with history >= 2021-06 and strict timestamps). Do NOT download more than a few MB
per source. tests/test_newdata_scout.py may only test your small parsing helpers.
