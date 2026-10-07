# oc_recent REPORT — diagnostic: what changed in 2025-09-24..2026-09-23 (2026-10-06; PLAN pre-registered)

DIAGNOSTIC (no selection rule, no PROMISING/REJECT verdict). Source: frozen
R2B1D17BF replicas research/tournament/oc_kpi/{events_s0..s3.parquet,
results.json} (s=0..3 pooled, each 1/4 capital). Year = ENTRY time in anchor
year [A_k, A_k+365d). Book = v213 episodes (limit entry -> stop/TP/close;
maker entries/TP/close, taker stops, funding excluded; mean = return on
position notional). Rungs = FIFO fill->exit, ret = engine ret net of rung
fees. Equity path = oc_kpi continuous-mix calendar months (verbatim). All
t < 2026-09-24. Repro: research/tournament/oc_recent/{PLAN.md,
analyze_recent.py, results.json}; test tests/test_oc_recent.py.

## 1. Year x sleeve: the recent year is a dip-margin year, not a book year

| year | book_long n/win/mean | book_short n/win/mean | dip n/win/mean | dip exits sl/tp/timeout | dip mean_w / gross_notional |
|---|---|---|---|---|---|
| 2021 | 421 / 0.423 / -0.00916 | 513 / 0.563 / 0.01069 | 4109 / 0.640 / 0.00102 | 208 / 1856 / 2045 (5.1/45.2/49.8%) | 0.1001 / 411.4 |
| 2022 | 452 / 0.518 / 0.01151 | 418 / 0.514 / -0.00322 | 4060 / 0.691 / 0.00096 | 242 / 2130 / 1688 (6.0/52.5/41.6%) | 0.1138 / 461.8 |
| 2023 | 491 / 0.582 / 0.01601 | 389 / 0.422 / -0.01224 | 4545 / 0.729 / 0.00130 | 287 / 2438 / 1820 (6.3/53.6/40.0%) | 0.1150 / 522.7 |
| 2024 | 622 / 0.547 / 0.01645 | 553 / 0.465 / 0.00001 | 3946 / 0.724 / 0.00539 | 50 / 2090 / 1806 (1.3/53.0/45.8%) | 0.1478 / 583.3 |
| 2025 | 396 / 0.515 / 0.01021 | 700 / 0.550 / 0.00749 | 4729 / 0.652 / 0.00057 | 137 / 2247 / 2345 (2.9/47.5/49.6%) | 0.0959 / 453.4 |

Book overall: 2025 win 0.537 (best of 5y) on 1096 trades vs 2024 win 0.508 on
1175. Directional mix flipped: longs 622->396, shorts 553->700; shorts healed
(0.465->0.550, mean ~0->0.0075) while longs stayed positive. Book edge did
NOT decay. Dip: most fills ever (4729, 394/mo vs 329/mo) but win -7.2pp,
mean/rung ~10x smaller (0.00057 vs 0.00539), TP share -5.5pp, timeout +3.8pp,
SL 1.3%->2.9%, rungs -35% smaller with -22% less gross notional.

## 2. By coin: dip decay is broad-based (all 5 coins), book mix shift is broad too

Dip win / mean, 2024 -> 2025: BTC 0.704/0.00391 -> 0.588/-0.00037; ETH
0.706/0.00388 -> 0.632/0.00056; SOL 0.732/0.00750 -> 0.663/-0.00051; BNB
0.703/0.00282 -> 0.679/0.00110; XRP 0.776/0.00900 -> 0.701/0.00207. Mean fill
weight fell on every coin (BTC 0.152->0.085, ETH 0.111->0.073, SOL
0.134->0.087, BNB 0.187->0.135, XRP 0.151->0.095). Timeout share rose on all
five; no single-coin story. Book: long count fell on 4/5 coins (BTC 136->70,
SOL 128->66 sharpest); short count rose on 4/5 (SOL 106->149, XRP 135->167);
2024's XRP-long star (138, win 0.667, mean 0.0556) normalised, ETH-long stayed
best (89, 0.652, 0.0175).

## 3. Monthly path: 2025 lived on two summer months; 2024 had a 63.8% November

| # | 2024-25 (11.27 %/mo, log 1.2727, 2 neg) | 2025-26 (5.06 %/mo, log 0.5842, 3 neg) |
|---|---|---|
| m1-6 | 2024-10 2.23, 2024-11 63.79, 2024-12 10.76, 2025-01 9.05, 2025-02 11.92, 2025-03 9.36 | 2025-10 4.98, 2025-11 4.52, 2025-12 1.52, 2026-01 -2.04, 2026-02 6.95, 2026-03 -1.50 |
| m7-12 | 2025-04 -0.68, 2025-05 9.72, 2025-06 -1.63, 2025-07 14.99, 2025-08 6.54, 2025-09 9.83 | 2026-04 0.51, 2026-05 7.25, 2026-06 12.42, 2026-07 -7.07, 2026-08 27.76, 2026-09 8.44 |
| top3 / share | 2024-11, 2025-07, 2025-02 / 58.6% of log | 2026-08, 2026-06, 2026-09 / 75.8% of log |

Oct-Dec 2025 (4.98/4.52/1.52) never fired vs Oct-Dec 2024 (2.23/63.79/10.76);
2026-07 (-7.07) is the worst month of either year. Dip fill-month extremes:
2025-10 opened the year with 692 fills at win 0.564 / mean -0.007 (weakest
dip-fill month of the two-year window), 2025-12 win 0.332 (weakest win rate of Mar-Apr 2026 nearly dry (40/30
fills); Jun-2026 1023 fills at 0.697/0.00206 then Jul-2026 14 fills. Bursts of
dislocations still come, but each pays less and TPs less often.

## 4. Plainly what changed; live implication

Not fewer dislocations (fills at a record high) and not book decay (book win
best-in-5y, shorts fixed). What changed is dip margin per dislocation:
smaller rungs, fewer TPs, more timeouts, ~10x lower mean per rung, on every
coin — consistent with shallower/faster-fading dislocations (lower
volatility per event) rather than missing events, plus a book regime tilted
short. The year still cleared 5.06 %/mo only via concentration (top-3 months
76% of log vs 59%). Live expectation: plan for high-volume/low-margin dip
flow and a lumpier path — the two summer months did the work, and any overlay
that trims gross (risk caps, DVOL-short-style gates) bites hardest exactly
here, because it shaves the few big months' notional while the other nine
months cannot make it back. (Sleeve equity attribution would need a sleeve
on/off replay and is not claimed; trade means are on position notional.)

One-line verdict: the most recent year is a lower-margin, more concentrated
regime — record dip volume at ~1/10th the per-rung edge with intact book win
rates — so live sizing should protect the few big months' gross, not chase
more fills.
