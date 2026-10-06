# oc_spreadcost REPORT (2026-10-06; assignment oc_spreadcost, descriptive + realism overlay)

## Setup
Top-of-book store `data/raw/topbook_live/` (collector `backend/liquidations.py`,
~1 s best bid/ask per venue/symbol, read-only, one file at a time): 30 day
files (2 venues x 5 symbols x 3 days 2026-10-04..06), 1,097,819 rows, ~30
covered hours (10-04 3.9 h + 10-05 ~17 h with the 12:58->17:40 backend gap as
missing rows + 10-06 9.6 h; no `_coverage` under `topbook_live/`, gaps are
missing rows by construction). Spread = `(ask-bid)/mid*1e4` bps; 0 invalid
rows kept (ask<=bid / non-positive / NaN excluded and counted: 0 everywhere).
Volatile minutes per coin x venue: 1m buckets by `sample_time`, volatility =
`(max(mid)-min(mid))/mean(mid)*1e4`, top 20 buckets with >= 20 samples (no 1m
kline data exists for the October window, so volatility is self-contained from
the topbook mids). Dip replica: B1 (static resting bid at `lv`, STRICT
`low < lv` fill, size `1/(1+n)` with the v399 n detector) + D0-from-fill exits
(TP `px*(1+sg)` maker; close5 stop 4sg / backstop 8sg / timeout at next-bar
open taker; funding 0.0001 on settling timeouts; stop-first), R2 depths
{2.5,3,3.5,4,5}, 4 phase-shifted 4h grids (clock shifts 0..3h from 2020-08-01,
as in oc_phasedisp), 5 anchor years (bar open in [2021-09-24, 2026-09-24),
Binance 1m, no row >= 2026-09-24 00:00 UTC used). Overlay (realism adjustment,
NOT a rule): every taker exit pays half the Bybit spread extra --
stop/backstop legs `0.5*p90/1e4`, timeout legs `0.5*median/1e4` (stops fire in
volatile minutes, hence p90); TP maker legs unchanged. Fills pooled over the 4
phases (22,251 fills: 12,215 TP untouched, 655 stop + 269 backstop + 9,112
timeout charged). Sums are rung-y attribution units, not portfolio %/month.
Script `research/tournament/oc_spreadcost/{spreadcost.py,run.py}` ->
`results.json` + `fills.parquet`; test `tests/test_oc_spreadcost.py`.
All five years are research data; findings need prospective validation.

## 1. Quoted spread per coin x venue (bps; n = valid rows)

| coin | Binance med / p90 / p99 / max | Bybit med / p90 / p99 / max | vol20 med bin / byb |
|---|---|---|---|
| BTC | 0.0117 / 0.0117 / 0.0118 / 2.81 | 0.0117 / 0.0117 / 0.0118 / 3.46 | 0.0116 / 0.0116 |
| ETH | 0.0369 / 0.0371 / 0.0371 / 7.43 | 0.0369 / 0.0371 / 0.0371 / 1.73 | 0.0368 / 0.0368 |
| SOL | 0.8292 / 0.8337 / 0.8380 / 4.94 | 0.8292 / 0.8337 / 0.8380 / 2.49 | 0.8296 / 0.8292 |
| BNB | 0.1269 / 0.1280 / 0.1284 / 2.97 | 1.2706 / 1.2810 / 1.2853 / 2.54 | 0.1260 / 1.2616 |
| XRP | 0.6646 / 0.6679 / 0.6698 / 2.66 | 0.6646 / 0.6679 / 0.6698 / 5.32 | 0.6624 / 0.6624 |

BTC/ETH/SOL/XRP books are venue-identical to 2 decimals (as in oc_topbook);
Bybit BNB is ~10x wider (1.27 vs 0.13 bps). Spreads do NOT widen in volatile
minutes (vol20 medians ~= overall medians on every coin x venue); maxima are
single-second prints (2 venues x 1 s > 5 bps in the earlier 2-day cut).

## 2. Overlay charge per coin (half Bybit spread, fractions of fill price)

