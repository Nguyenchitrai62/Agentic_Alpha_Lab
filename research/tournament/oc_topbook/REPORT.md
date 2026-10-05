# oc_topbook — live top-of-book stream: loader + data-prep report (no outcome research)

Sample: 591,204 top-of-book rows, 2026-10-04 05:25 UTC → 2026-10-05 19:22 UTC
(~2 days — far too little history for any test; nothing here is joined to dip
fills). Methods frozen in PLAN.md before results were computed. Loader:
`research/tournament/oc_topbook/load_topbook.py` → `results.json` +
`aggregates_1m.parquet` (9,910 rows) + `aggregates_4h.parquet` (80 rows);
this file renders `results.json`. The stream was still running while the loader
ran, so file row counts grew slightly vs the PLAN estimate; the loader reports
whatever was on disk at run time.

## 1. File layout (`data/raw/topbook_live/`, partitioned by sample_time UTC date)

20 topbook files (2 venues × 5 symbols × 2 days), ~1 s sampling (median dt
1,000 ms in every file). Schema on all 591,204 rows:
`venue, symbol, sample_time, quote_time, bid, bid_qty, ask, ask_qty, recv_time`
(conforms; zero invalid rows: no ask<=bid, no non-positive/NaN prices/qtys).
Source: `backend/liquidations.py` sampling the latest best bid/ask once per
`book_sample_s` (default 1 s) from Binance `<sym>@bookTicker` and Bybit
`tickers.{SYM}` bid1/ask1. There is NO `_coverage` dir under `topbook_live/`;
uptime is proxied by `data/raw/liquidations_live/_coverage/` (same process).
Rows per file:

| file (venue/symbol/day) | rows |
|---|---|
| binance BTC/ETH/SOL/BNB/XRP 10-04 | 14,172 each |
| binance BTC/ETH/SOL/BNB/XRP 10-05 | 44,983 each |
| bybit BTC 10-04 / 10-05 | 14,172 / 44,925 |
| bybit ETH 10-04 / 10-05 | 14,172 / 44,906 |
| bybit SOL 10-04 / 10-05 | 14,172 / 44,923 |
| bybit BNB 10-04 / 10-05 | 14,169 / 44,896 (3 rows short on 10-04) |
| bybit XRP 10-04 / 10-05 | 14,172 / 44,922 |

Derived per row (point-in-time, no lookahead): `spread_bps=(ask-bid)/mid*1e4`,
`bid_usd=bid*bid_qty`, `ask_usd=ask*ask_qty`; `wide = spread > 5 bps`.

## 2. Coverage (liquidation-stream proxy, same collector) and own sample gaps > 60 s

| venue | day file | intervals | covered h | span (UTC) |
|---|---|---|---|---|
| binance | 10-04 | 237 | 3.94 | 05:25 → 16:38 |
| bybit | 10-04 | 237 | 3.94 | 05:25 → 16:38 |
| binance | 10-05 | 746 | 12.43 | 02:10 → 19:18 |
| bybit | 10-05 | 749 | 12.43 | 02:10 → 19:18 |

Proxy gaps (both venues move together — collector-level outages, not venue drops):

| gap start → end (UTC) | length |
|---|---|
| 10-04 05:28:05 → 05:29:33 | 87.5 s |
| 10-04 05:29:44 → 12:45:18 | 7.26 h |
| 10-04 16:38:20 → 10-05 02:10:14 | 9.53 h (overnight, collector off) |
| 10-05 12:58:14 → 17:40:28 | 4.70 h (backend down window) |

Own `sample_time` gaps > 60 s: 30 = every (venue, symbol) file shows the same 3
gaps (2 on 10-04: ~89 s + ~26,134 s; 1 on 10-05: ~16,934 s), matching the proxy
gap bounds within ~1 s. The overnight gap spans the day-file boundary so it
appears in neither day file (expected). "Zero rows" is a true zero only inside
covered intervals. 10-04 is 3.9 h of data spread over an 11.2 h span; any 10-04
rate is unreliable.

## 3. Rows per day / venue / coin: spread (bps) and top-of-book size (USD)

Pooled over valid rows per file (all rows valid; majors order):

