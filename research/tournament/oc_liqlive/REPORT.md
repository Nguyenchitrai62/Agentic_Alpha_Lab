# oc_liqlive — live liquidation stream: loader + data-prep report (no outcome research)

Sample: 1,866 liquidation rows, 2026-10-04 05:26 UTC → 2026-10-05 19:18 UTC
(~2 days — far too little history for any test; nothing here is joined to dip
fills). Methods frozen in PLAN.md before results were computed. Loader:
`research/tournament/oc_liqlive/load_liq.py` → `results.json` +
`aggregates_1m.parquet` (9,870 rows) + `aggregates_4h.parquet` (80 rows);
this file renders `results.json`.

## 1. File layout (`data/raw/liquidations_live/`, partitioned by event_time UTC date)

20 liquidation files (2 venues × 5 symbols × 2 days) + 4 coverage files
(`_coverage/{binance,bybit}/{2026-10-04,2026-10-05}.parquet`).
Rows per file (event_time order inside each file, schema
`venue, symbol, side∈{long,short}, raw_side, price, qty, notional_usd,
event_time, recv_time` conforms on all 1,866 rows; `notional≈price×qty` everywhere):

| file (venue/symbol/day) | rows |
|---|---|
| binance BTC 10-04 / 10-05 | 40 / 424 |
| binance ETH 10-04 / 10-05 | 47 / 317 |
| binance SOL 10-04 / 10-05 | 27 / 162 |
| binance BNB 10-04 / 10-05 | 6 / 102 |
| binance XRP 10-04 / 10-05 | 26 / 166 |
| bybit BTC 10-04 / 10-05 | 22 / 207 |
| bybit ETH 10-04 / 10-05 | 17 / 107 |
| bybit SOL 10-04 / 10-05 | 15 / 86 |
| bybit BNB 10-04 / 10-05 | 1 / 8 |
| bybit XRP 10-04 / 10-05 | 9 / 77 |

(`data/raw/topbook_live/` exists with the same venue/symbol/day layout at ~1 s
sampling; out of scope for this LIGHT job — never loaded here.)
Schema vocab: raw_side ∈ {BUY, SELL (binance), Buy, Sell (bybit)};
side=long means a LONG position was liquidated (forced SELL).

## 2. Coverage (per-venue connected-stream intervals) and gaps > 60 s

| venue | file | intervals | covered h | span (UTC) |
|---|---|---|---|---|
| binance | 10-04 | 237 | 3.94 | 05:25 → 16:38 |
| bybit | 10-04 | 237 | 3.94 | 05:25 → 16:38 |
| binance | 10-05 | 746 | 12.43 | 02:10 → 19:18 |
| bybit | 10-05 | 749 | 12.43 | 02:10 → 19:18 |

Gaps (both venues move together — collector-level outages, not venue drops):

| venue | gap start → end (UTC) | length |
|---|---|---|
| both | 10-04 05:28:05 → 05:29:33 | 87.5 s |
| both | 10-04 05:29:44 → 12:45:18 | 7.26 h |
| both | 10-04 16:38:20 → 10-05 02:10:14 | 9.53 h (overnight, collector off) |
| both | 10-05 12:58:14 → 17:40:28 | 4.70 h (backend down window) |

"Zero liquidations" is a true zero only inside covered intervals. 10-04 is
3.9 h of data spread over an 11.2 h span; any 10-04 rate is unreliable.

## 3. Rows per day / venue / coin, majors first (event_time UTC date)

| day | venue | coin | rows | notional $m | max single $k | long share |
|---|---|---|---|---|---|---|
| 10-04 | binance | BTC | 40 | 0.35 | 107.4 | 0.30 |
| 10-04 | binance | ETH | 47 | 5.88 | 5,632.7 | 0.49 |
| 10-04 | binance | SOL | 27 | 0.24 | 142.8 | 0.33 |
| 10-04 | binance | BNB | 6 | 0.00 | 3.2 | 0.50 |
| 10-04 | binance | XRP | 26 | 0.04 | 20.3 | 0.15 |
| 10-04 | bybit | BTC | 22 | 0.06 | 14.8 | 0.14 |
| 10-04 | bybit | ETH | 17 | 0.08 | 42.8 | 0.76 |
| 10-04 | bybit | SOL | 15 | 0.01 | 4.9 | 0.07 |
| 10-04 | bybit | BNB | 1 | 0.00 | 0.0 | 1.00 |
| 10-04 | bybit | XRP | 9 | 0.05 | 42.3 | 0.11 |
| 10-05 | binance | BTC | 424 | 9.54 | 1,501.7 | 0.49 |
| 10-05 | binance | ETH | 317 | 4.94 | 299.9 | 0.47 |
| 10-05 | binance | SOL | 162 | 1.00 | 183.3 | 0.56 |
| 10-05 | binance | BNB | 102 | 0.37 | 122.2 | 0.52 |
| 10-05 | binance | XRP | 166 | 0.71 | 79.7 | 0.71 |
| 10-05 | bybit | BTC | 207 | 2.23 | 256.1 | 0.57 |
| 10-05 | bybit | ETH | 107 | 0.76 | 125.1 | 0.63 |
| 10-05 | bybit | SOL | 86 | 0.32 | 30.1 | 0.59 |
| 10-05 | bybit | BNB | 8 | 0.09 | 42.6 | 0.25 |
| 10-05 | bybit | XRP | 77 | 0.30 | 46.9 | 0.73 |

