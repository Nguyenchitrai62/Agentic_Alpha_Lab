# New data A (tag bitfinex): Bitfinex margin positioning
Source: https://api-pub.bitfinex.com/v2/stats1/{key}/hist?limit=10000&sort=1&start=..&end=.. with keys pos.size:1h:t{SYM}:long and
pos.size:1h:t{SYM}:short for BTCUSD, ETHUSD, XRPUSD, SOLUSD (BNB if it exists), plus funding-book keys if available (e.g. credits.size:1h:fUSD:tBTCUSD).
History starts ~2021-02 (BTC / XRP), 2021-05 (SOL). Rate limit: <= 1 request / 2 s; paginate by start time.
Features (examples, define before looking at results): long/short ratio, log changes of long and short sizes over 4h / 24h, z-scores vs a trailing
30-day window, BTC-level values as market-wide features for every coin. State the publication lag you use (assume a value stamped h is usable from
h + 1h unless proven otherwise).
