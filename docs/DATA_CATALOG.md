# Kept data stores (local, gitignored under data/raw)

User rule (2026-09-29): download once, keep reusable derived data, never re-download. Raw archive zips are NOT kept (Binance perp
aggTrades ~122 GB, spot ~150 GB+); every fetcher keeps the derived tables below, which cover all feature definitions used so far.

| Store | Content | Coverage | Built by |
|---|---|---|---|
| `data/raw/aggflow_20260929_orders/{SYM}_flow_4h.parquet` | Binance USD-M perp taker ORDERS per 4h bar and size tier (<10k, 10k-100k, 100k-1M, >=1M USDT): buy / sell notional, counts | 2020-01 (SOL 2020-09) .. 2026-09-27 | `scripts/fetch_aggtrades_flow.py SYM --orders --out ...` |
| `data/raw/aggflow_20260929_orders_1m/{SYM}/*.parquet` | same orders per MINUTE in 8 log-size bins (lt1k .. ge3m): buy / sell notional, buy / sell order counts | same | same (1m store) |
| `data/raw/aggflow_20260928_orders/` | audited O1 4h table (identical to the 20260929 4h table) | same | `--orders` |
| `data/raw/aggflow_spot_20260929_orders/` + `_1m/` | Binance SPOT taker orders, 4h tiers + 1m store | BTC / ETH 2017-08, BNB 2017-11, XRP 2018-05, SOL 2020-08 .. 2026-09-28 (complete, 973 MB 1m store) | `--market spot --orders --out ...` |
| `data/raw/okxflow_20260929/` + `_1m/` | OKX USDT-perp taker orders (price x contracts x ctVal), 4h tiers + 1m store; days listing every trade twice (until ~2021-11) skipped | 2021-10-01 (BNB 2022-12-23) .. 2026-09-27 | `scripts/fetch_okx_flow.py` |
| `data/raw/bybitflow_20260929/` | Bybit perp taker orders, 4h tiers only | BTC 2020-03, others mid-2021 .. 2026-09 | `scripts/fetch_bybit_flow.py` |
| `data/raw/aggflow_20260928/`, `aggflow_spot_20260928/` | fill-level (per aggTrade) 4h tiers, perp and spot | 2020 / 2017 .. 2026-09 | default mode |
| `data/raw/binance_premium_20260928/` | Binance 1m premium-index klines + settled funding | 2020-01 .. 2026-09 | `scripts/fetch_binance_premium.py` |
| `data/raw/majors_intraday_20260924/`, `btc_intraday_20260924/` | 1m / 15m / 1h klines of the majors | 2020 .. 2026 | earlier fetchers |
| `data/raw/um_metrics_20260926/` | Binance metrics (open interest, long/short ratios, 5m) | BTC 2020-09, others 2021-12 .. | earlier fetcher |

Live extensions: `scripts/aggflow_live.py` appends live perp order flow (REST aggTrades) and the backend keeps a daily archive.
If a new feature needs information finer than the 1m store (single order sizes, sub-minute timing), the archive has to be streamed
again - extend the fetcher to keep the new aggregate at the same time.
