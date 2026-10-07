# OpenCode task oc_deribitstrike_back_<CUR> - helper fetch of Deribit strike-level option trades, BACKWARDS from 2026-09
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. The extra message gives CUR = BTC or ETH. Write ONLY
`data/raw/deribit_strike_20261007_b/<CUR>/`, `research/tournament/oc_deribitstrike_back_<CUR>/`.

## Context
Workers oc_deribitstrike_btc / _eth are fetching the same dataset FORWARD from 2021-01 into data/raw/deribit_strike_20261007/<CUR>/ (about
7 months per hour per coin; do NOT touch that folder or those processes). You fetch BACKWARDS to halve the wall time: months 2026-09, 2026-08,
..., stopping when you reach a month that already exists (complete, listed in that folder's manifest.json or present as a parquet) in
data/raw/deribit_strike_20261007/<CUR>/ - re-check that folder before starting each month.

## Method
Copy the fetch + aggregation code of research/tournament/oc_deribitstrike_BTC/ (fetch_strike.py, strike_lib.py) or
research/tournament/oc_deribitstrike_ETH/ into your own folder unchanged except the month order and the output folder (read
docs/opencode/OPENCODE_W_oc_deribitstrike.md for the spec: public history.deribit.com get_last_trades_by_currency_and_time, paging with
start = last timestamp and de-dup on trade_id, hourly per-instrument aggregates, DTE <= 100, polite <= 5 requests / second for YOUR process,
back off on 429). Output: one parquet per month `<CUR>_YYYY-MM.parquet` with exactly the same schema as the forward fetcher's files, written
atomically (write to tmp then rename), plus manifest.json (months, rows, sha256, script sha256). Verify on one month that your output equals
the forward fetcher's file for the same month if one exists (2025-06 exists as a sample: re-fetch it into your tmp/ and compare row-for-row).
REPORT.md: months done, rows, the equality check, any gaps. Keep running until you meet the forward fetcher or run out of time; leave only
complete months.
