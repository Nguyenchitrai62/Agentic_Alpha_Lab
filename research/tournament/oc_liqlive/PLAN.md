# oc_liqlive — PLAN (written BEFORE computing results; DATA-PREP only, no outcome research)

## Task
DATA-PREP for the live liquidation collector (`backend/liquidations.py`, read-only).
Build `load_liq.py` that reads everything under `data/raw/liquidations_live/` into
tidy DataFrames, document layout / coverage / gaps / duplicates / clock skew,
then aggregate per 1m and per 4h bar per major. No outcome statistics against dip
fills (too little history). No 1m kline data, no fills/harness data is loaded.

## Hypothesis (data-prep, not trading)
The collector writes a usable going-forward liquidation stream for the 5 majors
(BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT) on 2 venues (binance, bybit) since
2026-10-04, plus per-venue connected-stream coverage files. Expected picture:
~2 days of data with at least two collector-level outages (a ~7.3 h gap on
2026-10-04 and a ~4.7 h gap on 2026-10-05 ~12:58→17:40 UTC when the backend was
down); Binance `forceOrder` yields at most one event/symbol/s (snapshot), Bybit
`allLiquidation` yields every liquidation batched per 500 ms, so per-venue
counts/notionals are not comparable. All numbers here describe the stream only.

## Exact causal / definitional rules (frozen)
- Input (read-only): `data/raw/liquidations_live/{binance,bybit}/<SYM>/YYYY-MM-DD.parquet`
  partitioned by **event_time UTC date**; normalised columns
  `venue, symbol, side∈{long,short}, raw_side, price, qty, notional_usd,
  event_time, recv_time` (ms UTC ints for times). `side=long` = liquidated long
  (forced SELL). `data/raw/liquidations_live/_coverage/{venue}/YYYY-MM-DD.parquet`
  with `venue, start_ms, end_ms` connected liquidation-stream intervals.
  `backend/liquidations.py` is never modified. `data/raw/topbook_live/` is out of
  scope (only its layout is noted, never loaded in this LIGHT job).
- Tidy loader (`load_liq.py`): `list_liq_files()`, `load_liquidations()` → one
  DataFrame with exactly the 9 normalised columns (dtypes: venue/symbol/side/
  raw_side str, price/qty/notional float64, event_time/recv_time int64), sorted by
  event_time; `load_coverage()` → `venue, start_ms, end_ms, file` sorted by
  start_ms. Files are read one at a time; peak RAM < 1 GB; one process; no GPU;
  no network; no `data/raw/*intraday*`, no `research/tournament/ext/*`, no
  harness/fills data.
- File layout doc: per file path, rows, event_time min/max (UTC), recv_time
  min/max. Coverage per day (per venue file: intervals, covered hours =
  sum(end-start)/3.6e6, span start→end) and per symbol (per venue/symbol/day:
  rows, total/max notional, event span, long share) — majors first
  (BTC, ETH, SOL, BNB, XRP). A minute with zero liquidations inside a covered
  interval = true zero; outside = no data.
- Gap: consecutive coverage intervals (same venue, sorted) with
  `next.start_ms - prev.end_ms > 60_000 ms`. Reported with UTC start/end and
  seconds. Cross-checked against the known backend outage
  2026-10-05 ~12:39–17:40 UTC (exact measured bounds reported, not assumed).
- Duplicates: exact key `(venue, symbol, event_time, raw_side, price, qty)`
  (the collector's dedupe key; venues give no trade id, so two identical
  liquidations in the same ms would collapse — counted as duplicates here too).
  Report: n duplicate keys beyond first occurrence, and whether the on-disk files
  themselves already contain any (re-read merge check).
- Clock skew: `lag_ms = recv_time - event_time` per row. Report per-venue median /
  p1 / p99 / share negative. Negative median on this host is the documented local
  clock running behind the exchange, not a schema break. Schema check: every row
  has side∈{long,short}, price>0, qty>0, notional≈price*qty, event_time>0.
- Aggregation (observed liquidations only, no prices): 1m bucket
  `m = floor(event_time to minute)`; 4h bucket `T = 00/04/08/12/16/20 UTC session
  containing m`. Per (bucket, venue, symbol): `n`, `n_long`, `n_short`,
  `long_notional`, `short_notional`, `total_notional`, `max_single`, plus
  `covered` (True iff the bucket overlaps any coverage interval of that venue).
  Bars with no liquidations but fully/partially covered are emitted with zeros
  (true zeros distinguishable from no-data); fully uncovered bars are omitted.
  Full tables → `aggregates_1m.parquet` + `aggregates_4h.parquet` in this folder;
  `results.json` carries the layout/coverage/gap/duplicate/skew tables, the full
  per-day-per-symbol table, the full 4h table, and the 1m summary (n buckets,
  top-10 by notional) — no dip-fill join, no forward returns, no PnL.
- Money: notional USD (≈ USDT). No fees/funding/PnL/backtest of any kind.

## Decision rule
No trading decision and no PROMISING verdict (explicitly not applicable: N≈2 days,
no outcome statistic is computed). Verdict line = stream readiness only:
READY (continuous coverage, schema conforms) / PATCHY (usable with gap masks) /
BROKEN (schema break or unexplainable loss), plus the single most notable
descriptive fact (largest coverage gap / thinnest symbol). The "what becomes
possible after N weeks" section is a forward plan, not a finding.

## Resource / leakage guardrails
- ONE process, RAM < 1 GB, no 1m kline files, no bulk downloads, no GPU.
- Only files WRITTEN: `research/tournament/oc_liqlive/` (PLAN.md, load_liq.py,
  results.json, aggregates_*.parquet, REPORT.md) + `tests/test_oc_liqlive.py`.
  No commits, no edits outside these paths, no `../Kronos`, no backend edits.
- Post-2025-09-24 boundary: the liquidation rows (collected since 2026-10-04) and
  their coverage files are the ONLY post-boundary data touched; they feed no
  model/threshold (there is none). All five walk-forward years remain research
  data; any future cascade-flag finding needs prospective validation.
- Repro: `load_liq.py` prints files/rows/gaps/dupes/skew and writes
  results.json + the two aggregate parquets; REPORT.md renders the same tables.
  Pure helpers (minute/4h bucketing, gap detection, aggregation, skew summary)
  are unit-tested offline with synthetic frames (no repo data in tests).
