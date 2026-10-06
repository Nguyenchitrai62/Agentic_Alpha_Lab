# oc_stopslip REPORT — is the S4 "stop slip 0.5" assumption conservative? (2026-10-06; PLAN pre-registered before any outcome)

DIAGNOSTIC (no PROMISING rule, no selection verdict). Universe: every `book_stop`
(773) + `rung_sl` (926) exit of the deployment config R2B1D17BFG2 =
`research/tournament/oc_kpi_g2/events_s{0..3}.parquet` pooled over the 4 phase
sub-accounts = 1699 stops, exit minutes 2021-10-27..2026-09-22. Stop level :=
event fill (base engine ran `stop_slip=0`, touch stops, so the fill IS the stop
except on gap opens, where it is the gap open and the measured slip is a lower
bound); `rung_sl` event prices are net of MAKER+TAKER, so `lv*0.00075` is added
back to recover the raw fill. Per stop, per venue (Binance 1m
`data/raw/{btc,majors}_intraday_20260924`, Bybit 1m `data/raw/bybit_linear_1m_20261004`,
no row >= 2026-09-24 00:00 UTC used): actual slip = adverse-positive bps of the
next-minute open vs the stop (long/stop-sell: `(stop-O_next)/stop`; short/stop-buy:
`(O_next-stop)/stop`); S4 slip = `0.5 * max(0, (stop-L)/stop)` longs /
`0.5 * max(0, (H-stop)/stop)` shorts from the SAME exit-minute bar; slip fraction
= actual / S4 (1.0 = next-open fill equals the S4 assumption). Flash = exit-minute
range `R=(H-L)/O` above `mu + 3*sig` of trailing-1440m R (causal; see PLAN.md for
the logged `R > 3*sig` -> `R > mu+3*sig` fix). Years by EXIT time in anchor years
Y0..Y4. Repro: `research/tournament/oc_stopslip/{PLAN.md,run.py,results.json,
stops.parquet}`; test `tests/test_oc_stopslip.py`. All five years are research
data; findings need prospective validation. Coverage is 100%: all 1699 stops have
the exit-minute bar AND the next-minute open on BOTH venues.

## (a) Stop slippage distribution per coin x year, bps (median / p90 / p99 / max; n)

| coin | year | n | Binance med/p90/p99/max | Bybit med/p90/p99/max |
|---|---|---|---|---|
| BTC | 2021 | 32 | 47.9 / 217.1 / 228.3 / 233.3 | 54.1 / 260.6 / 444.6 / 465.3 |
| BTC | 2022 | 86 | 2.4 / 132.8 / 215.0 / 240.9 | 5.9 / 226.7 / 311.2 / 336.8 |
| BTC | 2023 | 77 | -10.1 / 130.2 / 330.4 / 330.4 | -9.8 / 108.3 / 329.0 / 329.0 |
| BTC | 2024 | 39 | 1.8 / 49.5 / 309.1 / 315.3 | 2.7 / 48.7 / 312.0 / 318.2 |
| BTC | 2025 | 64 | -0.3 / 27.4 / 168.4 / 190.8 | 0.5 / 27.5 / 197.9 / 220.2 |
| ETH | 2021 | 44 | 24.1 / 171.5 / 232.9 / 242.3 | 29.3 / 178.0 / 241.6 / 251.2 |
| ETH | 2022 | 67 | 8.9 / 178.8 / 238.1 / 241.7 | 16.1 / 233.9 / 304.0 / 307.5 |
| ETH | 2023 | 101 | -3.6 / 145.6 / 295.0 / 300.2 | 0.4 / 180.4 / 338.9 / 344.2 |
| ETH | 2024 | 53 | -3.0 / 32.3 / 675.7 / 721.5 | -0.7 / 80.7 / 743.3 / 749.2 |
| ETH | 2025 | 42 | -11.5 / 12.8 / 43.0 / 53.2 | -5.4 / 103.9 / 107.9 / 107.9 |
| SOL | 2021 | 35 | -18.1 / 313.4 / 313.4 / 313.4 | -1.0 / 307.9 / 307.9 / 307.9 |
| SOL | 2022 | 93 | -23.8 / 243.3 / 374.8 / 384.4 | -9.3 / 360.1 / 1347.0 / 1347.0 |
| SOL | 2023 | 69 | -24.9 / 31.3 / 191.6 / 300.5 | -15.0 / 46.1 / 257.4 / 358.4 |
| SOL | 2024 | 25 | -3.4 / 18.0 / 28.4 / 28.8 | -3.4 / 17.4 / 27.4 / 27.7 |
| SOL | 2025 | 67 | -40.2 / 37.5 / 391.5 / 444.8 | -68.1 / 16.6 / 300.3 / 300.3 |
| BNB | 2021 | 55 | 5.8 / 85.8 / 184.9 / 203.4 | 11.2 / 94.2 / 184.5 / 206.8 |
| BNB | 2022 | 94 | 3.2 / 46.5 / 65.2 / 77.3 | 7.5 / 65.9 / 79.7 / 79.7 |
| BNB | 2023 | 134 | -13.2 / 111.2 / 453.0 / 453.0 | -5.5 / 99.4 / 469.4 / 469.4 |
| BNB | 2024 | 47 | 5.7 / 428.2 / 428.2 / 428.2 | 13.5 / 451.8 / 451.8 / 451.8 |
| BNB | 2025 | 73 | -6.8 / 53.0 / 216.9 / 398.0 | -1.0 / 74.1 / 239.4 / 428.6 |
| XRP | 2021 | 93 | 8.4 / 439.3 / 642.0 / 642.0 | 8.4 / 432.4 / 613.4 / 613.4 |
| XRP | 2022 | 58 | -17.7 / 17.4 / 133.5 / 224.5 | -16.7 / 144.7 / 708.8 / 748.2 |
| XRP | 2023 | 145 | -10.6 / 187.8 / 721.9 / 812.6 | -7.6 / 187.8 / 1026.6 / 1114.3 |
| XRP | 2024 | 45 | -1.1 / 132.3 / 494.9 / 494.9 | -1.1 / 140.4 / 521.7 / 521.7 |
| XRP | 2025 | 61 | 1.1 / 76.1 / 160.7 / 160.7 | 1.8 / 82.5 / 167.5 / 167.5 |
| ALL | pooled | 1699 | -4.6 / 145.6 / 494.9 / 812.6 | -1.6 / 196.9 / 738.1 / 1347.0 |

