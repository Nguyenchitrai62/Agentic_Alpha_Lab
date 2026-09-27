# ma-sr W11: intraday data download (read OPENCODE_VF_COMMON.md first; this is a data task)
Files you may write: `data/raw/btc_intraday_20260924/*`, `research/masr/fetch_intraday.py`.
1. BTCUSDT USD-M 15m klines 2019-09-08 .. latest closed bar via
   `agentic_alpha_lab.data.binance_usdm.fetch_klines("BTCUSDT", "15m", ...)` -> `klines_15m.parquet`.
2. BTCUSDT USD-M 1m klines 2019-09-08 .. 2026-09-23 from the public archive
   `https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-YYYY-MM.zip`
   (and daily zips `.../daily/klines/BTCUSDT/1m/BTCUSDT-1m-YYYY-MM-DD.zip` for the current
   partial month). Read zips in memory (zipfile+io), never write temp files outside the
   workspace. Some CSVs have a header row, some do not: handle both. Columns as in
   binance_usdm.KLINE_COLUMNS; convert times to UTC datetimes; save one parquet per year
   `klines_1m_YYYY.parquet`.
3. Validate: no duplicate open_time, count missing minutes per year, OHLC sanity; write
   `manifest.json` with row counts, first/last times, gaps, SHA-256 per file.
4. Cross-check: resample 1m -> 1h for 2024 and compare with `data/raw/ma_ribbon_20260924/klines_1h.parquet`
   (max abs diff of close); report in manifest.
Stop when done. No studies.
