# liqhist: Binance liquidation-history probe (2026-10-06)

Scope: PUBLIC Binance data archive only (`https://data.binance.vision`, S3 listing
`https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=...&delimiter=/`),
symbols BTCUSDT/ETHUSDT/SOLUSDT/BNBUSDT/XRPUSDT, prefixes
`data/futures/um/daily|monthly/liquidationSnapshot/<SYMBOL>/`. Polite rate 4 req/s,
resume-safe, CHECKSUM-verified downloader in `fetch_liqhist.py` (rerun:
`.venv/Scripts/python.exe research/data_fetch/liqhist/fetch_liqhist.py --probe-only`).
Memory note: our own collector (`backend/liquidations.py`) started 2026-10-04 only.

## 1. Archive probe: first/last date per symbol, gaps

| symbol | daily prefix | monthly prefix | files | first | last | gaps |
|---|---|---|---|---|---|---|
| BTCUSDT | `data/futures/um/daily/liquidationSnapshot/BTCUSDT/` | `.../monthly/...` | 0 / 0 | none | none | n/a (prefix empty) |
| ETHUSDT | `.../ETHUSDT/` | `.../monthly/...` | 0 / 0 | none | none | n/a |
| SOLUSDT | `.../SOLUSDT/` | `.../monthly/...` | 0 / 0 | none | none | n/a |
| BNBUSDT | `.../BNBUSDT/` | `.../monthly/...` | 0 / 0 | none | none | n/a |
| XRPUSDT | `.../XRPUSDT/` | `.../monthly/...` | 0 / 0 | none | none | n/a |

Every listing returns `IsTruncated=false` with zero `<Contents>` and zero
`<CommonPrefixes>` (raw XML saved under `data/raw/binance_liq_20261006/s3_listings/`,
`um_daily|monthly_liquidationSnapshot_<SYM>.xml`, 10 files). Parent prefixes
`data/futures/um/daily/liquidationSnapshot/` and `.../monthly/...` are likewise empty.
Full data-type listing proves the dataset is absent from USD-M: daily offers only
`aggTrades, bookDepth, bookTicker, indexPriceKlines, klines, markPriceKlines, metrics,
premiumIndexKlines, trades`; monthly offers only `aggTrades, bookTicker, fundingRate,
indexPriceKlines, klines, markPriceKlines, premiumIndexKlines, trades` (saved as
`control_um_daily|monthly_types.xml`). Positive control
`data/futures/um/daily/aggTrades/BTCUSDT/` returns 1000 keys/page, `IsTruncated=true`
(first file `BTCUSDT-aggTrades-2019-12-31.zip`), so the listing method works.
Alternative names `forceOrders/` and `liquidations/` under UM daily are also empty.

## 2. Download / conversion

Nothing to download (0 bytes, trivially <= 3 GB). No zips, no CHECKSUMs, no parquet
files written. The downloader path in `fetch_liqhist.py` (verify `.CHECKSUM` SHA256,
resume-safe skip of present-and-verified files, 3 GB cap, convert to one parquet per
symbol with columns `time` UTC-ms int64, `side` string, `price`/`qty`/`notional` float)
was therefore not exercised. Original-columns documentation: n/a (no UM files exist).

## 3. Coverage per year 2020-2026; daily count / notional distribution

All zeros: 0 files, 0 rows, 0 notional for every year 2020-2026 and every symbol.
No daily-count or notional distribution exists.

## 4. Context: what DOES exist (out of scope for USDT research)

- COIN-M `liquidationSnapshot` exists but is the wrong margin type and stops early:
  `data/futures/cm/daily/liquidationSnapshot/BTCUSD_PERP/` holds 472 daily zips from
  `...-2023-06-25.zip` to `...-2024-10-14.zip`; `ETHUSD_PERP/` 474 zips over the same
  span; CM monthly `liquidationSnapshot/` is empty. CM PERP/quarterly symbols exist for
  BTC/ETH/BNB/XRP/SOL analogues (118 prefixes), but none is a USDT-M contract.

## 5. Alternative free historical sources actually verified (HTTP 200, no key, no paid API)

1. Binance UM `metrics` daily archive on the same vision bucket (e.g.
   `data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2020-09-01.zip`, downloaded
   12 191 bytes 2026-10-06): columns `create_time,symbol,sum_open_interest,
   sum_open_interest_value,count_toptrader_long_short_ratio,
   sum_toptrader_long_short_ratio,count_long_short_ratio,
   sum_taker_long_short_vol_ratio` at 5 min steps from 2020-09-01. Proxy (positioning/
   OI/taker flow), NOT order-level liquidations.
2. Binance Futures DATA REST, free, no key (verified 200): `/futures/data/openInterestHist`,
   `/futures/data/globalLongShortAccountRatio` (sample 2026-10-06 OK). Recent window
   only (e.g. 5 m lookback ~30 days), no 2021-2026 full history.
3. Bybit v5 public market REST, free, no key (verified 200):
   `/v5/market/open-interest?category=linear&symbol=BTCUSDT`,
   `/v5/market/funding/history`, `/v5/market/recent-trade`. Recent window only.
4. OKX public REST reachable (verified 200): `/api/v5/public/instruments?instType=SWAP`
   returns `BTC-USDT-SWAP`; `/api/v5/public/liquidation-orders` endpoint exists (HTTP 200)
   but is recent-only by design (and param-sensitive, `code 51014` for bad `uly`).
   No multi-year liquidation history.
5. Own live collectors (forward-only, too short): `backend/liquidations.py` records
   Binance `fstream ... /market/stream?streams=@forceOrder` (one snapshot/sec/symbol) and
   Bybit `allLiquidation.{SYM}` into `data/raw/liquidations_live/` since 2026-10-04.
6. Binance REST `/fapi/v1/forceOrders` (recent liquidations): NOT usable unauthenticated
   from here (HTTP 401 on 2026-10-06) and recent-only by design in any case.
Paid/aggregator sources (CoinGlass, CryptoQuant, Glassnode, Tardis.dev historical
liquidation downloads) were deliberately NOT used (paid or commercial licence).

## Verdict

USABLE for 2021-2026 research: NO.
