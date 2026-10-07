# oc_idea8 REPORT: dominance-momentum dip throttle (IDEAS.md idea #8)

Universe: majors (BTC/ETH/SOL/BNB/XRP) x R2 depths (2.5/3/3.5/4/5), 5498
fills, outcome y_dep (exact net at deployed TP, fees + adverse funding
inside). Anchor years 2021-09-24 .. 2025-09-24
(n = 990/1045/1330/989/1144). Market-wide FLOW per 4h bar T: dom30 =
BTC 30d log-ret minus equal-weight majors 30d log-ret (180 bars, full
opens history from 2017, causal, oc_dombook math); ddom(T) = dom30(T) -
dom30 42 bars earlier (7 d). Alt-dip throttle (ONE pre-registered rule):
m = 0.5 on ETH/SOL/BNB/XRP fills iff ddom(T) > q67 else 1.0, BTC always
1.0; q67 = 67th pct of ddom over full-grid bars strictly < anchor.
size_new = size_dep x m, scored with harness5 equal-exposure
renormalisation per year (timing only). Coverage 100% in all 5 years;
no missing grid T; no new data fetched; opens only; one process, < 1 GB.

## Verdict

NOT PROMISING under the pre-registered rule: gain 4/5 sequential, LOYO
gain 5/5, but worst-day not-worse only 3/5. The 2022 bear year is the
hypothesised win (gain +0.98, worst day -1.91 -> -1.35, FTX-type alt
cascade throttled), but 2021 misses gain by -0.01 and the throttle
deepens the worst day in 2021 (-0.43 -> -0.58) and 2023 (-0.58 -> -0.95),
so the tail clause binds exactly where the yearly renorm scales
unthrottled days up.

## Tables

Sequential screen (cut-offs from strictly previous bars; renorm sizes):

year    n     q67     train bars  thr(all/alts)  S_dep   S_new   gain    pass?
21-22   990   0.0298  8756        0.40/0.50        4.485   4.471   -0.014  NO
22-23   1045  0.0292  10946       0.39/0.48        0.924   1.901   +0.977  YES
23-24   1330  0.0275  13136       0.26/0.33        6.627   6.852   +0.225  YES
24-25   989   0.0249  15332       0.29/0.35        4.265   4.891   +0.626  YES
25-26   1144  0.0240  17522       0.33/0.41        1.906   2.336   +0.430  YES
(units native size*y_dep; S_dep > 0 every year; raw retention
0.80/1.67/0.90/0.98/1.03 - descriptive, renorm isolates timing.)

Worst daily sum (renormalised sizes, grouped by floor(T) day):

year    W_dep    W_new    tail pass?
21-22   -0.434   -0.581   NO
22-23   -1.915   -1.351   YES
23-24   -0.577   -0.951   NO
24-25   -0.703   -0.465   YES
25-26   -0.498   -0.302   YES

Full path (concatenated renormalised daily sums, descriptive):
worst day -1.91 -> -1.35 (improves, driven by 2022); maxDD -1.91 -> -1.35.

LOYO gain (cut-offs from bars in the other 4 year windows, renorm inside
held-out; LOYO q67 0.017-0.021, lower than sequential 0.024-0.030):

held-out  q67     gain    pass?
21-22     0.0171  +0.004  YES
22-23     0.0179  +1.011  YES
23-24     0.0193  +0.204  YES
24-25     0.0186  +0.525  YES
25-26     0.0211  +0.366  YES

Per-coin gain split (renormalised sizes; BTC never throttled - its gain is
purely the yearly renorm factor > 1; descriptive):

year    BTC     ETH     SOL     BNB     XRP
21-22   +0.155  +0.124  -0.320  +0.053  -0.027
22-23   +0.005  +0.134  +0.283  +0.112  +0.444
23-24   +0.177  -0.168  -0.136  +0.179  +0.173
24-25   +0.090  +0.227  -0.017  +0.212  +0.114
25-26   +0.016  +0.127  +0.264  +0.107  -0.083
(Spearman ddom vs y_dep on alt rows: -0.02/+0.01/-0.05/-0.11/+0.05 -
no consistent rank relation; the effect is tail-timing, not ranking.)

## Caveats / post-hoc log

1. No post-hoc change: flow definition (ddom = dom30 minus 42-bar lag),
   single q67/x0.5 rule on alts only, bar-pool cut-offs, and the 3-part
   decision rule were all pre-registered in PLAN.md before any outcome was
   computed. Two code fixes before the first successful run (both
   definition-preserving): Timestamp->ns conversion and a DatetimeIndex
   boolean-mask op; no outcome had been produced yet.
2. The failure is the tail, not the sign: sequential gain misses only 2021
   (by -0.014, the smallest |gain|), LOYO is 5/5, but the yearly renorm
   scales unthrottled days up, so the worst day deepens in 2021 and 2023
   even though raw exposure falls (raw retention 0.80/0.90 there).
3. Sequential q67 (0.024-0.030, full history back to 2017) sits above LOYO
   q67 (0.017-0.021, other-4-year windows only): the pre-2021 history has
   higher ddom quantiles. Both families pass gain; the verdict does not
   hinge on which pool is used.
4. Rung-level equal-exposure screen is the cheap gate only: the throttle
   path (compounding/margin) matters live and no engine run is claimed.
   All five years were available when the rule was frozen (assignment);
   needs prospective validation.

## One-line verdict

NOT PROMISING: the dominance-momentum alt-dip throttle (x0.5 iff ddom >
pre-anchor q67) gains in 4/5 years sequentially and 5/5 LOYO but deepens
the worst day in 2/5 years (tail 3/5 < 4/5) - do not throttle alt dips on
ddom without a tail guard, direction closed pending one.
