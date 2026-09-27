# mj W14: majors intraday data (read OPENCODE_VF_COMMON.md first; data task)
Majors: ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (BTC already exists in data/raw/btc_intraday_20260924).
Files: `research/mj/fetch_majors.py`, `data/raw/majors_intraday_20260924/*`.
1. USD-M 1m klines from each symbol's first month (ETH 2019-11, BNB 2020-02, XRP 2020-01,
   SOL 2020-09) to 2026-09-24 from the public archive
   `https://data.binance.vision/data/futures/um/monthly/klines/{SYM}/1m/{SYM}-1m-YYYY-MM.zip`
   plus daily zips for the current month; read zips in memory; header/no-header CSVs;
   one parquet per symbol-year `{SYM}_1m_{YYYY}.parquet`.
2. 15m, 1h klines via `agentic_alpha_lab.data.binance_usdm.fetch_klines` -> `{SYM}_15m.parquet`,
   `{SYM}_1h.parquet` (4h/1d/funding already in data/raw/xasset_20260924).
3. manifest.json: rows, first/last, missing minutes per year, SHA-256. Validate against
   existing 4h bars by resampling 1m (report max close diff). Stop when done.
