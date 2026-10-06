# oc_collectors — live liquidation + top-of-book collector health since the 2026-10-05 17:40 UTC restart

Anchor: backend restarted 2026-10-05 ~17:40 UTC (coverage resumes binance 17:40:28.349Z, bybit 17:40:28.313Z).
Data on disk at check time ends 2026-10-06 02:44:18.803Z. Methods: reran
`research/tournament/oc_liqlive/load_liq.py` and `research/tournament/oc_topbook/load_topbook.py`
(no network, no edits); coverage from `data/raw/liquidations_live/_coverage/`
(same collector process — `topbook_live/` has no own coverage dir); per-hour counts
clipped to >= 2026-10-05T17:40:00Z. Full numbers in `results.json`. OPS check only:
no fills, no forward returns, no PnL.

## 1. Coverage since 17:40 UTC: continuous, identical on both venues

~32,630 s (~9.06 h) per venue, ZERO gaps > 60 s since the restart (proxy + own
`sample_time` diffs agree). Covered seconds per clock hour (both venues equal):

| hour | covered s | | hour | covered s |
|---|---|---|---|---|
| 10-05 17:00 | 1,172 (from 17:40:28) | | 10-06 00:00 | 3,600 |
| 10-05 18:00–23:00 | 3,600 each | | 10-06 01:00 | 3,600 |
| | | | 10-06 02:00 | 2,670 (data ends 02:44:18) |

Top-of-book rows/hour/stream match coverage to the second: 1,171 in the partial
hour, 3,593–3,600 in every full hour (only Bybit BNB deviates by 2–5 rows in two
hours), 2,670 in the trailing partial hour — i.e. the ~1 s sampler ran on all 10
streams (2 venues x 5 symbols) the whole time. Total since anchor: 326,813 topbook
rows; 802 liquidations (binance 568 / bybit 234).

Liquidations/hour since anchor are sparse but flowing on every stream except
Bybit BNB (expected — see below); e.g. BTC binance 10–44/h, ETH binance 4–24/h,
SOL/XRP single digits–27/h; Bybit BNB 4 rows total since anchor while its
top-of-book flows at 1/s, so this is venue truth (few BNB liquidations on Bybit),
not a drop. Per-venue/symbol totals since anchor in `results.json`.

## 2. Earlier days (comparison)

| day file | covered h (per venue) | note |
|---|---|---|
| 10-04 | 3.94 | 3.9 h spread over an 11.2 h span — rates unreliable |
| 10-05 | 17.1 | includes the 12:58:14 -> 17:40:28 backend-down hole (4.70 h) |
| 10-06 | 2.72 | partial day, clean so far |

Old gaps > 60 s (both venues together = collector-level, not venue drops):
87.5 s + 7.26 h on 10-04, 9.53 h overnight (collector off), 4.70 h on 10-05
pre-restart. Post-restart is the first clean stretch.

## 3. Duplicates and clock skew

- Duplicates on collector keys: 0 liq rows (2,512 full / 802 since anchor),
  0 topbook rows (855,687 full), 0 invalid topbook rows.
- Skew `recv-event` (liq): full-sample median +238 ms (binance +490 ms, bybit
  −347 ms, 32% negative); since anchor median +40 ms (binance +115 ms, bybit
  −593 ms, bybit 100% negative). Topbook: `quote-sample` median +475 ms full
  (+773 ms in the BTC+XRP since-anchor subset), `recv-sample` median −60 ms.
  All |lags| < ~1.5 s — the known local-clock-behind-exchange effect, not a break.
  Cross-venue per-second sequencing should keep ±1 s tolerance.

## 4. Disk growth per day (on-disk parquet)

| day | topbook | liq events | liq coverage |
|---|---|---|---|
| 10-04 (3.9 h covered) | 4.44 MB | 60 KB | 11 KB |
| 10-05 (17.1 h covered) | 19.27 MB | 118 KB | 35 KB |
| 10-06 partial (2.7 h) | 3.26 MB | 64 KB | 9 KB |

Full-day rate: topbook ~27 MB/day, liq ~0.2 MB/day (coverage negligible).
Projection: 4 weeks ~0.76 GB + ~6 MB; 12 weeks ~2.3 GB + ~18 MB — trivial disk.

## 5. Verdict: healthy since the restart, accumulable IF uptime holds

YES — 9 h continuous at full rate on all 10 streams with zero gaps/duplicates/
invalid rows can accumulate the 4–12 weeks needed, at negligible disk cost.
Caveats: only 9 h of clean evidence against 2 multi-hour outages in the first
2 days, so keep gap-masked rates, the >5 min gap alert, and auto-restart watch;
Binance `forceOrder` 1-event/s/symbol snapshot bias still applies to any joint
liquidation use.
