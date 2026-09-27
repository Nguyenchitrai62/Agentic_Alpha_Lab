# xs W13: multi-coin USD-M universe data (read OPENCODE_VF_COMMON.md first; data task)
Files: `research/xs/fetch_universe.py`, `data/raw/xs_universe_20260924/*`.
1. From `https://fapi.binance.com/fapi/v1/exchangeInfo` list USDT-margined PERPETUAL
   contracts (status TRADING) and their onboardDate. Also try to include symbols that were
   delisted/settled (status != TRADING) if klines are still returned; record them.
2. Rank by 30-day quote volume from `https://fapi.binance.com/fapi/v1/ticker/24hr` (current,
   record that this ranking is as-of today and therefore survivorship-biased) and take the
   top 60 plus any delisted symbols found.
3. For each symbol download 4h and 1d klines from max(onboardDate, 2019-09-08) to the latest
   closed bar (`agentic_alpha_lab.data.binance_usdm.fetch_klines`) and full funding history
   (`/fapi/v1/fundingRate`, paginate, sleep 0.2s). Save `{SYM}_4h.parquet`, `{SYM}_1d.parquet`,
   `{SYM}_funding.parquet`.
4. `manifest.json`: per symbol onboardDate, status, first/last bar, rows, gaps, SHA-256,
   and the universe-selection caveat. Respect rate limits (sleep, retry with backoff).
Stop when done. No studies.
