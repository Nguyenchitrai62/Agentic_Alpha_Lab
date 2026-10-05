# oc_topbook — PLAN (written BEFORE computing results; DATA-PREP only, no outcome research)

## Task
DATA-PREP for the live top-of-book collector (`backend/liquidations.py`, read-only).
Build `load_topbook.py` that reads everything under `data/raw/topbook_live/` into
tidy per-second frames, documents layout / schema / coverage / gaps / quality,
then aggregates per 1m and per 4h bar per major. No outcome statistics against dip
fills, no fills/harness data is loaded, no 1m kline data.

## Hypothesis (data-prep, not trading)
The collector writes a usable going-forward top-of-book stream for the 5 majors
(BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT) on 2 venues (binance, bybit) since
2026-10-04, sampled ~1/s from Binance `<sym>@bookTicker` and Bybit `tickers.{SYM}`
bid1/ask1. Expected picture: ~2 days of data (~590k rows: ~14172/day-file on
2026-10-04, ~44900 on 2026-10-05) with the same collector-level outages as
oc_liqlive (a ~7.3 h gap on 2026-10-04 and a ~4.7 h gap on 2026-10-05
~12:58→17:40 UTC when the backend was down, plus an ~88 s blip on 10-04
05:28 UTC). Spreads on majors should be sub-5 bps almost always (BTC/ETH ~0.01–0.04
bps on both venues; Bybit BNB notably wider ~1.27 bps vs Binance ~0.13 bps);
fraction of seconds with spread > 5 bps near zero. All numbers here describe the
stream only.

## Exact causal / definitional rules (frozen)
- Input (read-only): `data/raw/topbook_live/{binance,bybit}/<SYM>/YYYY-MM-DD.parquet`
  partitioned by **sample_time UTC date**; normalised columns
  `venue, symbol, sample_time, quote_time, bid, bid_qty, ask, ask_qty, recv_time`
  (ms UTC ints for times, floats for prices/qtys; see `BOOK_COLUMNS`/`BOOK_KEY` in
  `backend/liquidations.py`, never modified). There is NO `_coverage` dir under
  `topbook_live/`; collector uptime is proxied by
  `data/raw/liquidations_live/_coverage/{venue}/YYYY-MM-DD.parquet`
  (`venue, start_ms, end_ms` connected-stream intervals, same process) PLUS own
  `sample_time` gap detection below. Day files are keyed by sample_time date, so a
  late-evening sample never leaks into the wrong day file beyond its own date label.
- Tidy loader (`load_topbook.py`): `list_book_files()`, `load_topbook()` reads one
  venue/symbol/day file at a time and returns one DataFrame with exactly the 9
  normalised columns (dtypes: venue/symbol str, times int64, bid/bid_qty/ask/ask_qty
  float64), sorted by sample_time; peak RAM < 1 GB; one process; no GPU; no network;
  no `data/raw/*intraday*`, no `research/tournament/ext/*`, no harness/fills data,
  no `data/raw/liquidations_live/{binance,bybit}/*` event files (only `_coverage`).
- Derived per-row (pure, point-in-time, no lookahead): `mid = (bid+ask)/2`,
  `spread_bps = (ask-bid)/mid*1e4`, `bid_usd = bid*bid_qty`, `ask_usd = ask*ask_qty`.
  Invalid rows (ask<=bid, bid<=0, ask<=0, qty<=0, NaN) are counted and EXCLUDED from
  aggregates (reported as quality table, never silently kept).
- File layout doc: per file path, rows, sample_time min/max (UTC), median sampling
  dt, quote-sample lag (`quote_time - sample_time`) median/p99. Coverage: reuse the
  oc_liqlive gap list method — consecutive coverage intervals (same venue, sorted)
  with `next.start_ms - prev.end_ms > 60_000 ms` reported with UTC start/end and
  seconds; cross-check own topbook `sample_time` diffs > 60 s per venue (all symbols
  share the collector clock, so per-venue gap sets must match across symbols and
  match the liquidation-coverage gaps within seconds).
- Duplicates: collector key `(venue, symbol, sample_time)` (`BOOK_KEY`); report n
  duplicate keys beyond first occurrence and whether on-disk files already contain
  any. Clock: `quote-sample lag` and `recv-sample lag (recv_time - sample_time)`
  per venue median/p1/p99/share-negative (negative = local clock behind exchange,
  documented on this host, not a schema break).
- Aggregation (valid rows only): 1m bucket `m = floor(sample_time to minute)`; 4h
  bucket `T = 00/04/08/12/16/20 UTC session containing m`. Per (bucket, venue,
  symbol): `n` (seconds), `spread_mean_bps`, `spread_max_bps`, `bid_usd_mean`,
  `ask_usd_mean`, `frac_wide` (share of rows with spread > 5 bps), plus
  `covered_frac` on 4h bars (share of the 4 h window inside liquidation-coverage
  intervals of that venue; 1m rows carry `covered` bool = bucket overlaps any
  coverage interval). Bars fully outside coverage are omitted (no data, not zero).
  Full tables → `aggregates_1m.parquet` + `aggregates_4h.parquet` in this folder;
  `results.json` carries layout/schema/duplicate/lag tables, coverage gaps, the
  per-day-per-symbol spread/size table, the Binance-vs-Bybit spread comparison per
  coin, the full 4h table, and the 1m summary — no dip-fill join, no forward
  returns, no PnL.
- Venue comparison: per coin, covered-window pooled mean/median/p99 spread on
  binance vs bybit + ratio (bybit/binance of means) and frac_wide each side.
- Money: sizes in USD (≈ USDT). No fees/funding/PnL/backtest of any kind.

## Decision rule
No trading decision and no PROMISING verdict (explicitly not applicable: N≈2 days,
no outcome statistic is computed; the default >=4/5-years sign + LOO rule needs
anchor years that do not exist here). Verdict line = stream readiness only:
READY (continuous coverage, schema conforms) / PATCHY (usable with gap masks) /
BROKEN (schema break or unexplainable loss), plus the single most notable
descriptive fact (largest coverage gap / widest coin-venue). The "what live
execution research this enables" section is a forward plan, not a finding.

## Resource / leakage guardrails
- ONE process, RAM < 1 GB, no 1m kline files, no bulk downloads, no GPU.
- Only files WRITTEN: `research/tournament/oc_topbook/` (PLAN.md, load_topbook.py,
  results.json, aggregates_*.parquet, REPORT.md) + `tests/test_oc_topbook.py`.
  No commits, no edits outside these paths, no `../Kronos`, no backend edits.
- Post-2025-09-24 boundary: the topbook rows (collected since 2026-10-04) and the
  liquidation coverage files are the ONLY post-boundary data touched; they feed no
  model/threshold (there is none). All five walk-forward years remain research
  data; any future fill-realism finding needs prospective validation.
- Repro: `load_topbook.py` prints files/rows/gaps/dupes/spreads and writes
  results.json + the two aggregate parquets; REPORT.md renders the same tables.
  Pure helpers (spread/sizes, minute/4h bucketing, gap detection, aggregation,
  lag summary) are unit-tested offline with synthetic frames (no repo data in tests).
