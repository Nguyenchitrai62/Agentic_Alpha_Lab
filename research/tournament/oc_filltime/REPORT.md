# oc_filltime REPORT: fill-minute timing, staleness of the 24h high, weak-breadth count

Universe: majors (BTC/ETH/SOL/BNB/XRP) x R2 depths (2.5/3/3.5/4/5), 6876 fills,
outcome y1.0 (fill mean, bps). Anchor years start each 2021-09-24 .. 2025-09-24
(n = 990/1045/1330/989/1144). Features from majors 1m (one coin at a time,
float32): f = fill offset 16..238; age24 = minutes since the fill coin's
trailing 1440-min high at minute f-1 (coverage 100%); n_weak = # of OTHER
majors with close(f-1) <= bar-open x (1 - 2.5 sigma_4h), v293 sigma (coverage
98% overall, 100% inside the 5 anchor years — all NaNs predate 2021-09-24).
LATE = f >= 209 (last 30 fillable minutes, 16.0% of fills).

## Verdict

PROMISING (as assigned, fixed window only): LATE fills lose RELATIVE to early
fills in 4/5 years with 4/5 LOYO sign agreement. NOT promising per the rule:
the continuous f / age24 / n_weak features (LOYO tercile spreads 3/5 each).
Late fills still average POSITIVE y1.0 in 4/5 years — this is a relative drag
(-10..-39 bps vs early), not an absolute loser — and 2025-26 flips (+18.5).
Context/sizing input at most; needs prospective validation.

## Tables

Spearman IC(feature, y1.0) per anchor year (p in brackets):
feature 21-22          22-23          23-24          24-25          25-26          | IC sign
f       -0.195 (~0)    -0.177 (~0)    -0.216 (~0)    -0.241 (~0)    -0.190 (~0)    | 5/5 (-)
age24   +0.085 (0.008) +0.004 (0.91) -0.035 (0.20)  +0.054 (0.090) +0.128 (~0)   | 4/5 (+)
n_weak  +0.004 (0.89)  +0.006 (0.84) +0.096 (0.0005)+0.026 (0.42)  +0.107 (0.0003)| 5/5 (+)

Mean y1.0 by tercile, bps [lo n / mid n / hi n], cut-offs from PREVIOUS data only:
f      21-22: +24 (327) / +73 (322) / +19 (341)
f      22-23: -12 (389) / +15 (331) / +11 (325)
f      23-24: +42 (464) / +50 (504) / +21 (362)
f      24-25: +56 (267) / +33 (369) / +39 (353)
f      25-26: -18 (306) / +38 (370) / +15 (468)
age24  21-22: +35 (282) / +40 (407) / +38 (301)
age24  22-23: +21 (373) / -18 (294) / +3 (378)
age24  23-24: +46 (475) / +48 (362) / +27 (493)
age24  24-25: +41 (336) / +41 (284) / +41 (369)
age24  25-26: +2 (310) / +3 (380) / +30 (454)
n_weak 21-22: +44 (417) / +22 (314) / +47 (259)
n_weak 22-23: +1 (514) / -2 (338) / +22 (193)
n_weak 23-24: +47 (655) / +29 (390) / +37 (285)
n_weak 24-25: +37 (457) / +54 (324) / +30 (208)
n_weak 25-26: +8 (442) / +13 (354) / +21 (348)

LOYO tercile spread = mean(y1.0|Hi) - mean(y1.0|Lo), bps (training = other 4 years):
held-out f      age24   n_weak
21-22    -5.3    +5.0    +2.7
22-23    +24.8   -28.8   +21.1
23-24    -18.7   -10.5   -10.4
24-25    -24.2   +0.9    -6.4
25-26    +32.7   +27.6   +12.7
sign     3/5 (-) 3/5 (+) 3/5 (+) -> all FAIL the >=4/5 bar

LATE (f >= 209) vs early, per year (spread = mean_late - mean_early, bps):
year   n_late/n_early mean_late mean_early spread  win_late/win_early
21-22  174/816        +25.2     +40.9      -15.8   0.575/0.712
22-23  178/867        -4.8      +5.5       -10.3   0.517/0.731
23-24  164/1166       +12.3     +43.5      -31.3   0.665/0.788
24-25  141/848        +7.9      +46.6      -38.8   0.511/0.730
25-26  246/898        +27.9     +9.5       +18.5   0.606/0.669
LOYO sign agreement (held-out vs pooled other-4): 4/5 (only 2025-26 disagrees).
Rule: neg spread 4/5 AND agree 4/5 -> PROMISING (late loses, relatively).

Descriptive LATE x n_weak (NOT part of the rule): late&n>=2 vs late&n<2 mean
bps = 21-22: +35.5/+17.7; 22-23: -21.0/+7.3; 23-24: -33.3/+42.9;
24-25: +24.3/-4.0; 25-26: +32.2/+23.4 — sign flips both ways, no stable
amplification of the late drag by weak breadth.

## Caveats / post-hoc log

1. No post-hoc change to definitions, universe, cut-offs, or the decision
   rule. Only addition after the first run: the descriptive late-by-n split
   and win rates (rule untouched).
2. The LATE flag passes 4/5 on a 5-year rule whose 5th year flips hard
   (+18.5 on the largest late-n, 246). First-four-year sensitivity (repo
   selection uses 2021-2024): neg 4/4, agree 4/4 — the flag is stable until
   2025-26. Do not size on it without prospective data.
3. Late fills are losers only RELATIVELY: mean_late > 0 in 4/5 years and
   win_late > 50% every year. Skipping late fills saves a -10..-39 bps drag
   vs early fills, not an absolute loss (except 2022-23, -4.8 bps).
4. Continuous-f terciles are hump-shaped (mid often best; early fills also bad
   in 22-23 and 25-26), which is why the strong 5/5 IC fails the tercile-LOYO
   readout (3/5). The effect is real but not a monotone gate.
5. age24/n_weak ICs are tiny (<= 0.13) and LOYO-negative; n_weak's 5/5 IC sign
   rests on three near-zero years (+0.004/+0.006/+0.026) — noise, not signal.
6. Causality: f from fills; age24/n_weak use only minutes <= f-1 plus
   bar-open O/sigma (truncation-tested); tercile/LOYO cut-offs never see the
   test year; no minute at/after 2026-09-24 00:00 UTC is used. All five years
   are research data per the assignment; any use needs prospective validation.

## One-line verdict

PROMISING (as assigned): fills in the last 30 fillable minutes (f >= 209) trail
early fills by 10-39 bps in 4/5 years (4/5 LOYO agreement, win rate lower 5/5),
but stay positive on average and flip in 2025-26 — a relative-drag sizing input,
not a skip rule; f/age24/n_weak as continuous features fail (LOYO 3/5 each).
