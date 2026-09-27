# vf W5: derivatives positioning (read OPENCODE_VF_COMMON.md first)
Files: `src/agentic_alpha_lab/patterns/positioning.py`, `tests/test_vf_positioning.py`,
`research/vf/positioning_study.py`, `artifacts/research/vf/positioning/*`,
`data/raw/metrics_ext_20260924/*`. Prefix `pos_`.
Existing 5m metrics: `data/processed/btc_derivatives_metrics_20260905_v1/metrics.parquet`
(create_time, sum_open_interest, sum_open_interest_value,
count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio,
count_long_short_ratio, sum_taker_long_short_vol_ratio), 2022-01-01..2026-03-22.
Extend to 2026-09-23 from the public Binance archive
`https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-YYYY-MM-DD.zip`
(no auth; skip missing days; record hashes in a manifest). Treat each metrics
row as available 5 minutes after create_time.
Also use funding via `common.load_funding(include_opened_year=True)` (as-of).
compute(): OI change over 1/6/24/72 bars-equivalent (log), OI z-score vs 30d,
OI/price divergence, top-trader and global long/short ratio levels and
z-scores, taker buy/sell ratio z-score, funding z-score vs 30d, funding x OI
interaction. NaN before 2022 is fine.
events(): crowding contrarian hypotheses (e.g. funding z > 2 and long/short
ratio z > 2 -> -1; mirror -> +1), OI surge with price up/down (continuation),
OI flush (large OI drop) -> +1. Event study on 1h/4h/1d.
