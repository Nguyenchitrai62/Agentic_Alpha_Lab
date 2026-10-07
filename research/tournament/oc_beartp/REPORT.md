# oc_beartp REPORT: bear-regime faster dip take-profit (idea #14)

Universe: majors (BTC/ETH/SOL/BNB/XRP) x R2 depths (2.5/3/3.5/4/5), 5498
fills, sizes fixed at size_dep. Regime = v410 bear flag: BTC 4h open[T] <
mean of last 1200 4h opens incl. T (min 600; hourly_ext BTC opens on the
00/04/08/12/16/20 UTC grid; NaN-MA -> non-bear), causal at the bar open.
Rule (fixed, zero fitted params): bear bars -> TP 0.5 sigma (y0.5);
non-bear -> deployed tp_dep/y_dep. Outcomes exact net (fees + adverse
funding inside) via harness5.load. Anchor years start each
2021-09-24 .. 2025-09-24 (n = 990/1045/1330/989/1144). No 1m loaded; one
process, peak RAM < 1 GB.

## Verdict

NOT PROMISING under the pre-registered rule: maxDD not worse in 4/5 years
but the yearly sum is lower in all 5 years (0/5 not-lower). Faster TP in
bear bars lifts the rung win rate every year yet gives up the deployed
rungs' upside (mean y_dep > y0.5 on every cohort), so the DD relief
(4/5, two ties) is bought with a sum loss in 5/5.

## Tables

Per anchor year (T in [anchor, anchor+365d); sums native size*y units):

year    n     n_bear  share   changed  S_dep   S_new   gain     sum_ok?
21-22   990   816     0.824   0.796    4.485   3.641   -0.844   NO
22-23   1045  388     0.371   0.335    0.924   0.357   -0.566   NO
23-24   1330  288     0.217   0.211    6.627   6.556   -0.072   NO
24-25   989   80      0.081   0.079    4.265   4.196   -0.069   NO
25-26   1144  840     0.734   0.714    1.906   1.446   -0.460   NO
(gain bps x1e4: -8436 / -5664 / -716 / -693 / -4598.)

Win rate (unweighted mean(y>0), all rungs; bear-only in brackets):

year    win_dep        win_new        bear y0.5-y_dep mean
21-22   0.671 (0.656)  0.796 (0.808)  -0.000901
22-23   0.692 (0.802)  0.726 (0.894)  -0.001669
23-24   0.765 (0.722)  0.790 (0.840)  -0.000386
24-25   0.688 (0.650)  0.700 (0.800)  -0.000677
25-26   0.656 (0.664)  0.747 (0.788)  -0.000718
(win rises in 5/5, but the bear-rung mean outcome falls in 5/5.)

Worst day (min daily sum by floor(T) day) and path maxDD (max(peak-cum)
of the cumulative daily-sum path from 0, native units):

year    W_dep    W_new    DD_dep   DD_new   dd_ok?
21-22   -0.434   -0.434   0.539    0.434    YES
22-23   -1.915   -1.915   1.915    1.915    YES (tie)
23-24   -0.577   -0.559   0.577    0.559    YES
24-25   -0.703   -0.703   0.703    0.703    YES (tie)
25-26   -0.498   -0.498   0.588    0.606    NO
(S_dep/S_new/gain cross-checked equal to harness5.score_tp to 4dp.)

## Caveats / post-hoc log

1. No post-hoc changes: PLAN.md was written before any outcome was
   computed; the script ran once with the frozen rule (no variant search).
2. Zero fitted parameters, so sequential and leave-one-year-out scoring
   coincide (same fixed rule, no refit); per-year consistency above is the
   stability read.
3. The 4h-open panel comes from hourly_ext only (2020-08-01.., so every
   test T has >= 1200 bars of history except none missing; earliest test T
   2021-09-24 08:00 has ~2520 prior 4h bars). No hourly bar with START >=
   2026-09-24 00:00 UTC is used; all test T are on the 4h grid.
4. y columns are rung-level exact nets; engine path effects
   (compounding/margin/queue) are not modelled — this is the cheap
   rung-level gate only.
5. All five years are research data per the assignment; a NOT PROMISING
   screen needs no prospective validation, and any reuse of this direction
   must pre-register a new variant.

## One-line verdict

NOT PROMISING: bear-bar TP 0.5 sigma cuts path maxDD in 4/5 years but lowers the yearly sum in 5/5 (0/5 not-lower) — faster exits win more rungs yet give up more upside than they save.