| day | venue | coin | n | spread mean / med / p99 / max (bps) | wide frac | bid $ med | ask $ med |
|---|---|---|---|---|---|---|---|
| 10-04 | binance | BTC | 14,172 | 0.0120 / 0.0117 / 0.0118 / 1.431 | 0 | 538,990 | 482,428 |
| 10-05 | binance | BTC | 44,983 | 0.0120 / 0.0116 / 0.0117 / 1.568 | 0 | 414,281 | 433,297 |
| 10-04 | binance | ETH | 14,172 | 0.0373 / 0.0371 / 0.0371 / 1.333 | 0 | 289,733 | 228,566 |
| 10-05 | binance | ETH | 44,983 | 0.0371 / 0.0368 / 0.0371 / 5.012 | 0.000022 (1 s) | 255,261 | 267,772 |
| 10-04 | binance | SOL | 14,172 | 0.8230 / 0.8225 / 0.8284 / 2.464 | 0 | 93,620 | 89,782 |
| 10-05 | binance | SOL | 44,983 | 0.8287 / 0.8289 / 0.8346 / 3.301 | 0 | 126,418 | 123,236 |
| 10-04 | binance | BNB | 14,172 | 0.1269 / 0.1269 / 0.1271 / 1.144 | 0 | 20,179 | 21,318 |
| 10-05 | binance | BNB | 44,983 | 0.1267 / 0.1265 / 0.1271 / 2.970 | 0 | 16,307 | 15,533 |
| 10-04 | binance | XRP | 14,172 | 0.6661 / 0.6660 / 0.6706 / 1.336 | 0 | 55,196 | 53,454 |
| 10-05 | binance | XRP | 44,983 | 0.6618 / 0.6607 / 0.6694 / 2.642 | 0 | 48,077 | 48,564 |
| 10-04 | bybit | BTC | 14,172 | 0.0118 / 0.0117 / 0.0118 / 1.034 | 0 | 247,020 | 230,531 |
| 10-05 | bybit | BTC | 44,925 | 0.0117 / 0.0116 / 0.0117 / 0.925 | 0 | 228,113 | 239,614 |
| 10-04 | bybit | ETH | 14,172 | 0.0371 / 0.0371 / 0.0371 / 0.409 | 0 | 132,549 | 129,557 |
| 10-05 | bybit | ETH | 44,906 | 0.0370 / 0.0368 / 0.0371 / 1.731 | 0 | 158,489 | 191,167 |
| 10-04 | bybit | SOL | 14,172 | 0.8227 / 0.8224 / 0.8285 / 1.646 | 0 | 57,601 | 52,612 |
| 10-05 | bybit | SOL | 44,923 | 0.8286 / 0.8289 / 0.8346 / 1.666 | 0 | 61,319 | 71,651 |
| 10-04 | bybit | BNB | 14,169 | 1.2696 / 1.2701 / 1.2727 / 1.273 | 0 | 10,901 | 11,318 |
| 10-05 | bybit | BNB | 44,896 | 1.2643 / 1.2661 / 1.2725 / 2.534 | 0 | 23,941 | 19,435 |
| 10-04 | bybit | XRP | 14,172 | 0.6661 / 0.6660 / 0.6705 / 1.332 | 0 | 23,574 | 24,242 |
| 10-05 | bybit | XRP | 44,922 | 0.6618 / 0.6608 / 0.6695 / 5.317 | 0.000022 (1 s) | 26,164 | 24,813 |

Only 2 seconds in 591,204 exceed 5 bps (one ETH/bianance, one XRP/bybit, both on
10-05). Spreads are otherwise rock-stable within each coin (p99 ≈ median).

## 4. Duplicates and clock lags (quote/sample/recv times)

- Duplicates on the collector key (venue, symbol, sample_time): **0** — the
  on-disk files are already clean (1 s sampling, no double-flush).
- `quote_time − sample_time`: all-rows median **+429 ms** (p1 −965 ms, p99
  +1,447 ms, 17.6% negative) — the sampled quote's exchange timestamp usually
  trails the sampler tick by < 0.5 s; small vs the 1m/4h buckets below.
- `recv_time − sample_time`: median **−59 ms** (p1 −1,354 ms, p99 0 ms, 91.9%
  negative) — the sampler stamps `sample_time` just after receiving, so recv
  slightly precedes the stamp; the documented local-clock-behind-exchange effect
  is absorbed in quote_time instead. Not a schema break.

