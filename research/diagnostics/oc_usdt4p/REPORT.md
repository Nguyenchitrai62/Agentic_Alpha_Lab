# oc_usdt4p REPORT (2026-10-06): full-engine check of the USDT/USD premium book tilt on R2B1D17BFG2

POST-HOC LABELLED screen: the rule came from the vectorised screens in
`research/tournament/oc_usdtprem` (idea #71) and `research/tournament/oc_premexpo`
(USDT tilt = ALPHA vs exposure-matched control, 5y placebo pct 99.4); this is the
full-engine check, not a selection.

## Setup
Harness = verbatim copy of `oc_cmegap4p.py` worker wiring (itself `v421`
worker wiring: `phase_offset_full` prep + `pipe_setup("v321", agents on)` +
kd=1.7 corr-size + bear-book filter + G=2.0 gross cap + `win_start=5`; gate
fees maker 0.0002 / taker 0.00055; adverse long funding 0.0001), 4 phases
s=0..3, reset-metric (`reset_metric.year_reset` per anchor year, `v388.mix`
full-path DD).
Rule: USDT/USD premium z from Coinbase Exchange USDT-USD 1h
(`data/raw/coinbase_usdt_20261006/USDT-USD_1h.parquet`, 47240 rows,
2021-05-04 01:00 .. 2026-09-23 23:00 UTC, sha256
c6970f93...5e5c4269; median premium +0.5 bps): `prem = close - 1`,
`mean24 = rolling(24, min 20)`, `z = (mean24 - trailing-2160 mean)/std(ddof=1)`
current excluded (rolling 2160, min 1728, shift 1); as-of = last hourly row
with end strictly before T (`end <= T - 1s`; for 4h T the bar `[T-2h, T-1h]`).
On book rows: LONG targets x1.15 when z > 1, x0.85 when z < -1, else x1.0
(one market-wide signal for all 5 majors; shorts/flats/NaN-z bit-identical).
Applied AFTER the bear filter and BEFORE the shifted-clock ffill (same place
oc_cmegap4p put its tilt).
Rows: R2B1D17BFG2 (base) vs R2B1D17BFG2_USDT (base + tilt). Standard-grid tilt
counts (identical all shifts): 10950 rows, up 1909 / down 2109 / NaN-z 0
(coverage 100%; USDT history fully warmed up before 2021-09-24).
Book-only attribution: engine `attrib` per-bar book fractions of bar-start
equity (net of book fees/funding; sleeve excluded), cumulated as a book-only
path; its DD is close-sampled only (BOOK_CLOSE, no 1m marks).
Resources: strictly sequential (no Pool), RAM gate 2 GB with one bounded 300 s
wait then proceed-with-warning (second attempt: start 2.29 GB, s1 logged the
warning at 1.87 GB; each leg ~0.5 GB, all 8 legs succeeded; first attempt OOM'd
at 0.5 GB during minute concat and was retried via heavy_slot).
Win rate = pooled all-trade (book episodes net>0 after fees + rung exits
ret>0) by exit time in (a0, a0+365d], 4 shifts combined; book episodes mirror
`v213.trade_stats` episode logic.

## Reproduction (gate)
Base reproduces v421 exactly: 5y 5.41 %/mo, max yearly DD 16.91, full-path DD
16.82 (run.log row R2B1D17BFG2). Per-shift final equities also bit-match
oc_expiry4p/oc_cmegap4p base (s0 55.993, s1 17.031, s2 26.262, s3 6.264).
Proceeded to USDT comparison.

## Per anchor year (reset-metric %/month, DD; pooled all-trade win, n = nb+nr)

| year | base R / DD / win (n) | USDT R / DD / win (n) | gap R (USDT-base) |
|---|---|---|---|
| 2021-09-24 | 2.588 / 10.86 / 0.6129 (5001) | 2.620 / 11.16 / 0.6145 (5025) | +0.032 |
| 2022-09-24 | 3.282 / 16.91 / 0.6574 (4802) | 3.139 / 17.01 / 0.6557 (4827) | -0.143 |
| 2023-09-24 | 6.045 / 15.81 / 0.6956 (5979) | 5.624 / 16.39 / 0.6899 (6049) | -0.421 |
| 2024-09-24 | 10.677 / 8.27 / 0.6699 (5010) | 9.976 / 8.32 / 0.6674 (5009) | -0.701 |
| 2025-09-24 | 4.648 / 12.90 / 0.6267 (5783) | 4.639 / 11.90 / 0.6288 (5782) | -0.009 |

## Aggregates

| row | 5y mean | worst year | max yearly DD | full-path DD | dev4 (2021-24) | win_all 5y |
|---|---|---|---|---|---|---|
| base | 5.410 | 2.588 | 16.91 | 16.82 | 5.601 | 0.6533 |
| USDT | 5.168 | 2.620 | 17.01 | 17.00 | 5.300 | 0.6521 |
| USDT-base | -0.242 | +0.032 | +0.10 | +0.18 | -0.301 | -0.0012 |

No losing year on either leg. Win rate is flat (5y 0.6533 -> 0.6521; yearly
within +/-0.006). USDT loses -0.24 %/mo on the 5y mean and -0.30 %/mo on dev4;
2024 is -0.701 %/mo worse and 2023 -0.421 %/mo worse.

## Book-only attribution (attrib path, reset-style 4-shift average; DD close-sampled BOOK_CLOSE)

| year | base book R / DD | USDT book R / DD | gap R |
|---|---|---|---|
| 2021-09-24 | 0.429 / 8.96 | 0.434 / 10.27 | +0.005 |
| 2022-09-24 | 1.882 / 9.84 | 1.774 / 10.03 | -0.108 |
| 2023-09-24 | 1.853 / 13.67 | 1.719 / 13.90 | -0.134 |
| 2024-09-24 | 4.136 / 8.85 | 3.777 / 9.98 | -0.359 |
| 2025-09-24 | 3.334 / 8.37 | 3.333 / 9.75 | -0.001 |

Book aggregates: base 5y 2.319 / worst 0.429 / maxDD 13.67 / dev4 2.066;
USDT 5y 2.200 / worst 0.434 / maxDD 13.90 / dev4 1.919
(USDT-base: 5y -0.119, dev4 -0.147, maxDD +0.23pp).
Read: the tilt does not help the book leg itself in the full engine -- 4/5
years worse on book R, 5/5 years worse on book DD -- so the combined-portfolio
loss comes from the book, not from a dip-sleeve interaction.

## Live feasibility (Coinbase public candles, no keys)
`GET /products/USDT-USD/candles?granularity=3600` with a 2h window on
2026-10-06: HTTP 200, 3 candles, 0.517 s round-trip, no auth. The hourly plan
(1 candle/hour, read as-of each 4h bar with the pipeline's 5-min delay) is
feasible on the public endpoint; production would poll the last few closed
hourly candles each 4h bar and reuse the frozen z90 warm-up (90d history).

## Verdict
KEEP-CANDIDATE requires full-path DD not higher by > 0.3pp (17.00 - 16.82 =
+0.18 YES) AND 5y mean >= 5.45 (5.168 NO) AND no year worse by > 0.3 %/mo
(2024 gap -0.701, 2023 gap -0.421 NO) AND dev4 higher than base
(5.300 > 5.601 NO). Fails three of four legs.

VERDICT: NO
