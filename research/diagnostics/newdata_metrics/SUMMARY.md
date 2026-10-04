# Binance 5m metrics vs dip-fill outcomes (dev only, majors, t_exit < 2025-09-14; 2026-10-04)
12 features (top-trader / account long-short z, taker ratio, OI change 1h/4h/24h; own coin and BTC), as-of the fill minute with a 5-minute lag.
Only oi_1h (own-coin open-interest change over the hour before the fill) has the same IC sign every year (-0.22 / -0.07 / -0.01 / -0.13 / -0.19,
partial IC after x0..x6 -0.063, t -5.6). But its profile is not monotonic (decile 0: +35 bp / win 0.75; decile 5: +36 bp) and the low-vs-high
tercile spread reverses in 2023 (-11 vs +24 bp) and is flat in 2024 -> weak, inconsistent; NOT registered. Other features flip sign by year.
Script: metrics_dip_study.py (results JSON local).
