# Quarterly-futures basis fetcher (OpenCode worker task; leader owns all modelling)
Read AGENTS.md. You only build a DATA store + a causal feature table; do not evaluate returns, do not train models, do not edit leader files,
registry, ledgers, CONTINUOUS_RESEARCH.md, NEXT_AGENT.md, ../Kronos or git state. No credentials: public data.binance.vision archive only.
Write scope: `scripts/fetch_quarterly_basis.py`, `data/raw/qbasis_20261003/` (data + manifest.json with source URLs, sha256 per file, row counts,
first / last open time), `artifacts/research/engine_real/qbasis_features_4h.parquet`, `tests/test_qbasis_fetch.py`.

1. Download 1h klines of Binance USD-M DELIVERY contracts for BTC and ETH (symbols like BTCUSDT_210326, BTCUSDT_210625, ...; list them from the
   archive index https://data.binance.vision/?prefix=data/futures/um/monthly/klines/ - every BTCUSDT_YYMMDD / ETHUSDT_YYMMDD folder, interval 1h,
   monthly zips; fall back to daily zips for the current month) and Binance COIN-M delivery contracts BTCUSD_YYMMDD, ETHUSD_YYMMDD, BNBUSD_YYMMDD,
   XRPUSD_YYMMDD, SOLUSD_YYMMDD where they exist (prefix data/futures/cm/monthly/klines/). Keep the raw zips' parsed parquet (open_time,
   open, high, low, close, volume) per contract. Download once; skip files already present (user rule: never re-download).
2. Spot / perp reference: use the existing perp 1m/4h opens the engine uses (data/raw/majors_intraday_20260924 and data/raw/btc_intraday_20260924,
   1m klines; take the close of the last 1m bar of each hour) - do not download them again.
3. For each coin and each hour t (UTC, close time = t + 1h), FRONT contract = the delivery contract with the nearest expiry that is > 7 days after
   t (roll 7 days before expiry; the expiry time is 08:00 UTC on the date in the symbol); NEXT = the following one. Features at the hour close, using
   only bars that closed at or before t + 1h:
     qb_front = ln(F_front close / perp close) * 365 / days_to_expiry      (annualised front basis; USD-M if available else COIN-M)
     qb_slope = annualised next basis - annualised front basis
     qb_chg24 = qb_front - qb_front 24 h earlier
   Then aggregate to the engine's 4h bars (value at the 4h close = the last hourly value inside that bar). NaN where no contract exists.
   Output a long table (open_time of the 4h bar, close_time, sym in BTCUSDT/ETHUSDT/BNBUSDT/XRPUSDT/SOLUSDT, the three features, source um/cm).
4. Tests: synthetic roll / expiry cases, causality (a feature at a 4h close never uses an hourly bar closing after it; shuffling future rows does
   not change past values), the roll rule, NaN handling. Run `.venv/Scripts/python.exe -m pytest tests/test_qbasis_fetch.py -q`.
5. SUMMARY: append a 10-line section to `data/raw/qbasis_20261003/manifest.json` ("summary": coverage per coin, first date with a contract,
   number of rolls, share of NaN). Stop when done.
