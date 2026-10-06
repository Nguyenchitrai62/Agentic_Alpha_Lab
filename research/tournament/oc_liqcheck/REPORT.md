# oc_liqcheck — liquidation store data-quality report (first days, descriptive only)

Sample: 3,230 liquidation rows, 2026-10-04 05:25 UTC → 2026-10-06 09:24 UTC
(collector `backend/liquidations.py` storage: `data/raw/liquidations_live/{venue}/<SYM>/YYYY-MM-DD.parquet`,
coverage `data/raw/liquidations_live/_coverage/{venue}/YYYY-MM-DD.parquet`,
topbook `data/raw/topbook_live/{venue}/<SYM>/YYYY-MM-DD.parquet`).
Script `research/tournament/oc_liqcheck/liqcheck.py` → `results.json` (+ `hourly.csv`); this file renders it.
LIGHT, read-only: one file at a time, topbook `sample_time` column only, REST 1m klines only for burst windows.
No rule, no threshold, no selection, no backtest.

## 1. Rows per feed per hour (liquidations; topbook in §2)

| day | venue | rows | notional $m | biggest coin-hour |
|---|---|---|---|---|
| 10-04 | binance | 146 | 6.52 | ETH 15:00 $5.66m (the $5.63m single short) |
| 10-04 | bybit | 64 | 0.21 | — |
| 10-05 | binance | 1,398 | 20.44 | BTC 06:00 $2.83m |
| 10-05 | bybit | 600 | 4.04 | BTC 06:00 $0.72m |
| 10-06 | binance | 733 | 6.55 | BTC 06:00 $1.61m / ETH 06:00 $1.10m |
| 10-06 | bybit | 289 | 2.76 | BTC 06:00 $0.72m |

Top coin-hours (venues combined): 10-04 15:00 ETH $5.66m; 10-05 06:00 BTC $2.83m;
10-05 04:00 BTC $2.32m; 10-05 08:00 BTC $2.15m; 10-06 06:00 BTC $1.61m.
Full per-hour/venue/coin table: `results.json: liq_rows_per_hour` + `hourly.csv`.
Topbook is ~1 s sampling: median ~3,000–3,600 rows/hour/venue/symbol (see `topbook_summary`); hourly counts collapse only inside the gaps below.

## 2. Coverage gaps > 5 min (authoritative: `_coverage`; topbook agrees)

| venue | gap start → end (UTC) | length | note |
|---|---|---|---|
| both | 2026-10-04 05:29:44 → 12:45:18 | 7.26 h | collector-level outage (same on both venues) |
| both | 2026-10-05 12:58:15 → 17:40:28 | 4.70 h | backend outage (assignment window 12:39–17:40; stream shows continuous cover until 12:58, then nothing until 17:40) |

Covered hours: 10-04 3.94 h, 10-05 17.1 h, 10-06 9.4 h (per venue; span 10-06 00:00 → 09:24 at report time).
10-06 has no gap > 5 min (max ~49–50 s). All 20 topbook files show exactly the same two >5 min gaps, so "zero liquidations" inside covered time is a true zero. "Zero" inside the two gaps above is NO DATA.

## 3. Duplicates / monotonicity / coverage / sanity

- Duplicates (key venue,symbol,event_time,raw_side,price,qty): 0 in-file across all 30 liq files, 0 global. Schema has no trade id; two identical liquidations in the same ms would collapse (rare, documented).
- Timestamp monotonicity: all 30 liq files sorted non-decreasing by `event_time`. Clock: median recv−event +506 ms binance / −327 ms bybit; negative-lag rows are the documented local-clock drift (bybit files ~98% negative per-file median), not a schema break.
- Symbol coverage: all 5 majors present on both venues on all 3 days (30/30 files, no missing combo). Day totals above; smallest cell is bybit BNB (1/9/5 rows).
- Side/qty sanity: side ∈ {long,short} 3,230/3,230; raw_side domain + side mapping consistent 3,230/3,230 (binance SELL=long/BUY=short, bybit Buy=long/Sell=short); price>0 and qty>0 everywhere; notional=price×qty consistent within 1e-4 everywhere.

## 4. Descriptive look: top-10 liquidation minutes vs Binance 1m path (no rule)

All top-10 burst minutes are binance (1-per-second snapshot venue reads larger by construction).

| minute UTC | coin | notional $k | n | ±30 min range % | +1/+5/+15/+30m % |
|---|---|---|---|---|---|
| 10-04 15:04 | ETH | 5,641.7 | 4 | −0.24/+0.18 | −0.04/−0.07/+0.12/+0.03 |
| 10-05 08:31 | BTC | 1,601.3 | 7 | −0.43/+0.06 | −0.02/−0.18/−0.43/−0.29 |
| 10-05 04:32 | BTC | 820.0 | 23 | −0.26/+0.48 | −0.12/−0.08/−0.09/−0.26 |
| 10-05 20:51 | BTC | 818.0 | 2 | −0.15/+0.00 | −0.04/−0.04/−0.08/−0.04 |
| 10-06 06:14 | ETH | 793.5 | 1 | −0.04/+0.35 | −0.04/+0.09/+0.02/+0.18 |
| 10-05 22:01 | BTC | 770.2 | 4 | −0.23/+0.03 | −0.07/−0.08/−0.04/−0.06 |
| 10-05 18:28 | BTC | 638.6 | 5 | −0.18/+0.15 | +0.03/+0.05/+0.09/+0.13 |
| 10-05 06:53 | BTC | 626.1 | 14 | −0.34/+0.40 | +0.15/+0.13/+0.25/+0.09 |
| 10-05 06:17 | BTC | 616.7 | 2 | −0.29/+0.20 | +0.04/−0.04/−0.06/+0.18 |
| 10-05 06:53 | ETH | 491.0 | 15 | −0.29/+0.43 | +0.20/+0.16/+0.40/+0.06 |

Paths rebased to the burst-minute open (full 61-point paths in `results.json: burst_detail[].path_rebased_pct`).
Description only: no burst minute exceeds a ±0.5% excursion; single-event minutes (10-04 ETH, 10-06 ETH) are not "bursts". Nothing here selects or sizes anything.

## 5. When is the store ready for a walk-forward test?

Earliest ready date: **2027-01-04** — 3 calendar months after the 2026-10-04 collector start, with several
2.5-sigma flushes re-counted on covered time only. At N≈2.5 covered days the flush proxy is unstable
(158 coin-hours, hourly p95 notional ≈ $1.12m), so the calendar gate stands and the flush count must be
re-done once 3 months exist.

Verdict: stream HEALTHY but infant — schema conforms, no duplicates, coverage accounting works and the
two >5 min outages are fenced as no-data, yet N≈2.5 covered days supports monitoring only.
