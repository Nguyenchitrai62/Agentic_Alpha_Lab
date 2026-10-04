# New data B (tag bookdepth): Binance USD-M order-book depth (bookDepth)
Source: https://data.binance.vision/data/futures/um/daily/bookDepth/{SYM}/{SYM}-bookDepth-YYYY-MM-DD.zip (from 2023-01-01; columns timestamp,
percentage, depth, notional: cumulative depth at +-1..5 % from mid, ~every 30-60 s). Fetch BTCUSDT ETHUSDT SOLUSDT BNBUSDT XRPUSDT
2023-01-01 .. 2025-09-30 (and the 30 alts present in fills_U.parquet if available, else majors only); store an aggregated 1-minute table
(last snapshot per minute: bid/ask notional at 1 %, 2 %, 5 %).
Features (define before results): bid/ask imbalance at 1 % / 2 %, total depth at 1 % relative to its trailing 7-day median, change of bid depth
over the last 15 / 60 minutes before the fill. Join strictly before the fill minute (last snapshot with timestamp < t_fill). The study window is
therefore 2023-01..2025-09-13 only - say so and report per year 2023 / 2024 / 2025.
