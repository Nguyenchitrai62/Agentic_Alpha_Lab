# oc_idea7 REPORT: VRP-regime dip BUDGET dial (IDEAS.md idea #7)

Universe: majors (BTC/ETH/SOL/BNB/XRP) x R2 depths (2.5/3/3.5/4/5), 5498
fills, outcome y_dep (exact net at deployed TP, fees + adverse funding
inside). Anchor years start each 2021-09-24 .. 2025-09-24
(n = 990/1045/1330/989/1144). Market-wide BTC VRP_z per 4h bar T = 90d z of
(BTC DVOL asof - rv30 from hourly closes), strict end<T as-of; sleeve
multiplier m = {1.25 if VRP_z > q67, 0.75 if <= q33, else 1.0}, cut-offs
from strictly previous data (year-1 pool 113 rows, 2021-06-30..2021-09-24,
same 113 as oc_dvol). size_new = size_dep x m(T), scored with
harness5 equal-exposure renormalisation per year (timing only).
Coverage 100% in all 5 years. No new data fetched (DVOL panel + hourly
already in repo); no 1m loaded; one process, peak RAM ~0.4 GB.

## Verdict

NOT PROMISING under the pre-registered rule: gain 4/5 sequential, LOYO gain
4/5, but worst-day not-worse only 2/5. The 2022-23 bear year kills it:
the hi-VRP_z bucket (1.25x budget) averages -63 bps vs +61 bps mid, so the
dial up-spends into the worst outcomes (gain -0.74, worst day -1.91 -> -2.53,
raw retention 0.19). Same failure mode as v414 (sizing into fear adds DD),
now confirmed at the sleeve-budget layer. Direction holds in 4/5 years but
the tail clause fails.

## Tables

Sequential screen (cut-offs from strictly previous data; renorm sizes):

year    n     q33/q67        shares lo/mid/hi  S_dep   S_new   gain    pass?
21-22   990   0.38/1.10      0.47/0.26/0.27    4.485   5.052   +0.567  YES
22-23   1045  -0.13/0.86     0.48/0.25/0.27    0.924   0.181   -0.743  NO
23-24   1330  -0.36/0.78     0.26/0.37/0.37    6.627   6.798   +0.170  YES
24-25   989   -0.24/0.85     0.30/0.47/0.23    4.265   4.432   +0.167  YES
25-26   1144  -0.22/0.83     0.48/0.26/0.26    1.906   2.108   +0.202  YES
(units native size*y_dep; S_dep > 0 every year.)

Worst daily sum (renormalised sizes, grouped by floor(T) day):

year    W_dep    W_new    tail pass?  raw retention (descriptive)
21-22   -0.434   -0.341   YES         1.07
22-23   -1.915   -2.532   NO          0.19
23-24   -0.577   -0.472   YES         1.05
24-25   -0.703   -0.720   NO          1.01
25-26   -0.498   -0.531   NO          1.04

LOYO gain (cut-offs from the other 4 years, renorm inside held-out):

held-out  q33/q67       gain    pass?
21-22     -0.30/0.78    +0.177  YES
22-23     -0.24/0.82    -0.805  NO
23-24     -0.36/0.76    +0.232  YES
24-25     -0.32/0.82    +0.174  YES
25-26     -0.22/0.83    +0.202  YES

Mean y_dep by budget bucket, bps (descriptive, sequential cut-offs):

year    lo (0.75x)  mid (1.0x)  hi (1.25x)
21-22   +28.1       +8.1        +90.4
22-23   +18.0       +60.8       -63.2
23-24   +46.7       +36.9       +52.5
24-25   +45.0       +26.9       +73.6
25-26   +15.9       -20.3       +41.0
(Spearman VRP_z vs y_dep per year: +0.13/+0.03/+0.07/+0.03/+0.12 —
same sign 5/5 but weak; bucket profiles non-monotonic in 2025.)

## Caveats / post-hoc log

1. One pre-registered code fix after the first run (logged here, before
   REPORT): the cut-off training pool initially required size_dep, which
   starts at 2021-09-24, leaving year 1 with n_train = 0 and a degenerate
   all-1.0 multiplier. Fixed to the PLAN definition (majors x R2 grid rows,
   no size_dep needed): year-1 n_train = 113, matching oc_dvol's 113.
   No change to hypothesis, definitions, multipliers, or the decision rule.
2. The failure is concentrated, not marginal: 2022 fails gain sequentially
   AND LOYO, fails tail, and inverts the bucket ordering (hi worst). 2024
   and 2025 pass gain but shave the worst day (1.25x lands on a crash day)
   — the tail clause binds exactly where sizing-into-fear hurts.
3. Year-1 cut-offs train on 113 summer-2021 rows (q33/q67 = 0.38/1.10,
   elevated post-crash baseline); the 21-22 pass should not be
   over-interpreted.
4. Rung-level equal-exposure screen is the cheap gate only: the budget path
   (compounding/margin) matters live and no engine run is claimed. Raw
   retention is descriptive, not part of the rule.
5. Realised vol uses hourly aggregation (pre-registered LIGHT equivalent of
   1m; 30d window). Strict end<T as-of verified by test (truncate +
   recompute). All five years are research data; needs prospective
   validation.

## One-line verdict

NOT PROMISING: the VRP budget dial gains in 4/5 years sequentially and 4/5
LOYO but deepens the worst day in 3/5 (2/5 not-worse) and inverts in the
2022 bear year (hi-bucket -63 bps, gain -0.74) — compensation timing does not
survive the tail clause.
