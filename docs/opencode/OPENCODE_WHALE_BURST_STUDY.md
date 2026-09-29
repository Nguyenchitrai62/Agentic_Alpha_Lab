# Whale-burst reversal event study (dev years only) - bounded research task for OpenCode

Leader: Claude Code owns all modelling and evaluation decisions; you run ONE bounded, causal event study and report. Read AGENTS.md.
Write ONLY under `research/diagnostics/whale_burst/` (your script `whale_burst_study.py`, `results.csv`, `SUMMARY.md`) and
`tests/test_whale_burst_study.py`. Do not edit any other file, config, registry, ledger, ../Kronos or git state.

HARD DATA LIMIT: use only minutes with timestamp < 2025-09-24 00:00 UTC. Never load, compute or look at anything on/after that date
(it is the locked most recent year). Thresholds must be computed on minutes BEFORE 2021-09-24 (pre-anchor) only.

Data (already on disk, do not download):
- 1m taker-ORDER flow store: `data/raw/aggflow_20260929_orders_1m/{SYM}/*.parquet` (index = minute UTC, columns
  `{buy,sell,nb,ns}_{lt1k,1k_10k,10k_30k,30k_100k,100k_300k,300k_1m,1m_3m,ge3m}`: taker-buy / taker-sell notional USDT and order counts
  per order-size bin; files may overlap nothing but sum duplicates by minute to be safe).
- 1m klines (open/high/low/close): see `_closes` in `research/parallel/rounds/parallel-20260906-r2/v252/intrabar_flow.py` for the paths
  (BTC: data/raw/btc_intraday_20260924/klines_1m_20*.parquet; others: data/raw/majors_intraday_20260924/{SYM}_1m_20*.parquet); load
  open, high, low, close the same way.
Symbols: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT.

Definitions (fixed before looking at results):
- whale notional per minute W_sell = sell_1m_3m + sell_ge3m, W_buy = buy_1m_3m + buy_ge3m (orders >= 1M USDT).
- burst: a minute m with W_sell (or W_buy) >= threshold q, q = the 99.9th percentile of that side's per-minute W over all minutes of that
  symbol before 2021-09-24 where W > 0; also report q at the 99.5th and 99.97th percentiles as secondary rows. Keep only the first burst
  minute in any 60-minute window per symbol and side (no overlapping events).
- signal known at the END of minute m. Execution like a human/bot: an order can rest from minute m+2 on (1 minute latency).
- SELL burst -> LONG test: limit buy at close[m] * (1 - d), d in {0, 10, 30} bps, resting minutes m+2 .. m+31; fills only if a later 1m
  low trades THROUGH the limit (low < limit), fill price = limit, maker fee 0.02%. After the fill: stop-loss market at limit * (1 - 1.5%)
  (taker 0.055%, fill at min(stop, that minute's open) if gapped), take-profit limit at limit * (1 + t), t in {0.3%, 0.6%, 1.0%} (maker),
  else exit at market (taker) at the open of minute fill + H, H in {60, 240}. If stop and TP are touched in the same minute, assume the stop.
- BUY burst -> SHORT test: mirror image.
- Report per (side, q, d, t, H): events, fill rate, mean / median net return per filled trade (bps), win rate, t-stat, and the same by
  year (anchor years 2021-09-24..2022-09-23, ..., 2024-09-24..2025-09-23) and by symbol; a row is "stable" when the mean is > 0 in all four
  years. Baseline: the same trade rules started at RANDOM minutes (same count per symbol and year, fixed seed 7).
- Overlap with the existing dip ladder: for long tests report the share of fills where the fill price is already <= the 4h bar open *
  (1 - 2.5 * sigma_4h) (sigma_4h = std of the 4h open-to-open pct change over the previous 60 days, 360 bars); these fills are already
  traded by the pipeline. Report the non-overlapping subset separately.

Tests: synthetic cases for the fill rule (no fill on touch without trade-through, stop-first tie), the 60-minute de-duplication, and
that no minute >= 2025-09-24 is ever loaded (assert on the data frame max timestamp). Run
`.venv/Scripts/python.exe -m pytest tests/test_whale_burst_study.py -q`.
SUMMARY.md (<= 20 lines): the best stable rows vs the random baseline with costs, fill rates, the non-overlapping subset, and a plain
verdict (tradable edge or not). Stop when done.
