# oc_weekend REPORT: weekend dip tilt (IDEAS.md idea #18)

Universe: majors (BTC/ETH/SOL/BNB/XRP) x R2 depths (2.5/3/3.5/4/5) with
size_dep, 5498 fills, outcome y_dep (exact net at deployed TP, fees +
adverse funding inside). Anchor years start each 2021-09-24 .. 2025-09-24
(n = 990/1045/1330/989/1144). Weekend = holding-bar open T with
Sat 00:00 <= T < Mon 00:00 UTC (dayofweek 5/6, T = t_fill - f, 4h-aligned,
known at bid time). Fixed tilt m = 1.25 weekend / 0.90 weekday,
size_new = size_dep x m(T), scored with harness5 equal-exposure
renormalisation per year (timing only). No hourly/1m loaded; one process,
peak RAM ~0.3 GB. Market data to 2026-09-24 00:00 UTC read per assignment
(all five years research data; needs prospective validation).

## Verdict

NOT PROMISING under the pre-registered rule: weekend-minus-weekday spread
> 0 in only 2/5 sequential years, LOYO pooled spread > 0 in only 3/5, tail
not-worse 4/5. The sign flips: 2021-23 weekends average WORSE (-31/-20/-3
bps spread) and only 2024-25 weekends average better (+29/+13 bps). No
post-hoc change (single fixed pair, computed once).

## Tables

Per anchor year — weekend vs weekday (per-fill y_dep) and tilt outcome:

year    n    wknd n/share   mean wknd  mean wkday  spread  spread?  win wknd  win wkday
21-22   990  162 / 0.164   +13.7 bps  +44.9 bps   -31.2 bps  NO     65.4%     67.4%
22-23   1045 107 / 0.102   -10.9 bps  +8.8 bps    -19.6 bps  NO     65.4%     69.6%
23-24   1330 143 / 0.108   +42.2 bps  +45.6 bps   -3.4 bps   NO     68.5%     77.4%
24-25   989  164 / 0.166   +67.4 bps  +38.2 bps   +29.2 bps  YES    69.5%     68.6%
25-26   1144 224 / 0.196   +23.2 bps  +10.6 bps   +12.6 bps  YES    69.2%     64.7%
(bps = mean y_dep x1e4; spread = wknd - wkday.)

Tilted vs base (renormalised sizes, harness5 convention):

year    S_dep   S_new   gain    raw retention  worst day dep -> new  tail?  maxDD dep -> new
21-22   4.485   4.308   -0.177  0.92           -0.434 -> -0.568      NO     0.539 -> 0.568
22-23   0.924   0.928   +0.004  0.94           -1.915 -> -1.842      YES    1.915 -> 1.855
23-24   6.627   6.599   -0.029  0.93           -0.577 -> -0.555      YES    0.577 -> 0.555
24-25   4.265   4.399   +0.134  0.99           -0.703 -> -0.661      YES    0.703 -> 0.661
25-26   1.906   1.981   +0.075  1.00           -0.498 -> -0.465      YES    0.588 -> 0.538
(gain descriptive only, not part of the rule.)

LOYO pooled spread (other 4 years, unweighted fills):

held-out  train wknd/wkday n   pooled spread  pass?
21-22     638 / 3870           +6.3 bps       YES
22-23     693 / 3760           +0.1 bps       YES
23-24     657 / 3511           +1.7 bps       YES
24-25     636 / 3873           -8.9 bps       NO
25-26     576 / 3778           -3.2 bps       NO

Per-coin spread (bps, wknd - wkday; descriptive): 21-22 all negative except
SOL (+39); 22-23 mixed (BTC +42, XRP +37, others negative); 23-24 BTC/ETH/
SOL positive, BNB/XRP negative; 24-25 negative only BTC (-37); 25-26
negative BTC/ETH, positive SOL/BNB/XRP. No coin holds the sign 5/5.

## Caveats / post-hoc log

1. No post-hoc change: one fixed multiplier pair, one run, no tuning.
2. Weekend fills are scarce (10-20% of fills per year; 2022-23 only 107
   weekend fills), so yearly spreads are noisy; the pooled 5y spread is
   near zero (-0.8 bps overall) and LOYO pools sit within +/-9 bps.
3. Effect size vs cost: yearly spreads (-31..+29 bps per-fill mean) bracket
   the ~4-8 bps round-trip cost inside y_dep, but the sign is unstable, so
   no edge is claimed.
4. Rung-level equal-exposure screen is the cheap gate only; budget path
   (compounding/margin) matters live and no engine run is claimed.

## One-line verdict

NOT PROMISING: weekend-minus-weekday spread positive in only 2/5 years and
3/5 LOYO pools (tail 4/5) — weekend fills average worse in 2021-23 and the
fixed 1.25x/0.90x tilt has no stable timing edge.
