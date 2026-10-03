# OpenCode assignment: Bybit USDT-perp 1m klines + Bybit-vs-Binance execution agreement

Why: the user trades Bybit USDT perpetual futures; every simulation fills on Binance 1m klines. Decide with data whether Bybit prices
differ enough to matter.

## Write scope (nothing else)
- `scripts/fetch_bybit_klines.py` (new fetcher), `tests/test_fetch_bybit_klines.py`
- data: `data/raw/bybit_linear_1m_20261004/` (parquet per symbol + `manifest.json`)
- study: `research/diagnostics/bybit_vs_binance/` (script, CSV/JSON, `SUMMARY.md`)
Do not edit other files. No credentials: public endpoints only. Never place orders.

## Part 1 - fetcher
- Bybit v5 public kline: `GET https://api.bybit.com/v5/market/kline?category=linear&symbol=<SYM>&interval=1&start=<ms>&end=<ms>&limit=1000`
  (result.list rows = [startTime ms, open, high, low, close, volume, turnover], NEWEST FIRST). Symbols BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT,
  XRPUSDT; range 2021-06-01 00:00 UTC (or the symbol's first available minute) .. the last CLOSED minute at run time.
- Be polite: <= 5 requests / second, retry with backoff on HTTP errors / retCode != 0, resumable (re-running fetches only what is
  missing), one parquet per symbol `<SYM>_1m.parquet` with columns open_time (UTC, ms int64), open, high, low, close, volume, turnover
  (float64), sorted, no duplicates.
- `manifest.json`: per symbol first/last open_time, rows, sha256 of the file, list of missing minute ranges (gaps) inside the range.
- Tests: parsing of a mocked response (newest-first order), de-duplication, resume logic (no network in tests).

## Part 2 - study (dev years only for any statistic about strategy outcomes; plain price comparisons may use the full range)
Binance 1m: BTC `data/raw/btc_intraday_20260924/klines_1m_20*.parquet`, others `data/raw/majors_intraday_20260924/<SYM>_1m_20*.parquet`.
a) Per symbol and calendar year: percentiles (1, 5, 50, 95, 99) of the minute close basis bybit/binance - 1 in bps, and of the
   high and low differences in bps; share of minutes where |basis| > 5 bps / 10 bps.
b) Execution agreement on the simulated orders of the deployed pipeline M5 (`artifacts/research/system_audit/events_v367.parquet`) and
   R2 (`events_v321.parquet`): for every book_fill and rung_fill (a buy limit at `price` filled at minute t on Binance: low < price):
   does Bybit trade through the same price (low_bybit < price) in the same minute t / within t..t+2 / at any minute until the order would
   expire? For book_stop / rung_sl (touch stops) does Bybit's low reach the stop in the same minute? For book_tp / rung_tp does
   Bybit's high exceed the price in the same minute? Report agreement rates per kind, pipeline and year, and the count of Binance fills
   that Bybit would NOT have filled at all.
c) `SUMMARY.md` (<= 20 lines): basis numbers, agreement rates, and a plain reading: is Bybit execution materially different?
Run tests with `.venv/Scripts/python.exe -m pytest tests/test_fetch_bybit_klines.py -q`. Stop when done.
