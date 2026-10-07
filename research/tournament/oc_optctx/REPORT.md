# oc_optctx REPORT: options skew / put-call flow / Coinbase premium as dip-rung context

Universe: majors (BTC/ETH/SOL/BNB/XRP) x R2 depths (2.5/3/3.5/4/5), 6876 fills,
outcome y1.0 (fill mean, bps). Anchor years 2021-09-24 .. 2025-09-24
(n = 990/1045/1330/989/1144). PRIMARY: BTC Deribit options features for every
major rung. SECONDARY (descriptive): same 7 features from ETH options on ETH
rungs only (n = 1417). Deribit `bar` is the 4h bar START (floored trades), so
each row covers [bar, bar+4h); all features use bars with END strictly before
T (last usable 4h bar [T-8h,T-4h), last usable hour [T-2h,T-1h)). No bar with
START >= 2026-09-24 00:00 UTC is used. Coverage 100% in all 5 anchor years for
all 7 primary features. Cross-feature Spearman: skew-skew_z 0.90,
share-share_z 0.90, prem_last-prem_mean24 0.86 (z adds little); options vs
premium families ~0 (independent).

## Verdict (per-feature, pre-registered rule: IC>=4/5 AND spread>=4/5 AND resid IC>=4/5)

NOT PROMISING (as assigned): skew (4/5, 3/5, resid 3/5); skew_z90 (4/5, 3/5,
resid 3/5); putbuy_share6 (3/5, 3/5, resid 3/5); putbuy_share6_z90 (3/5 IC
fails; spread 4/5, resid 3/5); cbprem_last (IC 5/5-, resid 5/5-, but spread
3/5); cbprem_mean24 (IC 5/5-, resid 5/5-, but spread 3/5); cbprem_z90 (4/5,
3/5, resid 3/5). Nothing passes all three legs. The Coinbase premium's 5/5
negative IC (lower US-spot premium goes with better dip y1.0) survives DVOL
residualization but its LOYO spreads are sign-unstable and oppose the IC —
no tradable tercile rule. ETH-only put-buy share shows 5/5 IC and 5/5 resid IC
(+) on 1417 rungs but LOYO spreads fail (small samples, sign flips) —
descriptive only, watchlist at most.

## Tables

Spearman IC(feature, y1.0) per anchor year (p in brackets):
feature          21-22          22-23          23-24          24-25          25-26          | IC
skew             +0.024 (0.45) +0.113 (0.00) +0.035 (0.20) -0.069 (0.03) +0.144 (~0)     | 4/5
skew_z90         +0.054 (0.09) +0.042 (0.18) +0.025 (0.36) -0.072 (0.02) +0.156 (~0)     | 4/5
putbuy_share6    +0.085 (0.01) +0.102 (0.00) -0.015 (0.59) -0.082 (0.01) +0.116 (0.00)    | 3/5
putbuy_share6_z  +0.097 (0.00) +0.029 (0.35) -0.052 (0.06) -0.069 (0.03) +0.110 (0.00)    | 3/5
cbprem_last      -0.128 (0.00) -0.061 (0.05) -0.039 (0.15) -0.092 (0.00) -0.113 (0.00)    | 5/5 (-)
cbprem_mean24    -0.169 (~0)   -0.034 (0.27) -0.046 (0.09) -0.101 (0.00) -0.106 (0.00)    | 5/5 (-)
cbprem_z90       -0.044 (0.16) -0.016 (0.61) +0.014 (0.62) -0.026 (0.41) -0.078 (0.01)    | 4/5

LOYO tercile spread = mean(y1.0|Hi) - mean(y1.0|Lo), bps (training = other 4 years):
held-out  skew    skew_z  share6  share6_z premLast premM24 premZ
21-22     -62.1   -25.7   +11.4   +41.9    -38.8    -66.0   -15.5
22-23     +26.7   -35.7   +29.0   -21.0    +99.5   +148.8  +109.4
23-24     +46.6   +18.2   +21.8   -34.5    +17.1    +45.2    -4.5
24-25     -41.8   -22.4   -59.4   -44.3    +34.2    +22.3    +1.8
25-26     +37.3   +46.7   -15.6    -8.9    -57.4    -60.0   -37.5
sign       3/5     3/5     3/5     4/5(-)   3/5      3/5     3/5 -> ALL FAIL (need 4/5)

