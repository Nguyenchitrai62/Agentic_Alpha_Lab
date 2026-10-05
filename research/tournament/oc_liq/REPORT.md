# oc_liq — first look at the live liquidation stream (descriptive note only)

Sample: 1,710 liquidation rows, 2026-10-04 05:25 UTC → 2026-10-05 12:58 UTC
(collector started 2026-10-04; ~1.5 days — far too little history for any test).
Methods fixed in PLAN.md before any outcome was computed. Script:
`research/tournament/oc_liq/liq_note.py` → `results.json` (this file renders it).

## 1. Rows per day / venue / coin (event_time UTC date)

| day | venue | coin | rows | notional $m | max single $k | long share |
|---|---|---|---|---|---|---|
| 10-04 | binance | BNB | 6 | 0.00 | 3.2 | 0.50 |
| 10-04 | binance | BTC | 40 | 0.35 | 107.4 | 0.30 |
| 10-04 | binance | ETH | 47 | 5.88 | 5,632.7 | 0.49 |
| 10-04 | binance | SOL | 27 | 0.24 | 142.8 | 0.33 |
| 10-04 | binance | XRP | 26 | 0.04 | 20.3 | 0.15 |
| 10-04 | bybit | BNB | 1 | 0.00 | 0.0 | 1.00 |
| 10-04 | bybit | BTC | 22 | 0.06 | 14.8 | 0.14 |
| 10-04 | bybit | ETH | 17 | 0.08 | 42.8 | 0.76 |
| 10-04 | bybit | SOL | 15 | 0.01 | 4.9 | 0.07 |
| 10-04 | bybit | XRP | 9 | 0.05 | 42.3 | 0.11 |
| 10-05 | binance | BNB | 100 | 0.37 | 122.2 | 0.53 |
| 10-05 | binance | BTC | 384 | 8.57 | 1,501.7 | 0.54 |
| 10-05 | binance | ETH | 277 | 4.27 | 299.9 | 0.52 |
| 10-05 | binance | SOL | 150 | 0.95 | 183.3 | 0.58 |
| 10-05 | binance | XRP | 152 | 0.70 | 79.7 | 0.73 |
| 10-05 | bybit | BNB | 8 | 0.09 | 42.6 | 0.25 |
| 10-05 | bybit | BTC | 180 | 1.67 | 256.1 | 0.64 |
| 10-05 | bybit | ETH | 95 | 0.72 | 125.1 | 0.71 |
| 10-05 | bybit | SOL | 77 | 0.29 | 30.1 | 0.66 |
| 10-05 | bybit | XRP | 77 | 0.30 | 46.9 | 0.73 |

10-05 is long-heavy on both venues (long share 0.5–0.7); 10-04 is mixed/short-heavy
with tiny counts. Total notional ≈ $24.7m. WARNING: Binance `forceOrder` pushes at
most ONE event per symbol per second (a snapshot, not every liquidation), while
Bybit `allLiquidation` batches every liquidation per 500 ms — counts and notionals
are NOT comparable across venues.

## 2. Coverage gaps (`_coverage`, connected-stream intervals)

| venue | file | intervals | covered h | span (UTC) | gaps > 60 s |
|---|---|---|---|---|---|
| binance | 10-04 | 237 | 3.94 | 05:25 → 16:38 | 87 s @05:28; **7.26 h @05:29→12:45** |
| bybit | 10-04 | 237 | 3.94 | 05:25 → 16:38 | same two gaps (collector-level outage) |
| binance | 10-05 | 648 | 10.80 | 02:10 → 12:58 | none (max gap 0 s) |
| bybit | 10-05 | 651 | 10.80 | 02:10 → 12:58 | none (max gap 2.4 s) |

"Zero liquidations" is a true zero only inside covered intervals. 10-04 is 3.9 h of
data spread over an 11.2 h span; treat any 10-04 rate as unreliable.

## 3. Size distribution (notional USD)

Global: n=1,710, p50 $1,035, p90 $21,532, p99 $188,989, max $5,632,672.
By venue — binance p50 $1,100 / p90 $25,739 / p99 $284,431; bybit p50 $857 /
p90 $14,922 / p99 $102,627 (venue snapshot bias, see §1).
By side — long liqs n=963 / $10.0m; short liqs n=747 / $14.6m (the $5.6m single
short event dominates the short tail).
Histogram: <$100: 290; $100–1k: 551; $1k–10k: 579; $10k–100k: 250; $100k–1m: 38;
≥$1m: 2. Clock check: median recv−event lag +524 ms (binance) / −219 ms (bybit),
31% of rows negative — the documented local-clock drift, not a schema break.

