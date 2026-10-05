# oc_liq — PLAN (written BEFORE computing outcomes)

## Hypothesis
The live liquidation collector (`backend/liquidations.py`, running since 2026-10-04)
records a usable forced-liquidation stream for the 5 majors on Binance USD-M
(`forceOrder`, SELL = long liquidated / BUY = short liquidated, at most one event
per symbol per second) and Bybit (`allLiquidation`, Buy = long liquidated /
Sell = short liquidated, every liquidation batched every 500 ms). With ~1.5 days
of data this task is a DATA QUALITY + DESCRIPTIVE note only: too little history
for any statistical test. Expected picture: sparse, small-notional flow on
2026-10-04 (short collector uptime), denser flow on 2026-10-05; Binance counts
fewer but larger events per second-cap; no claim about predictive value.

## Exact definitions (frozen)
- Input liquidation rows: `data/raw/liquidations_live/{binance,bybit}/<SYM>/YYYY-MM-DD.parquet`
  with normalised columns `venue, symbol, side ∈ {long, short}, raw_side, price,
  qty, notional_usd, event_time, recv_time` (schema from `backend/liquidations.py`,
  which is READ-ONLY, never modified). `side=long` = liquidated long.
- Coverage: `data/raw/liquidations_live/_coverage/{venue}/YYYY-MM-DD.parquet`
  (`venue, start_ms, end_ms` connected intervals). A minute with zero liquidations
  inside a covered interval = true zero; outside = no data. Gap = consecutive
  intervals with `next.start_ms - prev.end_ms > 60 s`.
- Per-day/venue/coin table: row count, `sum(notional_usd)`, `mean/median/max`
  notional, long share. Size distribution: global + per-venue quantiles
  (p50/p90/p99/max) and log-binned histogram edges
  [0,100,1k,10k,100k,1M]; Binance vs Bybit compared ONLY as observed snapshots.
- Burst minute: UTC minute `m = floor(event_time to min)`; per-minute notional
  `N(m, venue, coin) = sum(notional_usd)` and count. "Largest liquidation minutes"
  = top 5 minutes by `N` over the whole sample (ties broken by count, then time).
  Side split (long vs short notional) reported per burst minute.
- 1m price path (those minutes ONLY): for each of the top 5 burst minutes, fetch
  Binance USD-M public `1m` klines for `[m-30, m+30]` of that coin (public REST,
  no auth, ~61 klines per burst; no bulk download). Path = closes rebased to the
  burst-minute open, plus high/low range of minute m. Bybit klines are NOT fetched
  (single-venue price path is enough for a descriptive note; Binance is the rung
  reference venue for the dip sleeve).
- Dip-ladder touch (that bar ONLY): frozen v183/v197 ladder from
  `scripts/dip_sleeve_forward.py` (READ-ONLY reference): for the 4h bar T
  containing burst minute m, `sigma_4h = std` of the 360 4h open-to-open returns
  ending at `T-4h`; rungs `L(k) = open(T)·(1-k·sigma)`, `k ∈ (2.5, 3.0, 3.5, 4.0)`.
  `open(T)` and sigma come from Binance USD-M public `4h` klines (one fetch of
  ~365 bars per involved coin, newest bar = T). Touch = `1m low of minute m`
  (from the ±30 window fetch) `< L(k)`; nearest-rung distance in sigma units
  `(open(T)-low_m)/(open(T)·sigma)` reported. No forward returns are computed.
- Money: notional in USD (≈ USDT, USDT-margined contracts). No PnL, no backtest.

## Decision rule
No trading decision. Verdict line = one sentence: stream HEALTHY / PATCHY /
BROKEN (based on coverage continuity + schema conformance) plus the single most
notable descriptive fact (e.g. largest burst minute and whether it touched a rung).
Anything beyond description is explicitly labelled "to measure once 3 months exist".

## Resource / leakage guardrails
- ONE process, RAM < 1.5 GB: liquidation files are < 2k rows total; klines are
  fetched per coin, one coin at a time, as float32, only the windows above
  (≤ 5×61 1m klines + ≤ 365 4h klines per involved coin). No local bulk 1m files
  are loaded. No GPU.
- Only files WRITTEN: `research/tournament/oc_liq/` (PLAN.md, scripts,
  results.json, REPORT.md) + `tests/test_oc_liq.py`. No commits, no edits outside.
- Recent-data boundary: liquidation rows (since 2026-10-04) and the minimal REST
  kline windows above are the ONLY post-2025-09-24 data touched; no statistic
  from them feeds any model/threshold (there is no model here). All years remain
  research data; findings need prospective validation.
- Repro: script prints venue/coin/day table, coverage gaps, quantiles, top-5
  minutes, per-burst price path + rung table into results.json; REPORT.md renders
  the same tables. Pure helpers (minute bucketing, sigma/rung math, coverage-gap
  detection) are unit-tested offline in tests/test_oc_liq.py with synthetic frames.