Residual IC after OLS on DVOL z90 (within-year fit), Spearman(resid, y1.0):
feature          21-22   22-23   23-24   24-25   25-26   | resid IC (resid spread sign, descr.)
skew             -0.063  +0.022  +0.038  -0.070  +0.124  | 3/5 (3/5)
skew_z90         -0.036  -0.056  +0.022  -0.073  +0.142  | 3/5 (3/5)
putbuy_share6    +0.042  +0.049  -0.012  -0.078  +0.095  | 3/5 (3/5)
putbuy_share6_z  +0.071  -0.021  -0.050  -0.067  +0.084  | 3/5 (4/5 descr.)
cbprem_last      -0.035  -0.007  -0.041  -0.066  -0.117  | 5/5 (-) (3/5)
cbprem_mean24    -0.136  -0.017  -0.064  -0.071  -0.102  | 5/5 (-) (3/5)
cbprem_z90       +0.017  +0.072  +0.009  -0.010  -0.067  | 3/5 (3/5)

Mean y1.0 by tercile, bps [lo n / mid n / hi n], cut-offs from PREVIOUS data only:
skew 21-22: +73 (154) / +35 (461) / +28 (375); 22-23: -10 (720) / +44 (155) / +27 (170);
 24-25: +65 (321) / +29 (433) / +30 (235) — profiles flip year to year.
putbuy_share6_z90 24-25: +69 (404) / +42 (269) / +4 (316) but 21-22 inverted:
 +10 (202) / +48 (176) / +45 (612).
cbprem_mean24 22-23: -140 (121) / +62 (361) / -3 (563); 23-24: +24 (681) / +51 (450) /
 +68 (199) — non-monotonic within years, opposite across years; no stable direction.

ETH-only descriptive (ETH options on ETH rungs; BTC-feature reference omitted for
brevity, see results.json): eth_skew IC 4/5 (+0.24/+0.30/+0.19/-0.00/+0.18),
resid 4/5; eth_putbuy_share6 IC 5/5 (+0.10/+0.39/+0.06/+0.04/+0.05), resid 5/5
(+0.05/+0.27/+0.07/+0.05/+0.04) — but LOYO spreads fail (some years < 30/side =
NaN; share_z spreads +46/+62/-38/-31/-22). Small samples; hypothesis only.

## Caveats / post-hoc log

1. No post-hoc change to definitions, universe, or the decision rule. Two
   analysis-script bugfixes were made BEFORE the first successful run (no
   outcome statistic had been seen): the dvol_z90 merge assertion (1250
   pre-2021-09-24 rows are NaN by DVOL warm-up design; assert now checks key
   match + anchor-year coverage) and a tercile-mask broadcasting bug.
2. Premium grid has one 6h step (a Coinbase/Binance hour gap, pre-2021); mean24
   requires >= 20/24 hours; anchor-year coverage is 100% regardless.
3. ETH options IV NaNs (~0.6% put / ~0.2% call bars) are pairwise-dropped;
   primary BTC features have zero IV NaNs.
4. Multiple comparisons: 7 features x 5 years = 35 ICs plus residual/LOYO
   batteries; single-year p-values are nominal. The pre-registered triple
   sign-consistency bar is the actual test — nothing clears it.
5. Causality: strict end<T as-of verified by test (truncate shift + cutoff
   audit); training/LOYO cut-offs never see the test year; no bar starting
   at/after 2026-09-24 00:00 UTC is used. In-sample walk-forward style only;
   needs prospective validation before any use.

## One-line verdict per feature

skew: NOT PROMISING — IC 4/5 but LOYO spreads flip sign yearly (3/5) and the
DVOL-residual IC flips too (3/5). | skew_z90: NOT PROMISING — same failure
(4/5, 3/5, resid 3/5); z adds nothing over raw skew (corr 0.90). |
putbuy_share6: NOT PROMISING — IC sign flips (3/5), spreads 3/5, residual 3/5.
| putbuy_share6_z90: NOT PROMISING — best spread leg (4/5 -) but raw and
residual IC only 3/5. | cbprem_last: NOT PROMISING — 5/5 negative IC surviving
DVOL, yet LOYO spreads 3/5 and mostly oppose the IC (non-monotonic terciles).
| cbprem_mean24: NOT PROMISING — strongest IC (5/5 -, resid 5/5 -) but spreads
swing +149/-66 bps across years (3/5); direction unusable as a rule. |
cbprem_z90: NOT PROMISING — weak ICs (4/5), spreads 3/5, residual 3/5.