## 4. Largest liquidation minutes (per-minute notional, all binance) + 1m path

| minute UTC | venue/coin | notional $k | n | long/short $k | max single $k | ±30 min path (Binance 1m close, % of burst-min open) |
|---|---|---|---|---|---|---|
| 10-04 15:04 | binance ETH | 5,641.7 | 4 | 0 / 5,642 | 5,632.7 | min −0.24 / max +0.18; flat |
| 10-05 08:31 | binance BTC | 1,601.3 | 7 | 78 / 1,524 | 1,501.7 | min −0.43 / max +0.06; drifted −0.3 |
| 10-05 04:32 | binance BTC | 820.0 | 23 | 820 / 0 | 273.3 | min −0.26 / max +0.48; 23-event long flush |
| 10-05 06:53 | binance BTC | 626.1 | 14 | 0 / 626 | 431.2 | min −0.34 / max +0.40 |
| 10-05 06:17 | binance BTC | 616.7 | 2 | 0 / 617 | 515.7 | min −0.29 / max +0.20 |

Bybit's largest minutes are an order smaller (04:22 BTC $398k n=11; 03:58 BTC
$241k; 08:46 ETH $212k). Full ±30 min rebased paths are in
`results.json: burst_detail[].path_rebased_pct` (61–62 points each, Binance 1m).
No burst minute shows more than a ±0.5% excursion — bursts cluster inside
ordinary minutes, not visible crashes. Outlier flag: the 10-04 15:04 ETH minute is
one 2,086.9 ETH ($5.63m) short liquidation + 3 dust events at a price consistent
with klines (2,699.05 vs 1m 2697.6–2700.2, lag +1.0 s) — reported as-is, but a
single-event minute should not be read as a "burst".

## 5. Dip-ladder coincidence (frozen v183/v197 rungs: L(k)=open(T)·(1−k·σ), σ over 360 4h returns ending T−4h)

| burst minute | 4h bar T | open(T) | σ_4h | rungs 2.5/3.0/3.5/4.0σ | burst-min low | dip distance | touched |
|---|---|---|---|---|---|---|---|
| ETH 10-04 15:04 | 12:00 | 2,698.90 | 0.01051 | 2628/2614/2600/2585 | 2,697.60 | 0.05σ | none |
| BTC 10-05 08:31 | 08:00 | 86,221.7 | 0.00769 | 84565/84233/83902/83570 | 86,416.2 | −0.29σ (above open) | none |
| BTC 10-05 04:32 | 04:00 | 86,050.2 | 0.00768 | 84397/84067/83736/83406 | 85,469.7 | 0.88σ | none |
| BTC 10-05 06:53 | 04:00 | 86,050.2 | 0.00768 | as above | 86,075.3 | −0.04σ | none |
| BTC 10-05 06:17 | 04:00 | 86,050.2 | 0.00768 | as above | 85,919.9 | 0.20σ | none |

No top-5 burst minute touched any ladder rung (nearest: 0.88σ below open vs the
shallowest 2.5σ rung). With N=5 minutes over 1.5 days this is a description, not a
finding about bursts vs rungs.

## 6. What to measure once 3 months exist
1. Burst definition fixed in advance (e.g. per-coin rolling quantile of per-minute
   notional inside covered time only) and burst→forward-return event study with
   the frozen ladder (do rungs fill more often in post-burst windows than
   baseline?); pre-register before looking.
2. Venue cross-check: Binance-capped vs Bybit-full counts for the same minutes
   (calibrate the 1-per-second snapshot bias) and topbook sampling around bursts
   (spread/depth before vs after).
3. Long-vs-short burst asymmetry and funding/ basis conditioning; liquidation
   size distribution stability (weekly p50/p99) as a stream-health monitor.
4. Coverage-SLO tracking (connected h/day, gap count) so "no liquidation" stays
   distinguishable from "no data"; alert on >5 min gaps.

Verdict: stream HEALTHY but infant — schema conforms, 10-05 is 10.8 h continuous on both venues, yet N≈1.5 days (with a 7.3 h outage on 10-04) supports data-quality monitoring only, and none of the five largest burst minutes reached the frozen dip-ladder rungs.
