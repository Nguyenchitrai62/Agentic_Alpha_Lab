# Collector check 2026-10-06 (~15:26 UTC, collector LIVE)

Scope: `backend/liquidations.py` (public WS only) -> `data/raw/liquidations_live/`
+ `data/raw/topbook_live/`; cross-checked with `scripts/daily_status.py` §7
(`check_collectors`, gap >5 min, 24h window). Read-only; new helper
`scripts/collector_coverage.py` + `tests/test_collector_coverage.py` (5 passed).

## Coverage since start (per venue; liq coverage == topbook sample gaps)
- Span 2026-10-04 05:25 UTC -> 2026-10-06 15:26 UTC = 58.0h expected.
- Covered 32.7h per venue (56.4%), IDENTICAL for binance/bybit, liq+topbook.
- No venue-specific gap >5 min: reconnect logic holds while process is alive.

## Every gap >5 min (all streams, both venues)
1. 10-04 05:29:44 -> 12:45:18 UTC (7h15m): died 4 min after first start; startup/manual-run era.
2. 10-04 16:38:20 -> 10-05 02:10:14 UTC (9h32m): overnight whole-process stop.
3. 10-05 12:58:14 -> 17:40:28 UTC (4h42m): midday whole-process stop.
4. 10-06 10:31:21 -> 14:16:27 UTC (3h45m): backend outage 10:32-14:16 UTC (given).
- Cause signature: all 4 hit every venue+stream at once = collector/backend down, not WS.

## Events/hour by coin (both venues / 32.7 covered h)
- BTC 1496 = 45.7/h; ETH 931 = 28.4/h; SOL 640 = 19.5/h; BNB 192 = 5.9/h;
  XRP 520 = 15.9/h (total ~115/h).
- Venue totals: binance 2563 (1/sec snapshot, not every liq), bybit 1216 (every
  liq per 500ms batch). Counts/notionals NOT comparable across venues.

## Sizes / growth
- Liquidations: 36 files, 344 KB (~115 KB/day). Topbook: 30 files, 36 MB
  (~12 MB/day; ~1.2-1.8 MB per symbol-venue-day, 1 s sampling).
- Projection: 3 mo -> liq ~10 MB, topbook ~1.1 GB; 6 mo -> ~20 MB / ~2.2 GB.

## Usable for research in 3-6 months?
- Volume yes (disk-trivial), coverage NO at 56%: gaps are unfillable (no free
  history for these streams). If uptime is >=95% from now, a usable panel with
  flagged holes; at current uptime, not enough.

## Fixes (text only, nothing changed)
1. Run collector supervised (auto-restart on crash/host boot); keep host awake.
2. Alert on coverage-heartbeat age >5 min (daily_status §7 already computes it).
3. Log every restart cause; never backfill (no source) - mark holes via _coverage.