Median slip is negative on most coin-years (the next-minute open typically
recovers a few bps vs the stop: pooled median -4.6 Binance / -1.6 Bybit; only
45% Binance / 48% Bybit of stops have adverse-positive next-open slip), but the
right tail is violent (pooled p90 +146/+197, p99 +495/+738, max +813/+1347 bps).

## (b) Implied slip fraction vs the S4 = 0.5 assumption (median actual / median S4 / median frac)

| coin | year | Binance actual / S4 / frac | Bybit actual / S4 / frac |
|---|---|---|---|
| BTC | 2021 | 47.9 / 43.2 / 1.28 | 54.1 / 56.6 / 1.46 |
| BTC | 2022 | 2.4 / 13.9 / 0.09 | 5.9 / 17.4 / 1.14 |
| BTC | 2023 | -10.1 / 8.8 / -2.70 | -9.8 / 11.1 / -1.06 |
| BTC | 2024 | 1.8 / 5.1 / 0.73 | 2.7 / 7.0 / 0.80 |
| BTC | 2025 | -0.3 / 7.3 / 0.02 | 0.5 / 7.1 / 0.48 |
| ETH | 2021 | 24.1 / 55.5 / 0.84 | 29.3 / 48.2 / 0.89 |
| ETH | 2022 | 8.9 / 39.0 / 0.59 | 16.1 / 39.3 / 1.03 |
| ETH | 2023 | -3.6 / 16.3 / -0.55 | 0.4 / 27.5 / 0.05 |
| ETH | 2024 | -3.0 / 6.2 / -0.99 | -0.7 / 10.3 / -0.11 |
| ETH | 2025 | -11.5 / 10.5 / -0.63 | -5.4 / 11.8 / -0.19 |
| SOL | 2021 | -18.1 / 13.8 / -0.69 | -1.0 / 15.3 / -0.03 |
| SOL | 2022 | -23.8 / 48.7 / -0.49 | -9.3 / 47.1 / -0.09 |
| SOL | 2023 | -24.9 / 22.2 / -2.86 | -15.0 / 26.3 / -0.51 |
| SOL | 2024 | -3.4 / 11.3 / -0.71 | -3.4 / 8.5 / -0.14 |
| SOL | 2025 | -40.2 / 11.9 / -3.72 | -68.1 / 12.6 / -3.84 |
| BNB | 2021 | 5.8 / 32.9 / 0.54 | 11.2 / 32.2 / 1.09 |
| BNB | 2022 | 3.2 / 17.7 / 0.53 | 7.5 / 19.5 / 1.00 |
| BNB | 2023 | -13.2 / 30.1 / -0.59 | -5.5 / 17.3 / 0.09 |
| BNB | 2024 | 5.7 / 11.1 / 0.95 | 13.5 / 11.1 / 1.46 |
| BNB | 2025 | -6.8 / 9.0 / -1.97 | -1.0 / 12.5 / 0.26 |
| XRP | 2021 | 8.4 / 47.4 / 0.48 | 8.4 / 50.2 / 0.74 |
| XRP | 2022 | -17.7 / 12.7 / -5.33 | -16.7 / 9.9 / -0.90 |
| XRP | 2023 | -10.6 / 53.3 / -0.69 | -7.6 / 48.3 / -0.19 |
| XRP | 2024 | -1.1 / 20.0 / -0.82 | -1.1 / 20.2 / -0.26 |
| XRP | 2025 | 1.1 / 10.2 / 0.10 | 1.8 / 11.6 / 0.22 |
| ALL | pooled | -4.6 / 18.2 / -0.49 | -1.6 / 19.0 / 0.09 |

