# oc_deribitstrike_back_BTC REPORT (CUR = BTC, BACKWARDS 2026-09 -> 2025-07)

## Method
Copied `fetch_strike.py` + `strike_lib.py` from
`research/tournament/oc_deribitstrike_BTC/` into this folder; `strike_lib.py`
byte-identical; `fetch_strike.py` differs ONLY in output folder
(`data/raw/deribit_strike_20261007_b/BTC/`) and month order (backwards from
2026-09, re-checking the forward folder before each month, stop at first
complete forward month). Same public endpoint
(history.deribit.com get_last_trades_by_currency_and_time), same paging
(start = last timestamp, de-dup on trade_id), same hourly per-instrument
aggregates, DTE <= 100, <= 5 req/s with backoff on 429, atomic write
(tmp + rename), same manifest schema (+ "direction": "backwards").
Never touched `data/raw/deribit_strike_20261007/` or forward processes.

## Months done (15 complete, 2025-07 .. 2026-09, 1138099 rows)

| month | rows |
|---|---|
| 2025-07 | 87306 |
| 2025-08 | 81228 |
| 2025-09 | 74501 |
| 2025-10 | 111140 |
| 2025-11 | 90969 |
| 2025-12 | 70673 |
| 2026-01 | 68700 |
| 2026-02 | 81466 |
| 2026-03 | 89006 |
| 2026-04 | 73591 |
| 2026-05 | 64682 |
| 2026-06 | 74529 |
| 2026-07 | 57392 |
| 2026-08 | 56146 |
| 2026-09 | 56770 |

Stopped at 2025-06: already complete in the forward folder (met_forward).
Manifest: `data/raw/deribit_strike_20261007_b/BTC/manifest.json`
(months, per-file rows + sha256, script sha256). Full log: `fetch_back.log`.

## Equality check (2025-06 sample, re-fetched into tmp/)
`tmp/BTC_2025-06.refetch.parquet`: forward rows = 78874, refetch rows = 78874,
identical column order (16 cols, same schema as forward fetcher).
Row-for-row `assert_frame_equal` (sorted by hour, instrument): PASS.

## Gaps / incidents
- 2025-09 full-month window failed twice transiently (RuntimeError after
  retries, shared API load with 3 sibling fetchers); succeeded on relaunch.
  Failed months leave no file (atomic write); cache holds only complete months.
- Remaining gap 2021-12 .. 2025-05 (excl. forward samples 2023-03, 2025-06)
  is left to the forward fetcher; a restart of this worker would stop again
  at 2025-06, so the leader should merge the two folders or redirect this
  worker past the samples if deeper backfill is wanted.
