# oc_b1btc REPORT: BTC-weighted correlation count for B1 (idea #20)

Universe: majors (BTC/ETH/SOL/BNB/XRP) x R2 depths (2.5/3/3.5/4/5), 5498
TEST fills, outcome y_dep (exact net at deployed TP, fees + adverse funding
inside), sizes from deployed table (harness5.load). Anchor years start each
2021-09-24 .. 2025-09-24 (n = 990/1045/1330/989/1144). n per fill REUSED from
oc_manual3 n_per_fill.parquet (v399-exact 2.5-sigma; join on
sym/x1/T/t_fill/f, full 5498 coverage, n in 0..4); btc_det recomputed EXACTLY
as v399 for the BTC leg only from BTC 1m (one yearly file at a time,
O = 1m open at T no ffill, C = 1m close at T+f-1 with within-bar ffill,
sig4 = 4h-open rolling(360,min120).std; BTC leg coverage 1.00/1.00/1.00).
Consistency exact: 0 non-BTC rows with btc_det=1 and n=0 (BTC counted in n);
agreement with oc_b1shape btc_det (no-ffill variant) 1.0000 — ffill never
binds in the TEST window. Arms B1 = size_dep/(1+n) vs B1-BTC =
size_dep/(1+n_btc) (n_btc = n+btc_det non-BTC, else n), renormed per year to
mean(size_dep); S/W/maxDD of daily-sum path as pre-registered. S_a matches
oc_manual3's dynamic B1 to the tick (4.393/1.015/6.696/4.323/1.649).
One process, peak RAM ~0.3 GB; only BTC 1m files read; no bar at/after
2026-09-24 00:00 UTC used.

## Verdict

NOT PROMISING under the pre-registered rule: gain>0 in 3/5 years (needs
>= 4/5), LOYO_gain>0 in 2/5, maxDD not-worse in 2/5. The extra BTC shrink
adds +0.04/+0.03/+0.06 in 2021/2024/2025 but loses -0.11/-0.03 in 2022/2023,
and deepens screen-maxDD in 3/5 years (2021: 0.74 -> 0.77; 2022:
1.40 -> 1.46; 2023: 0.64 -> 0.66) while improving it only in 2024/2025.
BTC-flush fills underperform alt-only fills in 3/5 years but outperform in
2/5 (2022/2023), so the leader-follow-through premise is not stable.

## Tables

Per-year B1 vs B1-BTC (renormalised sizes; native size*y_dep units):

year    n     S_a     S_b     gain    pass?  W_a     W_b     DD_a   DD_b   dd<=?
21-22   990   4.393   4.437   +0.044  YES    -0.738  -0.769  0.738  0.769  NO
22-23   1045  1.015   0.908   -0.107  NO     -1.076  -1.090  1.398  1.463  NO
23-24   1330  6.696   6.670   -0.026  NO     -0.635  -0.657  0.635  0.657  NO
24-25   989   4.323   4.350   +0.027  YES    -0.333  -0.323  0.333  0.323  YES
25-26   1144  1.649   1.705   +0.056  YES    -0.480  -0.486  0.538  0.527  YES

LOYO stability (mean gain over the other 4 years; no fitted params):

held-out  LOYO_gain  pass?
21-22     -0.013     NO
22-23     +0.025     YES
23-24     +0.005     YES
24-25     -0.008     NO
25-26     -0.015     NO

Bucket outcomes per year, y_dep>0 win rate / mean y_dep bps (descriptive):

year    BTC-flush (n, wr, bps)     alt-only (n, wr, bps)       isolated / BTC-own
21-22   264, 65.2%, +38.4          183, 69.4%, +47.7           334, 68.6%, +43.8 / 209, 65.1%, +28.0
22-23   240, 70.8%, +45.9          175, 66.9%, -25.5           428, 69.9%, +0.3 / 202, 67.8%, +1.7
23-24   313, 79.6%, +48.2          212, 70.8%, +28.4           537, 79.1%, +53.7 / 268, 72.0%, +38.1
24-25   212, 67.5%, +20.7          223, 75.8%, +83.7           389, 66.6%, +37.9 / 165, 66.1%, +29.0
25-26   398, 65.6%, +4.7           171, 69.6%, +38.1           352, 67.6%, +16.4 / 223, 59.2%, +3.4
(BTC-flush = non-BTC fills with BTC among flushers; alt-only = non-BTC with
n >= 1 but no BTC; BTC-flush worse in 2021/2024/2025, better in 2022/2023.)

n histogram per year (descriptive; btc_det share of TEST fills):
21-22: 0:422 1:177 2:135 3:117 4:139, btc 26.7% | 22-23: 0:515 1:189 2:151
3:102 4:88, btc 23.0% | 23-24: 0:659 1:227 2:160 3:138 4:146, btc 23.5% |
24-25: 0:460 1:183 2:138 3:139 4:69, btc 21.4% | 25-26: 0:443 1:203 2:147
3:182 4:169, btc 34.8%.

## Caveats / post-hoc log

1. One plumbing fix after the first run (before REPORT): the descriptive
   b1shape cross-check joined without the depth key and failed one-to-one
   validation (two rungs can share a fill minute); fixed to join on
   sym/x1/T/t_fill/f with validate="one_to_one" — agreement 1.0000. No
   change to hypothesis, definitions, arms, renormalisation, or the
   decision rule; scores identical across both runs.
2. Screen-vs-engine gap (expected, pre-registered as cheap gate only): the
   equal-exposure renormalisation re-levers the crash-day exposure cut, as
   in oc_manual3; the screen tests ALLOCATION only, no engine run claimed.
3. This re-tests oc_b1shape S3's formula with deployed weights and y_dep
   (there: 4/5 yearly-S wins on y1.0 flat but worse tails); here with
   size_dep x y_dep the yearly edge itself falls to 3/5 and tails to 2/5.
4. All five years are research data; any finding needs prospective
   validation.
5. Extra artifact (disclosed): `n_btc_per_fill.parquet` (5498 TEST rows:
   sym/x1/T/t_fill/f/size_dep/y_dep/n/btc_det/n_btc) is written alongside
   results.json so the causality tests verify the join without re-reading
   1m; not in PLAN's deliverable list, no effect on scores.

## One-line verdict

NOT PROMISING: B1-BTC beats B1 in only 3/5 years (LOYO 2/5) and deepens screen-maxDD in 3/5 (2/5 not-worse) — BTC-inclusive flushes underperform alt-only flushes in 3/5 years but outperform in 2022/2023, so the extra BTC shrink is not a stable improvement.