## 5. Aggregates per 1m and per 4h bar per major (valid rows only)

Panel semantics: every covered (venue, minute) × all 5 symbols is emitted
(n = observed seconds; 0 = missing samples inside coverage, not a spread of 0);
fully uncovered bars are omitted. `covered_frac` on 4h bars = share of the 4 h
window inside the proxy coverage. `aggregates_1m.parquet`: 9,910 rows, 1,982
venue-minutes with rows. `aggregates_4h.parquet`: 80 rows (8 session bars × 2
venues × 5 symbols). Columns:
`bucket_ms, bucket_utc, venue, symbol, n, spread_mean_bps, spread_max_bps,
bid_usd_mean, ask_usd_mean, frac_wide, covered[/covered_frac]`.
Per-bar means equal the per-day means above to 3 decimals in every covered bar
(spreads do not drift across the 2 days); per-bar max spikes (up to 5.3 bps) are
single-second prints. Full per-bar table is in `results.json` (`agg_4h.bars`).

## 6. Binance vs Bybit spreads per coin (pooled over both days, valid rows)

| coin | binance mean / med / max | bybit mean / med / max | bybit/binance mean | wide frac bin / byb |
|---|---|---|---|---|
| BTC | 0.0120 / 0.0116 / 1.568 | 0.0118 / 0.0116 / 1.034 | 0.98 | 0 / 0 |
| ETH | 0.0372 / 0.0368 / 5.012 | 0.0371 / 0.0368 / 1.731 | 1.00 | 1 s / 0 |
| SOL | 0.8273 / 0.8287 / 3.301 | 0.8272 / 0.8287 / 1.666 | 1.00 | 0 / 0 |
| BNB | 0.1267 / 0.1266 / 2.970 | 1.2656 / 1.2663 / 2.534 | **9.99** | 0 / 0 |
| XRP | 0.6628 / 0.6608 / 2.642 | 0.6628 / 0.6609 / 5.317 | 1.00 | 0 / 1 s |

BTC/ETH/SOL/XRP top-of-book spreads are venue-identical to 2 decimals; BNB is
the exception — Bybit's book is ~10× wider (~1.27 vs ~0.13 bps), stable across
both days. Top-size depth is venue-similar for BTC/ETH/XRP (same order of
magnitude) and thinner on Bybit for SOL (~60–70k vs ~95–125k USD median).

## 7. What live execution research this enables later (forward plan, not findings)

1. Maker fill realism for dip rungs on Bybit (the stated goal): with per-second
   spread + top-size series, a rung's limit bid can be replayed second-by-second
   (fill iff bid ≥ ask print, size capped by ask_qty/top size) instead of the
   current 1m-trade-through assumption. Needs 4+ weeks so the replay covers
   stress episodes with wide books; the 2 calm days here supply only the loader
   and the spread baseline (sub-5 bps ~always on majors except single-second
   prints; BNB/Bybit structurally wider).
2. Venue choice for BOOK entries: BNB entries routed to Binance vs Bybit differ
   by ~1.1 bps each way in spread alone — after 4+ weeks, compare realised
   fill-rate × spread-cost per coin/venue before any routing claim.
3. Spread/depth conditioning of ladder fills: fix a wide-book definition in
   advance (e.g. spread > coin-specific p99 inside covered time only), then a
   wide→fill event study against the frozen ladder. Minimum **4 weeks** for a
   pilot definition, **12 weeks (~3 months)** for a ladder-conditioned study;
   must also cover ≥1 stress week, which 2 calm days cannot supply.
4. Coverage-SLO tracking from this loader (covered s/day, gap count; alert on
   >5 min gaps) so "tight book" stays distinguishable from "no data".

Verdict: stream PATCHY but loadable — schema conforms, zero duplicates, zero
invalid rows, yet 2 multi-hour collector outages in 2 days (7.3 h on 10-04,
4.7 h on 10-05 12:58→17:40 UTC) mean every rate must be gap-masked; N≈2 days
supports prep/monitoring only. Most notable fact: Bybit BNB top-of-book is ~10×
wider than Binance (~1.27 vs ~0.13 bps) while all other majors match across venues.
