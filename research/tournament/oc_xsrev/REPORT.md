# oc_xsrev REPORT: daily cross-sectional reversal sleeve (idea #40)

Sleeve (fixed rule, 5 majors): at each UTC day close D, rank BTC/ETH/SOL/BNB/
XRP by the 1-day close-to-close return `C(D)/C(D-1)-1`; long the worst 2
(+0.25 each), short the best 2 (-0.25 each), middle 0 — gross 1.0x,
dollar-neutral; entered at the next day open, held open-to-open one day.
Daily O/C from `research/tournament/ext/hourly_ext.parquet` (t < 2026-09-24
00:00 UTC only; O(D) = D 00:00 open, C(D) = D 23:00 close; NaN coins never
selected, ties alphabetical; no thin days occurred). Costs: taker 0.00055 on
|dw|; longs pay 0.0003/day (0.0001 x 3), shorts zero. Base = R2B1D17BF reset-
convention year path (per-shift normalised segments, F(a0) = 1.0 — reproduces
oc_kpi R to 0.024pp/month; DD on the daily-00:00 grid, slightly under
hourly/1m-marked DDs). Combined = base daily + 0.25 x sleeve daily, per anchor
year [A, A+365d), 364-365 holding days (year 0 drops the 2021-09-24 partial
day — mix grid starts 04:00/08:00; last year ends 2026-09-22 — no 2026-09-24
open). One process, no 1m, peak RAM ~0.3 GB. All five years are research data;
any finding needs prospective validation. Repro:
research/tournament/oc_xsrev/{PLAN.md,run_xsrev.py,results.json};
test tests/test_oc_xsrev.py.

## Verdict

NOT PROMISING under the pre-registered gate: sleeve mean is positive in 0/5
years (negative every year, -2.5..-5.4 %/month), |corr| < 0.15 in 3/5 years,
combined DD not-worse in 0/5 years (worse every year by +0.25..+1.1pp). The
raw (pre-cost) edge is already zero-to-negative, and ~8 bps/day of turnover
(6.5) + funding (1.5) drag makes the net strongly negative.

## Tables

Per anchor year — sleeve standalone, then base vs combined:

year    sleeve m% / tot% / Sharpe / DD%      base m% / DD%     comb m% / DD%     excess / dDD     corr    pos? corr? dd?
21-22   -4.15 / -39.8 / -1.95 / 44.0          2.83 / 7.7        1.81 / 8.8       -1.02 / +1.11    -0.164   NO   NO   NO
22-23   -2.84 / -29.2 / -1.08 / 41.8          3.51 / 15.3       2.79 / 16.3      -0.71 / +0.97    +0.251   NO   NO   NO
23-24   -3.15 / -31.9 / -1.38 / 39.0          4.67 / 15.5       3.89 / 15.8      -0.78 / +0.25    -0.015   NO   YES  NO
24-25   -5.41 / -48.7 / -2.73 / 50.0         11.27 / 6.0        9.80 / 6.5       -1.47 / +0.46    -0.099   NO   YES  NO
25-26   -2.55 / -26.6 / -2.24 / 31.7          5.04 / 10.8       4.37 / 11.7      -0.66 / +0.87    +0.026   NO   YES  NO
(m% = year total^(1/12)-1; DD = max peak-to-trough on the year path, daily
grid; excess/dDD = combined minus base, pp.)

Sleeve operating stats (cost/fund/gross-mean bps/day, gross exposure):
21-22: 6.55 / 1.50 / -5.07, exp 1.00, thin 0, missing-opens 0.
22-23: 6.65 / 1.50 / -0.23, exp 1.00, thin 0, missing-opens 0.
23-24: 6.53 / 1.50 / -1.60, exp 1.00, thin 0, missing-opens 0.
24-25: 6.40 / 1.50 / -9.62, exp 1.00, thin 0, missing-opens 0.
25-26: 6.82 / 1.50 / +0.07, exp 1.00, thin 0, missing-opens 0.
(Gross is pre-cost; net mean is gross - cost - fund: -11.4 bps/day pooled.
Turnover alone (~6.5 bps/d ~ 2%/month) exceeds any gross edge.)

LOYO pooled sleeve mean (other 4 years, bps/day; descriptive): full-5y -11.38;
held-out 21-22 -10.94, 22-23 -12.13, 23-24 -11.82, 24-25 -9.84, 25-26 -12.16 —
pass (>0) 0/5 (uniformly negative; no subset rescues the sign).

## Caveats / post-hoc log

1. No post-hoc changes: single fixed rule, one run; PLAN.md frozen before any
   outcome was computed (amendment log still empty).
2. DDs here are daily-00:00 grid only (no 1m marking): base DDs read below
   oc_kpi 1m-marked DDs; the dd comparison is like-for-like on the same grid,
   but live DD would be worse for both legs.
3. The failure is not a cost-accounting artefact: mean gross (pre-cost) is
   negative in 4/5 years, so even zero-cost reversal loses; costs (~8 bps/day)
   roughly double the loss. Directionally this favours cross-sectional
   momentum over reversal at the 1-day horizon — but that is an unregistered
   observation, not tested here.
4. No lookahead: ranks use only closes <= D, positions execute at next open;
   hourly cap asserted in code; year day-sets and base convention identical
   to oc_tsmom Variant B.

## One-line verdict

NOT PROMISING: the 1-day cross-sectional reversal sleeve loses in 5/5 years (net -2.5..-5.4 %/month, gross ~0 or negative before ~8 bps/day costs) and worsens max yearly drawdown in 5/5 — the opposite of a diversifier.
