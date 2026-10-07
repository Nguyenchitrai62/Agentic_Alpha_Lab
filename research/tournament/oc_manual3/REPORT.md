# oc_manual3 REPORT: STATIC placement-time proxy for v399-B1 dip sizing (idea #15)

Universe: majors (BTC/ETH/SOL/BNB/XRP) x R2 depths (2.5/3/3.5/4/5), 5498
TEST fills, outcome y_dep (exact net at deployed TP, fees + adverse funding
inside). Anchor years start each 2021-09-24 .. 2025-09-24
(n = 990/1045/1330/989/1144; S_a and W_a match oc_idea7 to the tick).
n per fill recomputed exactly as v399-B1 (C[f-1] <= O[0] x (1 - 2.5 sig4),
sig4 = 4h-open rolling(360,min120) std, O = 1m open at T, C = 1m close at
T+f-1 with within-bar ffill) from 1m read one coin-year at a time
(v399_runs.pkl stores only equity paths, no per-fill n, so nothing was
reused). Static m(c,d) = walk-forward mean of 1/(1+n) over majors-R2 fills
with t_fill < anchor - 7d (min 30 cells else pooled depth mean else 1.0;
6876 grid rows; n_train = 1345/2335/3401/4743/5704). Arms (a)/(b)/(c) =
size_dep / size_dep x m(c,d) / size_dep x 1/(1+n), renormed per year to equal
mean exposure; maxDD of the cumsum of calendar-day sums from 0.
One process, peak RAM ~0.3 GB (one yearly 1m file at a time).

## Verdict

NOT PROMISING under the pre-registered rule: 0/5 years PASS (needs >= 4/5).
The dynamic BOT reference itself reduces screen-maxDD in only 2/5 years
(2022: 1.91 -> 1.40; 2024: 0.70 -> 0.33) and deepens it in 3/5 under
equal-exposure renormalisation; where it does help, the static proxy
recovers 2% (2022) and 25% (2025), and goes the wrong way in 2024 (-4%).
Correlation risk is episodic, not a fixed per-(coin, depth) trait: mean
y_dep by n bucket has no consistent sign across years (n = 4 is best in
2021/2023/2025, worst in 2024, flat in 2022), so a placement-time constant
cannot price it.

## Tables

Per-year screen (renormalised sizes; native size*y_dep units):

year    n     S_a     S_b     S_c     W_a     W_b     W_c     DD_a   DD_b   DD_c   rec     pass?
21-22   990   4.485   3.964   4.393   -0.434  -0.584  -0.738  0.539  0.584  0.738  --      NO (dyn deepens)
22-23   1045  0.924   0.997   1.015   -1.915  -1.903  -1.076  1.915  1.903  1.398  0.022   NO (< 0.50)
23-24   1330  6.627   6.382   6.696   -0.577  -0.665  -0.635  0.577  0.665  0.635  --      NO (dyn deepens)
24-25   989   4.265   4.006   4.323   -0.703  -0.716  -0.333  0.703  0.717  0.333  -0.040  NO (static deepens)
25-26   1144  1.906   1.704   1.649   -0.498  -0.480  -0.480  0.588  0.576  0.538  0.247   NO (< 0.50)
(-- = recovery undefined: dynamic gives no maxDD reduction to recover.)

Static haircut m(c,d), walk-forward means (rows coins BTC/ETH/SOL/BNB/XRP):

year    2.5             3.0             3.5             4.0             5.0
21-22   .76/.77/.73/.74/.82  .60/.57/.78/.63/.76  .53/.46/.56/.58/.74  .48/.41/.51/.47/.72  .36/.36/.24/.45/.67
22-23   .76/.77/.73/.71/.79  .62/.62/.65/.59/.73  .51/.50/.50/.53/.69  .44/.42/.47/.44/.66  .32/.30/.25/.38/.58
23-24   .77/.78/.75/.72/.79  .63/.64/.66/.62/.71  .51/.50/.58/.54/.67  .42/.43/.58/.49/.62  .30/.31/.52/.47/.56
24-25   .77/.77/.75/.74/.80  .64/.65/.66/.63/.72  .52/.52/.56/.54/.68  .43/.43/.56/.48/.63  .31/.33/.48/.46/.57
25-26   .77/.77/.74/.75/.80  .64/.65/.64/.63/.72  .51/.52/.54/.54/.67  .43/.43/.54/.49/.62  .33/.32/.45/.46/.57
(Deeper rungs earn bigger haircuts — they fill in bigger flushes — and the
table is stable across anchors; year 1 used 104 pooled fallbacks, later
years 30/0/0/0. Mean m ~0.64-0.66.)

Mean y_dep by flush-breadth n, bps (descriptive; no consistent pattern):

year    n=0    n=1    n=2    n=3    n=4
21-22   +45    +12    +35    +55    +52
22-23   +5     +22    -22    +38    -2
23-24   +50    +34    +32    +68    +35
24-25   +38    +53    +67    +65    -39
25-26   +10    +10    +13    +7     +32

n distribution per year, fills (descriptive):
21-22: 0:422 1:177 2:135 3:117 4:139 | 22-23: 0:515 1:189 2:151 3:102 4:88
23-24: 0:659 1:227 2:160 3:138 4:146 | 24-25: 0:460 1:183 2:138 3:139 4:69
25-26: 0:443 1:203 2:147 3:182 4:169

## Caveats / post-hoc log

1. Two pre-REPORT code fixes, both before REPORT.md existed and neither
   touching hypothesis, definitions, or rule: (a) the first script draft
   defined main() but never called it (ran zero work, wrote nothing); added
   the `__main__` guard. (b) Extracted pure helpers count_n_row /
   maxdd_of_cumsum / recovery_and_pass with byte-identical logic and
   re-ran: numbers identical to the first successful run.
2. Screen-vs-engine gap (expected, pre-registered as cheap gate only): the
   equal-exposure renormalisation re-levers exactly the crash-day exposure
   cut that drives v399's engine DD win (25.05 -> 13.88 with compounding,
   book, margin). So the dynamic reference can deepen screen-DD while
   helping engine-DD; the screen tests ALLOCATION only. Even so, the static
   proxy recovers ~nothing where the dynamic allocates well (2022/2024).
3. SOL coverage 0.98 (history starts 2020-09-14; early NaN-sig coins are
   skipped exactly as v399 skips them); all other coins 1.00. No 1m bar at
   or after 2026-09-24 00:00 UTC was read (files filtered to < DEV_END).
4. All five years are research data; any finding needs prospective
   validation. No engine run is claimed here.

## One-line verdict

NOT PROMISING: the static per-(coin, depth) proxy passes 0/5 years — the dynamic rule itself cuts screen-maxDD in only 2/5 years under equal exposure, and there the static recovers just 2% (2022) and 25% (2025); flush risk is episodic, not a fixed cell trait.
