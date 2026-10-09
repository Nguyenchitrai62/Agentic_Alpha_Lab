# oc_ideascan3 — probe notes (scan only, no backtests, no downloads > 50 MB)

Scripts: `probe_sources.py` (16 probes), `probe_retry.py` (12 corrected/extra probes).
Outputs: `probes/*.json` (one small truncated response each, total < 100 KB).
Run: `.venv/Scripts/python.exe research/tournament/oc_ideascan3/probe_sources.py`

## Verified (HTTP 200 with real payload, saved in probes/)

| Probe | Endpoint | What it proves |
|---|---|---|
| d1 | `GET www.deribit.com/api/v2/public/get_instruments?currency=BTC&kind=option&expired=true` | Full per-strike universe incl. expired, with `creation_timestamp`/`expiration_timestamp` (history start is enumerable) |
| d2b | `GET .../public/get_last_trades_by_instrument?instrument_name=BTC-PERPETUAL&count=3` | Per-instrument public trade history works (3 real trades, `has_more:true` → paginated backfill) |
| d3 | `GET api.bybit.com/v5/market/instruments-info?category=option&baseCoin=BTC&limit=10` | Bybit option universe with launch/delivery times, symbols `BTC-25JUN27-106000-C-USDT` |
| d4b | `GET .../v5/market/recent-trade?category=option&symbol=BTC-25JUN27-106000-C-USDT&limit=3` | Endpoint live (`retCode:0`); list empty for the far-dated illiquid strike → history pull must target near-term liquid strikes |
| d5 | `GET eapi.binance.com/eapi/v1/exchangeInfo` | Binance options universe: BTC/ETH/BNB/SOL/XRP underlyings all listed |
| d6/d7 | `POST api.hyperliquid.xyz/info` `{"type":"meta"}` / `{"type":"fundingHistory","coin":"BTC",...}` | Venue meta + hourly funding history sample (2140 bytes of real funding rows) |
| d17 | `POST .../info {"type":"metaAndAssetCtxs"}` | All-coin mids + funding + OI snapshot in one call |
| d8 | `GET api.international.coinbase.com/api/v1/instruments` | Coinbase Intl perps with live quote, `predicted_funding`, `open_interest` |
| d10 | `GET farside.co.uk/btc/` | Page live, title "Bitcoin ETF Flow (US$m)" → daily per-ETF flow table scrapable (flows from 2024-01-11) |
| d11 | `GET api.coingecko.com/api/v3/coins/markets?...ids=tether,usd-coin` | Live USDT/USDC supply + `market_cap_change_24h` (net-creation feed; `last_updated` today) |
| d12 | `GET api.binance.com/sapi/v1/system/status` | `{"status":0,"msg":"normal"}` → live maintenance gate (no history; forward-collect) |
| d13b | `GET www.okx.com/api/v5/public/instruments?instType=SWAP&uly=BTC-USDT` | `code:0`, BTC-USDT-SWAP spec incl. `listTime` 2019-11 |
| d14b | `GET api-pub.bitfinex.com/v2/ticker/tBTCUSD` | Venue reachable (98-byte quote array) |
| d18 | `GET api.bybit.com/v5/market/delivery-price?category=option&baseCoin=BTC&limit=3` | Endpoint live (`retCode:0`); empty list for this filter → needs per-symbol/expired queries |
| d20 | `GET query1.finance.yahoo.com/v8/finance/chart/BTC=F?interval=1d&range=5d` | CME BTC front-month OHLC, `firstTradeDate` 1513573200 (= 2017-12-18, CME launch) |

## Attempted, NOT verified (documented dead-ends — do not build on without re-probe)

- Deribit `get_last_block_trades_by_currency` (with and without `count`): HTTP 400 x2 (d2, d2c).
  Use per-instrument trade history + large-trade filter as proxy instead.
- OKX `liquidation-orders`: `uly=BTC-USDT` → 400 (d13); `uly=BTC-USDT-SWAP` → 200 with
  `code:51014 "Index doesn't exist"` (d13c). Endpoint exists; correct index enumeration TBD.
- Bitfinex `liquidations/hist/tBTCF0:USTF0` and `/tBTCUSD`: 404 x2 (d14, d14c). No verified liq archive.
- GDELT `doc` API (`artlist`, then `timelinevol` after 5 s backoff): 429 x2 (d15, d15b). Public but
  rate-limited from this host; usable only with caching/proxy. Tone family overlaps `oc_newinfo` anyway.
- Google Trends `trends/api/explore`: 429 (d16); no official keyless API → dropped.
- Stooq `btc.f` CSV: JS bot-check page from this host (d9) → use Yahoo `BTC=F` instead.
- Binance insurance fund `fapi/v1/insuranceFund?symbol=BTCUSDT`: 404 (d19a). No public REST endpoint found → dropped.

## History-span assessment (vs the 5 walk-forward anchors 2021-2025)

Full-span (>= 2021-09, all anchors): Deribit trades (BTC cont. since ~2019, confirm via
min `creation_timestamp`), Binance EAPI (BTC since Oct-2020; alt underlyings later, per-symbol),
OKX instruments (BTC-SWAP since 2019-11), Yahoo CME (since 2017-12-18).
Short-span (state the overlap, screen-only + paper): Bybit options (~2022+), Hyperliquid (~2023-02+),
Coinbase Intl (Dec-2023+), ETF flows (2024-01-11+), CoinGecko live feed (live only),
Binance sysstatus (live only, forward-collect).