| coin | stop/backstop: 0.5*p90 | timeout: 0.5*median |
|---|---|---|
| BTC | 0.59e-6 (0.0059 bps) | 0.58e-6 (0.0058 bps) |
| ETH | 1.85e-6 (0.019 bps) | 1.85e-6 (0.018 bps) |
| SOL | 4.17e-5 (0.42 bps) | 4.15e-5 (0.41 bps) |
| BNB | 6.41e-5 (0.64 bps) | 6.35e-5 (0.64 bps) |
| XRP | 3.34e-5 (0.33 bps) | 3.32e-5 (0.33 bps) |

Sub-basis-point on every coin (largest: BNB 0.64 bps per taker exit).

## 3. Replica 5y sums + DD, base vs spread-adjusted (per coin and total)

Equal-weight (sum of net y; DD of exit-date daily-sum path from 0):

| coin | n | base sum | adj sum | delta | base DD | adj DD | DD change |
|---|---|---|---|---|---|---|---|
| BTC | 4394 | 5.636 | 5.635 | -0.001 | 1.243 | 1.243 | +0.000 |
| ETH | 4577 | 6.549 | 6.545 | -0.004 | 1.330 | 1.330 | +0.000 |
| SOL | 3906 | 14.787 | 14.717 | -0.070 | 2.544 | 2.547 | +0.003 |
| BNB | 4734 | 2.024 | 1.884 | -0.140 | 2.384 | 2.398 | +0.014 |
| XRP | 4640 | 10.758 | 10.698 | -0.060 | 3.070 | 3.070 | +0.000 |
| TOTAL | 22251 | 39.755 | 39.479 | **-0.275** | 7.305 | 7.322 | **+0.016** |

Size-weighted (B1 actual, `w*y`; primary for a B1 ladder):

| coin | base sum_w | adj sum_w | delta_w | base DD_w | adj DD_w | DD_w change |
|---|---|---|---|---|---|---|
| BTC | 4.075 | 4.074 | -0.001 | 0.865 | 0.865 | +0.000 |
| ETH | 6.006 | 6.004 | -0.003 | 0.890 | 0.890 | +0.000 |
| SOL | 9.308 | 9.264 | -0.045 | 2.281 | 2.285 | +0.004 |
| BNB | 1.695 | 1.606 | -0.089 | 1.929 | 1.960 | +0.031 |
| XRP | 9.674 | 9.636 | -0.039 | 2.648 | 2.650 | +0.002 |
| TOTAL | 30.759 | 30.583 | **-0.176** | 3.127 | 3.138 | **+0.012** |

BNB carries ~half the total drag (-0.14 of -0.28 eq) from its structurally
wider Bybit book; BTC/ETH move by ~1e-3. DD is essentially unchanged
(+0.01-0.03 on DDs of 1-7). Per-year tables in `results.json:per_coin_year`.

## Notes
- Replica fidelity: phase-0 yearly eq sums 3.903/0.393/5.276/4.066/1.538 vs
  oc_dipexit D0 3.777/0.393/5.276/4.066/1.538 (Y1-Y4 exact; Y0 +0.126 = the 23
  rungs oc_dipexit drops because an E-variant leg is NaN). Phase dispersion is
  large: per-phase eq sums 15.18 / 10.10 / 9.40 / 5.08 (same clock-shift
  sensitivity as oc_phasedisp) -- one more reason the pooled 4-phase view is used.
- Caveats: spread sample is ~30 covered hours over 3 days with two multi-hour
  outages -- a calm-window snapshot, not a stress calibration (no wide-book
  episode; the p90 charge for stops is the concession to that). Taker-leg
  spread is proxied by half the quoted spread (no depth/replay: queue and
  `ask_qty` are not walked). Sums/DD are rung-y units pooled over 4 phases,
  not portfolio %/month. Heavy run went through the slot semaphore with
  `--min-free-gb 1.0` (documented deviation: host reported 0.7-1.8 GB free at
  assignment time, slots empty; job peak ~0.4 GB).

## Verdict
VERDICT: Half-spread on taker exits is a -0.28 eq (-0.18 size-weighted) realism
haircut over 5 pooled-phase years with no DD impact (+0.01-0.03) -- half of it
on BNB -- so missing spread explains none of the deployment S5 drag; the
current maker/taker + funding cost model already covers calm-window spread,
and any further spread work needs a multi-week sample with real stress episodes.
