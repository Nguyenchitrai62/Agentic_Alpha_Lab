# OpenCode task data_hlfunding - Hyperliquid funding history for the 5 majors (new venue data) + first descriptive look
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `data/raw/hyperliquid_20261007/`, `research/tournament/data_hlfunding/`
and `tests/test_data_hlfunding.py`.

## Why
docs/opencode/IDEAS_20261007c.md D4 / B1: a second venue's funding never entered this program (closed funding work used Binance only).
Hyperliquid (on-chain perp venue, mainnet ~2023) publishes hourly funding per coin through a keyless public API.

## Fetch (public, keyless; be polite: <= 2 requests / second, back off on 429)
- `POST https://api.hyperliquid.xyz/info` with `{"type": "fundingHistory", "coin": "<BTC|ETH|SOL|BNB|XRP>", "startTime": <ms>, "endTime": <ms>}`
  paged by time (each response returns at most ~500 rows; advance startTime past the last row's time; de-duplicate on time).
  Range: from the first available row to the last complete UTC hour. Save per coin `HL_<COIN>_funding_1h.parquet` (time UTC, fundingRate,
  premium) + `manifest.json` (rows, first/last time, sha256, fetch window, endpoint). Note any coin not listed or listed late (BNB?).
- One snapshot of `{"type": "metaAndAssetCtxs"}` saved as JSON (for the record).

## Descriptive look (no trading rule, no outcomes beyond what is listed)
For the overlap with Binance funding (data/raw/binance_premium_20260928 settled funding, or data/raw/binance_usdm - find it): per coin and year,
the correlation of HL 8h-summed funding with Binance 8h funding, the mean / p90 of the spread (HL - Binance, per 8h), and the share of 8h
windows with opposite signs. Data before 2025-09-24 only for anything that touches price returns (do not compute any return statistic here).
REPORT.md: coverage table, the descriptive table, and whether the history is long enough for a walk-forward test (anchors 2023-09-24 and
2024-09-24 at best; state it). Vietnamese 3-line verdict on whether a pre-registered screen is worth running.
