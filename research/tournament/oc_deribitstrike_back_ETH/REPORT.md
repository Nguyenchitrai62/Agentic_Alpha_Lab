# oc_deribitstrike_back_ETH REPORT (CUR = ETH, backwards fetcher)

## Method
Code copied from `research/tournament/oc_deribitstrike_ETH/fetch_eth_strike.py`
(fetch_window paging with `start = last timestamp` + trade_id dedup,
per-day windows, hourly per-instrument aggregation, DTE <= 100) UNCHANGED
except: output folder `data/raw/deribit_strike_20261007_b/ETH/` and BACKWARD
month order (2026-09 down), re-checking the forward folder
`data/raw/deribit_strike_20261007/ETH/` before starting each month and stopping
when a complete month exists there. See `fetch_back_eth.py`. Public endpoint
`history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time`,
<= 5 req/s (0.22 s spacing), backoff on 429. Atomic writes (tmp + rename);
only complete months kept. Forward folder/processes never touched.

## Equality check (required by assignment)
Re-fetched 2025-06 into `tmp/ETH_2025-06.parquet` (`verify_equality.py`) and
compared row-for-row with the forward fetcher's
`data/raw/deribit_strike_20261007/ETH/ETH_2025-06.parquet`:
same shape (60158 rows, 17 cols, same column order), same (hour,
instrument_name) keys, all float columns bit-exact, all other columns equal.
Result: ROW-FOR-ROW EQUAL. Schema of every backward month also verified
identical to the forward schema.

## Months done (15 complete, 771088 rows total)
| month | rows | | month | rows | | month | rows |
|---|---|---|---|---|---|---|---|
| 2026-09 | 35785 | | 2026-06 | 36546 | | 2026-03 | 51532 |
| 2026-08 | 31378 | | 2026-05 | 36881 | | 2026-02 | 49406 |
| 2026-07 | 29858 | | 2026-04 | 45006 | | 2026-01 | 45946 |
| | | | | | | 2025-12 | 49413 |
| 2025-11 | 61766 | | 2025-10 | 78023 | | 2025-09 | 64422 |
| 2025-08 | 86280 | | 2025-07 | 68846 | | | |
Manifest: `data/raw/deribit_strike_20261007_b/ETH/manifest.json`
(months, rows, sha256 per file, script sha256). No gaps, no partial files.

## Meeting the forward fetcher
Next backward month 2025-06 already exists complete in the forward folder, so
the fetcher stopped there (`met_forward: ["2025-06"]`, nothing overwritten).
Forward contiguous run had reached 2023-01 at last check and is still moving
forward, so the remaining gap (2023-02 .. 2025-06) is the forward workers'
territory, not mine. No overlap between the two caches.

## Gaps / issues
None. All 15 months fetched on first attempt; no 429 blocks, no gaps.
Note: no pytest file was added because the assignment allows writes only to
the two folders above (no test file named); verification is the row-for-row
equality check plus the schema check above.