Total ≈ $21.3m on 10-05 vs $6.7m on 10-04 (10-04 is gap-ridden, not a real
baseline). WARNING (unchanged): Binance `forceOrder` pushes at most ONE event
per symbol per second (a snapshot), Bybit `allLiquidation` batches every
liquidation per 500 ms — counts/notionals are NOT comparable across venues.
Bybit BNB is near-empty (9 rows in 2 days); flag before any per-symbol use.

## 4. Duplicates and clock skew (event vs receive time)

- Duplicates on the collector key
  (venue, symbol, event_time, raw_side, price, qty): **0** — the on-disk files
  are already clean ( venues supply no trade id, so two identical liquidations
  in the same ms would still collapse; not observed).
- Skew `lag = recv − event`: all-rows median +472 ms (p1 −650 ms, p99 +1,041 ms,
  31.4% negative). Per venue: binance median **+522 ms** (7.9% negative),
  bybit median **−246 ms** (87.8% negative) — the documented local clock running
  behind the exchange, larger on the Bybit stream; not a schema break. Skew is
  small vs the 1m/4h buckets below, but per-second sequencing across venues
  should carry ±1 s tolerance.

## 5. Aggregates per 1m and per 4h bar per major (observed liquidations only)

Panel semantics: every covered (venue, minute) × all 5 symbols is emitted
(zeros = true zeros); fully uncovered bars are omitted. `covered_frac` on 4h
bars = share of the 4 h window inside coverage.
`aggregates_1m.parquet`: 9,870 rows, 845 symbol-minutes (472 venue-minutes)
with ≥1 liquidation. `aggregates_4h.parquet`: 80 rows (8 session bars × 2
venues × 5 symbols). Columns:
`bucket_ms, bucket_utc, venue, symbol, n, n_long, n_short, long_notional,
short_notional, total_notional, max_single, covered[/covered_frac]`.
Top minutes by notional (stream description, NOT joined to fills):

| minute UTC | venue/coin | notional $k | n | long/short $k | max single $k |
|---|---|---|---|---|---|---|
| 10-04 15:04 | binance ETH | 5,641.7 | 4 | 0 / 5,642 | 5,632.7 |
| 10-05 08:31 | binance BTC | 1,601.3 | 7 | 78 / 1,524 | 1,501.7 |
| 10-05 04:32 | binance BTC | 820.0 | 23 | 820 / 0 | 273.3 |
| 10-05 18:28 | binance BTC | 638.6 | 5 | 0 / 639 | 631.8 |
| 10-05 06:53 | binance BTC | 626.1 | 14 | 0 / 626 | 431.2 |

4h-bar totals (n / $m, long+short; full per-symbol split in the parquet):

| 4h bar UTC | binance n / $m | bybit n / $m |
|---|---|---|
| 10-04 04 | 8 / 0.00 | 0 / 0.00 |
| 10-04 12 | 129 / 6.50 | 59 / 0.20 |
| 10-04 16 | 9 / 0.02 | 5 / 0.00 |
| 10-05 00 | 233 / 2.28 | 89 / 0.57 |
| 10-05 04 | 449 / 8.20 | 227 / 1.71 |
| 10-05 08 | 314 / 3.76 | 99 / 0.58 |
| 10-05 12 | 67 / 0.62 | 22 / 0.21 |
| 10-05 16 | 108 / 1.71 | 48 / 0.63 |

## 6. What becomes possible after N weeks (forward plan, not findings)

1. Liquidation-cascade flags for the dip ladder (the stated goal): fix a burst
   definition in advance (e.g. per-coin rolling quantile of per-minute notional
   inside covered time only), then a burst→fill event study against the frozen
   ladder. Needs dozens of burst episodes per coin: at ~2–5 large minutes/day
   observed so far, **4 weeks** is the minimum for a pilot definition +
   Binance-vs-Bybit snapshot-bias calibration, **12 weeks (~3 months)** for a
   ladder-conditioned study with long/short and funding splits and stable
   size-distribution monitoring (weekly p50/p99 as stream-health metrics).
2. Venue cross-check (2+ weeks): same-minute Binance-capped vs Bybit-full
   notionals to calibrate the 1-per-second snapshot bias before any joint use.
3. Top-of-book conditioning: extend the loader to `topbook_live` (spread/depth
   before vs after bursts) — descriptive after 2–4 weeks, no fills needed.
4. Coverage-SLO tracking from this loader (connected h/day, gap count; alert on
   >5 min gaps) so "no liquidation" stays distinguishable from "no data".
   Minimum history overall: **4 weeks** to start, **12 weeks** to conclude
   anything about cascades vs rungs; must also cover ≥1 stress week, which 2
   calm days cannot supply.

Verdict: stream PATCHY but loadable — schema conforms, zero duplicates, yet 2
multi-hour collector outages in 2 days (7.3 h on 10-04, 4.7 h on 10-05 12:58→17:40 UTC)
mean every rate must be gap-masked; N≈2 days supports prep/monitoring only.
