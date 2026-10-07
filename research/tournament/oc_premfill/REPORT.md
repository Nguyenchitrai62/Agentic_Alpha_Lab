# oc_premfill REPORT: perp-vs-spot dislocation at the fill as dip-rung context

Universe: majors (BTC/ETH/SOL/BNB/XRP) x R2 depths (2.5/3/3.5/4/5), 6876 fills,
outcome y1.0 primary, margin m = y1.5 - y1.0 secondary (descriptive). Anchor
years start each 2021-09-24 .. 2025-09-24 (n = 990/1045/1330/989/1144).
Premium: Binance 1m premium-index klines per major, own-symbol only, f-1 bar
(open_time == t_fill - 1m, exact match) plus 30m change and 7d z-score; all
bars used end <= t_fill; bars starting at/after 2026-09-24 00:00 UTC dropped.
Fill-time features -> bot_only label. Coverage ~100% (prem NaN: 4 BTC + 1 ETH
+ 1 XRP isolated minute gaps; z7d 95.3% in 23-24 from scattered minute gaps
breaking the 7200-contiguous-minute rule). y1.0 is heavily left-skewed
(skew -2.5..-3.7/yr; mean 37 bps << median 94 bps overall). Cross-feature
Spearman: prem-chg30 0.57, prem-z7d 0.73, chg30-z7d 0.73 (one idea, not three
independent bets).

## Verdict

NOT PROMISING as a directional signal. `prem` meets each leg's mechanical
count (IC 4/5, LOYO spread 4/5) but the two legs disagree on the DIRECTION of
the effect: within-year rank IC is 4/5 NEGATIVE (higher premium -> worse rank
outcome, |rho| <= 0.10) while LOYO Hi-Lo mean spreads are 4/5 POSITIVE. The
assignment rule asks for "the effect" with "the same sign" — there is no
single stable sign here. Median Hi-Lo spreads (+30/+16/-7/-28/-5 bps) are
mixed and coin-split ICs are mixed everywhere, so the positive mean spreads
reflect left-tail composition (fewer disaster stop-outs in Hi fills some
years), not a usable level effect. `prem_chg30` (IC 4/5, spread 3/5) and
`prem_z7d` (3/5, 3/5) fail outright.

## Tables

Spearman IC(feature, y1.0) per anchor year (p in brackets):
feature    21-22          22-23          23-24          24-25          25-26          | sign
prem       -0.030 (0.34)  -0.004 (0.89)  +0.021 (0.45)  -0.084 (0.009) -0.103 (0.000) | 4/5 (-)
prem_chg30 -0.029 (0.37)  +0.037 (0.24)  -0.023 (0.40)  -0.072 (0.023) -0.068 (0.022) | 4/5 (-)
prem_z7d   -0.059 (0.06)  +0.054 (0.08)  +0.009 (0.74)  -0.087 (0.006) -0.058 (0.05)  | 3/5 (-)

Spearman IC(feature, margin y1.5-y1.0), descriptive (NOT part of the rule):
feature    21-22   22-23   23-24   24-25   25-26   | sign
prem       -0.028  -0.076  -0.008  -0.055  -0.059  | 5/5 (-) tiny
prem_chg30 -0.039  -0.056  -0.014  -0.101  +0.010  | 4/5 (-) tiny
prem_z7d   -0.062  -0.027  +0.008  -0.126  -0.018  | 4/5 (-) tiny

Mean y1.0 by tercile, bps [lo n / mid n / hi n], cut-offs from PREVIOUS data only:
prem 21-22: +35 (696) / +41 (159) / +52 (135)
prem 22-23: -15 (505) / +16 (262) / +26 (277)
prem 23-24: +32 (290) / +39 (559) / +45 (481)
prem 24-25: +55 (321) / +24 (373) / +49 (295)
prem 25-26: +11 (474) / +6 (466) / +37 (204)
Median Hi-Lo spreads, bps (post-hoc descriptive): +30 / +16 / -7 / -28 / -5 (mixed).

LOYO tercile spread = mean(y1.0|Hi) - mean(y1.0|Lo), bps (training = other 4 years):
held-out  prem        prem_chg30  prem_z7d
21-22     +1.6        -14.7       -8.6
22-23     +38.2       +52.9       +82.1
23-24     +13.6       +10.3       +27.2
24-25     -20.1       -21.3       -13.4
25-26     +25.2       +19.6       +16.3
sign      4/5 (+)     3/5 (+)     3/5 (+) -> chg30/z7d FAIL

Descriptive coin-split ICs with y1.0 (NOT part of the rule), order 21-22..25-26:
prem BTC: -0.01/-0.24/+0.08/-0.04/-0.18; ETH: -0.10/-0.03/+0.02/-0.28/-0.27;
  SOL: -0.03/-0.13/+0.23/-0.06/-0.06; BNB: +0.04/+0.04/-0.10/-0.06/-0.09;
  XRP: -0.13/+0.12/-0.01/-0.03/+0.13. No coin consistent; chg30/z7d similar.

## Caveats / post-hoc log

1. No change to definitions, universe, or the decision rule. Post-hoc
   additions only: median spreads, margin ICs (pre-registered as descriptive),
   skew/coin-split descriptives (rule untouched).
2. First-four-year sensitivity (repo selection uses 2021-2024): prem IC 3/4
   negative, LOYO 3/4 positive — fails the >= 4 bar on the first four alone,
   independent of the sign-incoherence argument.
3. The IC-vs-spread sign flip is arithmetically consistent with skew: rank
   statistics follow the bulk (flat-to-negative), means follow the disaster
   tail (thinner in Hi fills in 3 of 5 years). Neither leg is "wrong"; jointly
   they describe tail composition, not a tradeable level effect (spreads
   +2..+38 bps vs ~4-8 bps costs, with a -20 bps year).
4. Causality: exact f-1 match required (no fill-forward); windows use only
   bars with END <= t_fill with contiguity verified; training/LOYO cut-offs
   never see the test year; no bar starting at/after 2026-09-24 00:00 UTC used
   (verified by test). Findings are in-sample walk-forward style, fill-time
   (bot_only), and need prospective validation.

## One-line verdict

NOT PROMISING: the two pre-registered legs disagree on direction (IC 4/5 negative vs LOYO mean spreads 4/5 positive, medians mixed, coins mixed), so perp-vs-spot dislocation at the fill carries no stable-sign directional information for dip-fill y1.0 — at most a tail-composition footnote, bot_only, needs no engine test.
