# OpenCode task oc_deribitstrike_<CUR> - Deribit option trades kept at STRIKE level (hourly per instrument), 2021-01 .. now
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. You are ONE of two workers: the extra message tells you CUR = BTC or ETH.
Write ONLY `data/raw/deribit_strike_20261007/<CUR>/`, `research/tournament/oc_deribitstrike_<CUR>/` and
`tests/test_oc_deribitstrike_<CUR>.py` (use the lower-case currency in the test file name, e.g. test_oc_deribitstrike_btc.py).

## Why
All option work so far used 4h aggregates (data/raw/deribit_opt_20260926: OTM put / call IV averaged over strikes). Trading options
(put-writing, protective puts, straddles - studies running now) needs strike-level prices and IVs to check the aggregate-IV approximation.

## Source and method
- Public, no key: `https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time` with currency=CUR, kind=option,
  count=1000, sorting=asc, paging by timestamp exactly like research/mj/fetch_deribit_options_4h.py (read it; copy the paging/retry code into
  your folder; DO NOT edit research/mj). Fix one known risk: when paging with `start = last timestamp + 1`, trades sharing the last millisecond
  can be skipped - page with `start = last timestamp` and de-duplicate on `trade_id` instead.
- Keep per trade: trade_id, timestamp, instrument_name (parse expiry, strike, C/P), price (in coin), mark_price, iv, index_price, amount,
  direction, block_trade_id (if present), liquidation (if present).
- Aggregate per (UTC hour, instrument): n, sum amount, amount-weighted VWAP price (coin), VWAP price in USD (price * index), VWAP iv, min / max
  price, VWAP index_price, taker buy amount, taker sell amount, block-trade amount. Keep ONLY instruments with days-to-expiry <= 100 at trade time.
- Monthly resumable cache: `data/raw/deribit_strike_20261007/<CUR>/<CUR>_YYYY-MM.parquet` (one file per month; skip months already
  complete). Range 2021-01-01 .. the last complete UTC day. Be polite: <= 5 requests / second, back off on 429. If the run exceeds your time,
  leave the cache consistent (only complete months written) and report which months are done - the leader will restart you.
- `manifest.json` in the CUR folder: months, rows, sha256 per file, script sha256, fetch time window, endpoint.

## Checks (write results to REPORT.md)
1. For three sample months (2021-06, 2023-03, 2025-06): rebuild the 4h `iv_otm_put` of data/raw/deribit_opt_20260926 (definition in the
   fetcher docstring: notional-weighted mean IV of OTM puts, strike < index, expiry within 60 days) from your hourly file and compare
   (correlation, median abs diff in vol points). Small differences are expected (hour vs trade weighting); large ones must be explained.
2. Coverage: per month, trades, instruments, share of hours with at least one put trade with 5..9 days to expiry within 0.85..0.98 of index
   (the strikes a weekly put-write would use) and with 20..40 days to expiry within 0.70..0.90 (protective puts).
3. Test file: paging de-duplication on a synthetic page boundary with equal timestamps; instrument-name parsing; hourly aggregation on a hand case.
