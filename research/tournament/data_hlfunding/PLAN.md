# PLAN.md — data_hlfunding (Hyperliquid funding history, data-only)

Assignment: `docs/opencode/OPENCODE_W_data_hlfunding.md` (wave 2026-10-07).
This is a DATA task: no trading rule, no engine run, no return statistic.

## Pre-registered scope (fixed before any outcome)

1. FETCH (public, keyless, polite <= 2 req/s, backoff on 429):
   - Endpoint `POST https://api.hyperliquid.xyz/info`, `{"type":"fundingHistory",
     "coin":<BTC|ETH|SOL|BNB|XRP>, "startTime":<ms>, "endTime":<ms>}`.
   - Page by time (<= ~500 rows/response; `startTime = last_time + 1`; de-duplicate
     on `time`). Range: earliest available row per coin through the last complete
     UTC hour at fetch time. Expected earliest rows (probed, coverage only):
     BTC/ETH/SOL/BNB ~2023-05-12, XRP ~2023-06-18 (to be confirmed by the fetch).
   - Output `data/raw/hyperliquid_20261007/HL_<COIN>_funding_1h.parquet`
     columns `time` (UTC), `fundingRate` (float), `premium` (float),
     plus `manifest.json` (per-file rows/first/last/sha256, fetch window, endpoint).
   - One `metaAndAssetCtxs` snapshot JSON in the same data folder.
2. DESCRIPTIVE ONLY (no trading rule, no price/return input anywhere):
   - Overlap HL vs Binance settled funding (`data/raw/binance_premium_20260928`
     `*_funding.parquet`, 8h at 00/08/16 UTC). HL rows grouped into 8h windows by
     `floor(time, 8h)` and SUMMED per window (HL was 8h-cadence at launch in
     May-Jun 2023, hourly afterwards; summing handles both; windows with no HL
     row are skipped, never imputed).
   - Per coin x calendar year: n windows, Pearson correlation of HL-8h-sum vs
     Binance-8h rate, mean / p90 of spread (HL - Binance per 8h, in bps),
     share of windows with opposite signs (zero excluded from the sign test).
     Each year-row uses only that year's windows (no cross-year fit).
   - NO price data is loaded; NO return statistic is computed.
3. REPORT: coverage table (first/last/rows/cadence note per coin), descriptive
   table, walk-forward-usability statement (anchors 2023-09-24 and 2024-09-24
   at best), 3-line Vietnamese verdict on whether a pre-registered screen is
   worth running. `results.json` beside it.
4. TESTS (`tests/test_data_hlfunding.py`): 8h-window assignment/sum unit test on
   synthetic rows (incl. mixed 8h/hourly cadence), dedup-on-time test, manifest/
   parquet schema test (skipped if fetch not yet run), truncation test
   (shuffling/removing post-cutoff rows never changes pre-cutoff windows).

## Variants

None. Data-only task: nothing to select, no dev-year comparison, no engine run,
no G2 reproduction (no overlay is built).

## Leakage statement (fixed upfront)

- Funding rows are venue-published history timestamped per hour; no price,
  return, or forward information enters any step.
- The fetch aligns rows as-of their own timestamps only; the analysis never
  shifts or imputes across window boundaries.
- No statistic from 2025-09-24..2026-09-23 (or any test year) feeds any choice:
  there is no choice to feed (no thresholds, no quantiles, no model).