Pooled median fraction is -0.49 (Binance) / +0.09 (Bybit): at the median the
next-open fill is BETTER than the stop, i.e. the S4 halfway-into-the-range
charge (~18-19 bps median) is conservative against a next-open market fill. But
the fraction is regime-dependent: 2021 (volatile up-trend, medians +0.5..+1.5 on
both venues) and BNB/ETH 2022-2024 spots (frac ~0.6..1.5) sit AT or ABOVE the S4
line, while SOL/XRP crash years go deeply negative (snapback after the stop).
Two venue notes: (i) Bybit fractions run hotter than Binance in 8 of the 10
positive-median cells (same stop vs Bybit's own minute range); (ii) on 7.2% of
stops the Bybit exit-minute bar never reaches the Binance-derived stop at all
(S4 = 0 on Bybit vs 0.5% on Binance) — venue wicks differ, so a Bybit stop would
not even have triggered there.

## (c) Flash minutes (share of stops with exit-minute range > trailing mean + 3 sigma)

Pooled: 75.5% Binance / 74.7% Bybit. Per coin-year it ranges 33-94% (lowest:
BTC/ETH 2024 ~33-72%; highest: BTC/ETH 2021-2022 ~81-94%). Stops fire in violent
minutes by selection: the median exit-minute range is ~146 bps (Binance) vs a
trailing 1-day mean of ~16 bps, so most stop minutes ARE 3-sigma tail events
against calm history — the flash flag mostly confirms that stops cluster in
bursts, it does not isolate a small subset.

## (d) Worst 10 stop events (by max adverse next-open slip over the two venues)

| exit (UTC) | coin | kind | side | sh | stop | Binance slip/s4 | Bybit slip/s4 | flash bin/byb |
|---|---|---|---|---|---|---|---|---|
| 2022-11-09 18:30 | SOL | rung_sl | sell | s1 | 10.453 | 138.7 / 76.1 | 1347.0 / 692.6 | -/- |
| 2022-11-09 18:30 | SOL | rung_sl | sell | s0 | 10.453 | 138.7 / 76.1 | 1347.0 / 692.6 | -/- |
| 2024-01-03 12:09 | XRP | rung_sl | sell | s2 | 0.55685 | 812.6 / 420.7 | 1114.3 / 570.6 | yes/yes |
| 2024-01-03 12:09 | XRP | rung_sl | sell | s2 | 0.553506 | 757.1 / 393.0 | 1060.6 / 543.9 | yes/yes |
| 2024-01-03 12:09 | XRP | rung_sl | sell | s3 | 0.54876 | 677.2 / 353.2 | 983.3 / 505.3 | yes/yes |
| 2024-01-03 12:09 | XRP | rung_sl | sell | s3 | 0.545054 | 613.8 / 321.6 | 922.0 / 474.8 | yes/yes |
| 2022-11-09 18:10 | SOL | rung_sl | sell | s0 | 10.924 | -60.4 / 6.4 | 905.4 / 514.5 | -/yes |
| 2022-11-09 18:10 | SOL | rung_sl | sell | s0 | 10.924 | -60.4 / 6.4 | 905.4 / 514.5 | -/yes |
| 2022-11-09 18:10 | SOL | rung_sl | sell | s1 | 10.924 | -60.4 / 6.4 | 905.4 / 514.5 | -/yes |
| 2024-01-03 12:09 | XRP | rung_sl | sell | s1 | 0.543407 | 585.3 / 307.4 | 894.5 / 461.0 | yes/yes |

(slips/s4 in bps; duplicates = the same crash minute hitting parallel rungs in
two phase shifts.) All ten are dip-rung long stops in two crash bursts: the FTX
collapse (2022-11-09, SOL) and the 2024-01-03 flush (XRP, -10% minute). The FTX
rows also show the venue caveat at its starkest: at 18:30 Bybit SOL traded
~9.05-9.35 while Binance printed ~10.29-10.46, so the Bybit slip (1347 bps) is
dominated by the venue gap against a Binance-derived stop, not by an intrabar
move on Bybit.

## Verdict (one line)

The S4 stop-slip-0.5 charge is conservative at the median (next-open fills beat
the stop by ~2-5 bps while S4 charges ~18-19 bps, median fraction -0.49 Binance /
+0.09 Bybit), roughly fair in 2021-type volatility (fraction ~0.5-1.5), and far
too small for the crash tail (p99 +495/+738 bps, max +813/+1347 bps) — with the
caveats that gap opens make the stop proxy a lower bound and Bybit's worst prints
mix venue dislocation into the slip.
