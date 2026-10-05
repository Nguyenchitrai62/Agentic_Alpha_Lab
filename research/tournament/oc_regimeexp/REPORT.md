# oc_regimeexp REPORT: R2B1D17BF monthly returns by market state at month start

Variant R2B1D17BF, 61 calendar months 2021-09..2026-09 (oc_kpi monthly table,
4-phase mix; 2021-09 partial from 2021-09-24, 2026-09 partial to g1).
State at each month start M0 (causal, hourly_ext only): bear = BTC 4h open
< mean of prior 1200 4h opens; vol = tercile of 30d hourly realized vol vs
all prior month starts back to 2021-03-01 (expanding); trend = sign of
90d log change of the 4h open. Returns in %.

## Single states (n, mean, median, share >= +5%, share < 0, worst)

bear=0 (price above 200d mean): n=33, mean +7.24, med 4.98, >=5% 48%, <0 27%, worst -7.50 (2024-01)
bear=1 (below 200d mean):       n=28, mean +4.55, med 2.21, >=5% 32%, <0 29%, worst -7.07 (2026-07)
vol low:  n=38, mean +7.45, med 4.69, >=5% 45%, <0 29%, worst -7.50 (2024-01)
vol mid:  n=19, mean +4.24, med 3.48, >=5% 37%, <0 21%, worst -7.07 (2026-07)
vol high: n=4,  mean +0.65, med 0.09, >=5% 25%, <0 50%, worst -3.21 (2024-09)
trend up:   n=33, mean +7.22, med 4.86, >=5% 45%, <0 24%, worst -7.50 (2024-01)
trend down: n=28, mean +4.57, med 2.83, >=5% 36%, <0 32%, worst -7.07 (2026-07)

## State combinations with n >= 5

bear0 + low + up:    n=21, mean +8.11, med 4.98, >=5% 48%, <0 29%, worst -7.50 (2024-01)
bear0 + mid + up:    n=8,  mean +6.04, med 6.92, >=5% 50%, <0 25%, worst -1.59 (2023-04)
bear1 + low + down:  n=12, mean +7.71, med 5.24, >=5% 50%, <0 33%, worst -5.16 (2023-09)
bear1 + mid + down:  n=8,  mean +1.56, med 1.85, >=5% 13%, <0 25%, worst -7.07 (2026-07)
Thin (n < 5, months only): bear0/low/down n=2 (2024-07, 2025-11);
bear0/mid/down n=2 (2025-03, 2025-05); bear1/high/down n=4
(2022-06, 2022-07, 2024-09, 2026-03); bear1/low/up n=3
(2022-10, 2024-10, 2026-06); bear1/mid/up n=1 (2021-10). No bear0/high month
ever occurred: high-vol months were always below the 200d mean in downtrend.

## Current state and what history says

At 2026-09-01 (September's bucket): NOT bear (78550 > 200d mean 69383),
vol LOW, trend UP. At the last data (price 2026-09-23 20:00 open 84467 >
200d mean 70695; vol through 2026-09-24 00:00 still low; 90d trend +35%):
same bucket bear0/low/up. That bucket's history: n=21, mean +8.1%/month,
median +5.0%, about half the months >= +5%, 29% negative, worst -7.5%
(2024-01) - but n=21 is thin for a forward expectation and every losing
month on record also came from benign-looking buckets, so treat as context,
not a forecast; needs prospective validation.

One-line summary: benign states (above the 200d mean, low vol, uptrend)
averaged ~7-8%/month vs ~1-5% in stressed states, but all buckets contain
losing months and the high-vol bucket has only n=4, so this is descriptive
context only.

## Caveats / post-hoc log

1. PLAN named the as-of evaluation "2026-09-24 00:00"; hourly data ends at
   the 23:00 bar, so no 4h bar opens at 2026-09-24 00:00. Implemented instead:
   price/trend from the last 4h open (2026-09-23 20:00), vol from all hourly
   bars t < 2026-09-24 00:00. Nothing at/after the cutoff is used.
2. Expanding vol terciles drift: BTC hourly vol trended down over 2021-2026,
   so 38 of 61 months land "low" and only 4 "high" - a property of the
   pre-registered causal rule, not a finding about markets.
3. 2021-09 (0.0%, mix starts 2021-09-24) and 2026-09 (partial) are included
   as stored; removing both leaves all bucket means within ~0.3pp of reported.
4. No selection, no tuning, no trade rule; monthly table byte-identical to
   oc_kpi/results_equity.json (test).
