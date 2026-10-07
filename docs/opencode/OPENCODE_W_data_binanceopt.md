# OpenCode task data_binanceopt - Binance options (EAPI) history: is there coin-specific implied vol for BNB / SOL / XRP?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `data/raw/binance_eapi_20261007/` and `research/tournament/data_binanceopt/`.
Public keyless GETs only (eapi.binance.com and data.binance.vision); polite rate; no downloads > 500 MB.

## Why
All implied-vol work used Deribit (BTC / ETH only); SOL / BNB / XRP dips used BTC's IV as a proxy. Binance lists options on all five
majors (docs/opencode/IDEAS_20261007c.md D3). Coin-specific IV could matter for the alt dips - IF enough history exists.

## Tasks
1. Probe: exchangeInfo (underlyings, listing dates if exposed), /eapi/v1/klines for one expired and one live symbol, /eapi/v1/mark,
   /eapi/v1/historicalTrades limits, and data.binance.vision option archives (check https://data.binance.vision/?prefix=data/option/ for
   daily BVOLIndex / EOHSummary files - list what exists, per underlying, first date).
2. If a daily or finer IV / volatility-index history exists for BNB / SOL / XRP (e.g. BVOLIndex or EOHSummary with mark IV), download it
   (respect size limit), build `<COIN>_iv_daily.parquet` (date, ATM-ish IV or index) + manifest (URLs, sha256, first/last date).
3. REPORT.md: coverage table per coin (first date, gaps), whether a walk-forward test is possible (needs >= 2021-09), and a comparison of the
   BTC / ETH series with Deribit DVOL on the overlap (correlation). Vietnamese 3-line verdict: usable or not.
