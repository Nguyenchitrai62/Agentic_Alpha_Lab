# oc_idea3 REPORT: pre-bar intraday-RV skip (IDEAS.md #3)

Universe: majors (BTC/ETH/SOL/BNB/XRP) x R2 depths (2.5/3/3.5/4/5), 6876
fills, outcome y1.0 (unit rung size). Anchor years by T start each
2021-09-24 .. 2025-09-24 (n = 990/1045/1330/989/1144). RV15(c,T) =
(max high[0..15] - min low[0..15]) / (O(T) * sigma_4h(T)), sigma_4h = v293
(pct_change().rolling(360).std(ddof=1).shift(1) on 4h opens); SKIP iff
RV15 > prior-year q80 (walk-forward, feature quantiles only). 3022/6876
rows SKIP=1 (44%); coverage 100%. Thresholds q80 =
0.671/0.554/0.461/0.538/0.504 (n_train ~10950 (coin,bar) each).

## Verdict

NOT PROMISING per the pre-registered rule: flagged-minus-kept spread sign
2/5 negative (needs >= 4/5) and LOYO negative 2/5. Skipping high-RV15 opens
cuts 42-137% of each year's sum (kept-share only 36-54%: fills concentrate
in volatile opens) while the worst day improves 4/5. No RV15 skip/filter is
supported; close the direction.

## Tables

Per-year SKIP=1 (flagged) vs SKIP=0 (kept), y1.0 in bps:
year   n_skip/n_keep mean_skip mean_keep spread  win_skip/win_keep min_skip/min_keep
21-22  503/487       +56.7     +19.0    +37.8   0.789/0.583        -1444/-457
22-23  485/560       +11.1      -2.6    +13.7   0.728/0.666        -1372/-2210
23-24  847/483       +31.7     +53.7    -22.1   0.778/0.764        -1505/-941
24-25  563/426       +30.4     +55.3    -24.9   0.682/0.721        -1353/-362
25-26  624/520       +17.4      +8.8     +8.6   0.710/0.590        -1195/-1010
sign: 3 positive, 2 negative -> negative 2/5 = FAIL (>= 4/5 needed).

LOYO (re-learned q80 on other-4 years, spread in the held-out year, bps):
held-out  q80_loyo n_skip spread_loyo negative?
21-22     0.504    622    +39.8       no
22-23     0.528    498    +17.2       no
23-24     0.511    783    -21.9       yes
24-25     0.518    583    -25.4       yes
25-26     0.517    620     +8.2       no
negative 2/5 = FAIL. Overall pooled spread -14.2 bps (29.3 vs 43.5).

Skip simulation per year (unit size; cut = fraction of yearly sum given up):
year   S_full S_skip cut     worst_day_full worst_day_skip tail?
21-22  3.777  0.923  +0.756  -0.430         -0.282         yes
22-23  0.393 -0.145  +1.368  -1.924         -1.924         no
23-24  5.276  2.595  +0.508  -0.496         -0.147         yes
24-25  4.066  2.355  +0.421  -0.507         -0.071         yes
25-26  1.538  0.455  +0.704  -1.018         -0.347         yes
Tail improves 4/5 (passes alone), but every year gives up 42-137% of the sum
(2022: a small positive year turns negative); kept-share 49/54/36/43/45%.
Per-coin spreads flip within years (e.g. 2021: +87/+74/+76/+30/-90) - no coin
carries the effect.

## Caveats / post-hoc log

1. No post-hoc change to RV15, thresholds, universe, outcome, minimum-n, or
   the decision rule. One code fix (missing `main()` call: first two runs
   exited 0 with no output, before any result existed) fired before any
   outcome was produced.
2. The q80-over-bars design skips ~20% of BARS but ~44% of FILLS overall
   (up to 64% in 2023): fills adversely select into volatile opens, so the
   "cheap 20% filter" is really a ~half-the-book cut. A higher quantile would
   keep more book but the spread sign already flips, so no threshold rescues it.
3. Effect sizes (+/-9..38 bps) sit near the ~4-8 bps cost scale but with
   flipping signs they are noise, not edge. First-four-year sensitivity
   (repo selection uses 2021-2024): spreads +38/+14/-22/-25 = 2/2 split,
   LOYO 2/4, tail 3/4 - still a clear fail; the 2025 year changes nothing.
4. Causality: RV15 uses only minutes 0..15 (before minute 16, the first fill);
   sigma uses 4h opens up to T (v293 shift(1)); thresholds use strictly
   pre-anchor (coin,bar) with no outcome read (flag-recompute test drops all
   y-columns). No minute at/after 2026-09-24 is used. All five years are
   research data per the assignment; this negative finding needs no
   prospective follow-up beyond keeping the direction closed.

## One-line verdict

NOT PROMISING: high-RV15-open dip fills differ from quiet-open fills with
flipping signs (+38/+14/-22/-25/+9 bps, LOYO 2/5) and skipping them cuts
42-137% of each year's sum - no intraday-RV filter; close the direction.
