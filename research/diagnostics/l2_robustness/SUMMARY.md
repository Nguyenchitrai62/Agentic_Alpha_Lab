# L2 MANUAL robustness (v342 L2; diagnostic only, nothing selected on it)
Design: MANUAL book (pullback entry 0.75 sigma, v216 grid in position) x0.75 + two human-placeable dip limits per coin at 3.0 / 4.0 sigma_4h
(TP limit + exchange-native touch stop at 8 sigma, R2 agents' size / TP at the bar open, size_mult 4.375, budget 0.26 at 8 sigma).
Rows (dev4 R / worst dev year / dev DD | 5y | most recent year | gate DD; no losing year in any row):
- base (M2 books)        5.779 / 2.251 / 19.71 | 5.531 | 4.544 | 19.71
- cost stress (maker 0.0004, taker 0.0012)  5.105 / 1.647 / 20.31 | 4.883 | 4.003 | 20.31
- human latency 15 min   5.558 / 2.260 / 20.00 | 5.354 | 4.544 | 20.00
- human latency 30 min   5.132 / 1.764 / 19.56 | 4.989 | 4.419 | 19.56
- human latency 60 min   3.942 / 0.098 / 24.83 | 3.760 | 3.035 | 24.83  (too late: breaks)
- CB books (live today)  6.233 / 3.437 / 17.73 | 5.925 | 4.704 | 17.73  (deployment form = paper pipeline M3; book win last year 0.556)
- CB books, latency 30   5.387 / 2.482 / 19.44 | 5.208 | 4.498 | 19.44
Bootstrap (base, first-four-year daily returns, 30-day blocks, 2000 draws): monthly p5 / p50 / p95 = 1.44 / 5.62 / 11.02, P(>=5 %/mo) 0.594,
P(loss year) 0.008, DD p50 / p95 = 11.16 / 20.16, P(DD > 20) 0.053.
Reading: the 5y floor holds in base, at 15-min latency and with CB books; the most recent year stays 4.0-4.7 (< 5) and cost stress breaches DD 20.
The CB-vs-M2 book comparison was seen here (dev and most recent year) -> CB is used only as the deployment form (PT member not live), not as a
research choice.
