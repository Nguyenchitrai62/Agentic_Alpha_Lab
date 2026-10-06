# oc_tsmom REPORT: daily 30-day time-series-momentum sleeve (idea #36)

Sleeve (fixed rule, BTC+ETH only): at each UTC day close D, signal = sign of
the 30-day close-to-close return; position = signal x (10% ann vol target /
realised 30d vol of daily log returns, xsqrt(365)), capped at 1.0x per coin;
entered at the next day open (hourly opens from
`research/tournament/ext/hourly_ext.parquet`, t < 2026-09-24 00:00 UTC only),
held open-to-open one day. Costs: taker 0.00055 on |dpos|; longs pay 0.0003/day
(0.0001 x 3), shorts zero. Base = R2B1D17BF reset-convention year path
(per-shift normalised segments, F(a0) = 1.0 — reproduces oc_kpi R to
0.024pp/month; DD on the daily-00:00 grid, slightly under hourly/1m-marked
DDs). Combined = base daily + 0.25 x sleeve daily, per anchor year
[A, A+365d), 364-365 holding days (year 0 drops the 2021-09-24 partial day —
mix grid starts 04:00; last year ends 2026-09-22 — no 2026-09-24 open).
Pre-registered Variant A (continuous-mix base) kept in results.json as a
sensitivity: identical passes. One process, no 1m, peak RAM ~0.2 GB. All five
years are research data; any finding needs prospective validation. Repro:
research/tournament/oc_tsmom/{PLAN.md,run_tsmom.py,results.json};
test tests/test_oc_tsmom.py.

## Verdict

NOT PROMISING under the pre-registered gate: combined return is higher in 5/5
years BUT the combined max yearly DD is not-worse in 0/5 years (worse every
year by +0.5..+1.5pp). The sleeve is positively correlated with the base
(+0.17..+0.47), so instead of diversifying it adds correlated volatility.

## Tables

Per anchor year — sleeve standalone, then base vs combined (primary Variant B):

year    sleeve m% / tot% / Sharpe / DD%    base m% / DD%    comb m% / DD%    excess / dDD    corr   ret? dd?
21-22   +1.18 / +15.1 / 0.84 / 16.9        2.83 / 7.7       3.15 / 8.3       +0.32 / +0.54   0.21   YES  NO
22-23   +0.12 / +1.5  / 0.18 / 19.2        3.51 / 15.3      3.56 / 16.4      +0.05 / +1.07   0.17   YES  NO
23-24   +1.00 / +12.7 / 0.69 / 17.7        4.67 / 15.5      4.91 / 16.1      +0.24 / +0.57   0.46   YES  NO
24-25   +1.67 / +22.0 / 1.22 / 11.6        11.27 / 6.0      11.73 / 7.0      +0.46 / +1.02   0.28   YES  NO
25-26   +0.90 / +11.4 / 0.64 / 16.2        5.04 / 10.8      5.25 / 12.4      +0.22 / +1.53   0.47   YES  NO
(m% = year total^(1/12)-1; DD = max peak-to-trough on the year path, daily
grid; excess/dDD = combined minus base, pp.)

Sleeve operating stats (avg |pos| BTC/ETH, cost/funding drag):
21-22: 0.15/0.12, cost 0.22 bps/d, fund 0.32 bps/d. 22-23: 0.25/0.21, 0.60,
0.65. 23-24: 0.22/0.19, 0.44, 0.74. 24-25: 0.25/0.15, 0.38, 0.75. 25-26:
0.26/0.18, 0.60, 0.67. (Drag ~1 bps/day combined vs sleeve mean +3.7 bps/d.)

LOYO pooled sleeve mean (other 4 years, bps/day; descriptive): full-5y +3.71;
held-out 21-22 +3.55, 22-23 +4.39, 23-24 +3.68, 24-25 +3.17, 25-26 +3.77 —
sign match 5/5 (sleeve mean positive in every 4y pool, but small).

Variant A sensitivity (continuous-mix base): ret 5/5, dd 0/5 — same verdict.

## Caveats / post-hoc log

1. One post-score correction, disclosed in PLAN.md amendment: primary base
   changed from continuous-mix daily sampling to the reset convention (the
   assignment cites reset_metric.py); the first run exposed mean-of-ratios vs
   ratio-of-means gaps up to 0.83pp/month. Both variants are stored; the
   verdict is identical, so no outcome shopping.
2. DDs here are daily-00:00 grid only (no 1m marking): base DDs read
   1-3pp below oc_kpi 1m-marked DDs; the dd comparison is like-for-like on the
   same grid, but live DD would be worse for both legs.
3. Sleeve standalone DDs (11.6-19.2%) exceed the base DDs in 4/5 years — the
   sleeve itself is the more volatile leg per unit; 0.25x sizing contains but
   does not remove the correlated tail.
4. Year-0 has 364 holding days (drops the 2021-09-24 partial day); the last
   year has 364 (no 2026-09-24 open exists). No lookahead: signals use only
   closes <= D, positions execute at next open; hourly cap asserted in code.

## One-line verdict

NOT PROMISING: the 0.25x 30d-TSMOM overlay lifts return in 5/5 years but
worsens max yearly drawdown in 5/5 (corr +0.17..+0.47 with the base — a
correlated return add-on, not a diversifier).
