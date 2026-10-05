# oc_dvol REPORT: Deribit implied vol (DVOL) as dip-rung context

Universe: majors (BTC/ETH/SOL/BNB/XRP) x R2 depths (2.5/3/3.5/4/5), 6876 fills,
outcome y1.0 (fill mean, bps). Anchor years start each 2021-09-24 .. 2025-09-24
(n = 990/1045/1330/989/1144). DVOL 1h (resolution 3600) for BTC+ETH fetched
from Deribit public API, 2021-04-01 .. 2026-09-23 23:00 bar (48048 bars/coin,
gap-free, max step 1h); raw JSON in `data/raw/deribit_dvol_20261005/` +
`manifest.json` (URL + sha256 per file). BTC rungs use BTC DVOL/BTC realized,
ETH rungs ETH/ETH, SOL/BNB/XRP use BTC as market proxy. All features use bars
with END strictly before T (1h staleness by construction). Coverage 100% in
all 5 years (DVOL warm-up ends ~2021-06-30, before year 1). Cross-feature
Spearman: z90-chg24 0.30, chg24-vrp 0.35, z90-vrp 0.15 (not redundant).

## Verdict

PROMISING per the pre-registered rule: `dvol_z90` (IC + in 5/5, LOYO spread +
in 4/5) and `vrp` (IC + in 5/5, LOYO spread + in 4/5); NOT promising:
`dvol_chg24` (IC 4/5, spread 3/5). Direction: higher / more elevated implied
vol at the bar open goes with BETTER dip-fill y1.0 (contrarian dip edge is
paid when fear is high). Effect sizes are modest (IC ~0.08-0.23, LOYO spreads
mostly +10..+44 bps vs ~4-8 bps round-trip cost) and tercile profiles are
often non-monotonic — context, not a standalone rule.

## Tables

Spearman IC(feature, y1.0) per anchor year (p in brackets):
feature    21-22          22-23          23-24          24-25          25-26          | IC sign
dvol_z90   +0.089 (0.005) +0.181 (~0)   +0.120 (~0)   +0.109 (0.001) +0.107 (0.000) | 5/5
dvol_chg24 +0.199 (~0)    +0.041 (0.18) -0.057 (0.04) +0.089 (0.005) +0.193 (~0)   | 4/5
vrp        +0.234 (~0)    +0.100 (0.001) +0.112 (~0)   +0.077 (0.015) +0.099 (0.001) | 5/5

Mean y1.0 by tercile, bps [lo n / mid n / hi n], cut-offs from PREVIOUS data only:
dvol_z90 21-22: +31 (459) / -63 (30!) / +51 (501); cut from n=113, q=(-0.46,-0.34)
dvol_z90 22-23: -1 (418) / -3 (385) / +24 (242)
dvol_z90 23-24: +14 (221) / +29 (136) / +47 (973)
dvol_z90 24-25: +37 (368) / +48 (355) / +38 (266)
dvol_z90 25-26: +23 (202) / +16 (420) / +8 (522)
vrp      21-22: +19 (693) / +71 (160) / +96 (137)
vrp      22-23: +18 (603) / -59 (180) / +15 (262)
vrp      23-24: +26 (506) / +51 (648) / +39 (176)
vrp      24-25: +33 (460) / +42 (465) / +97 (64)
vrp      25-26: +17 (629) / +6 (418) / +22 (97)
dvol_chg24 21-22: +4 (348) / +44 (161) / +61 (481)
dvol_chg24 22-23: +23 (386) / -11 (376) / -4 (283)
dvol_chg24 23-24: +42 (467) / +56 (526) / +10 (337)
dvol_chg24 24-25: +48 (195) / +36 (546) / +48 (248)
dvol_chg24 25-26: +19 (216) / +7 (534) / +20 (394)

LOYO tercile spread = mean(y1.0|Hi) - mean(y1.0|Lo), bps (training = other 4 years):
held-out  dvol_z90      vrp         dvol_chg24
21-22     +21.2         +11.0       +55.2
22-23     +43.7         -31.8       -18.6
23-24     +42.0         +23.4       -22.2
24-25     +2.5          +39.6       +5.8
25-26     -15.6         +7.0        +1.3
sign      4/5 (+)       4/5 (+)     3/5 (+) -> FAIL

Descriptive coin-split ICs (NOT part of the rule):
dvol_z90 BTC-only: +0.17/+0.19/+0.26/+0.26/+0.15 (5/5 +); ETH-only: +0.26/+0.25/+0.17/-0.08/+0.18;
  proxy (SOL+BNB+XRP on BTC DVOL): +0.04/+0.19/+0.07/+0.16/+0.13 (5/5 +).
vrp BTC-only: +0.37/+0.13/+0.21/-0.02/+0.25; ETH-only: +0.32/+0.16/+0.14/+0.11/+0.08 (5/5 +);
  proxy: +0.19/+0.08/+0.04/+0.09/+0.07 (5/5 +).
dvol_chg24 weaker and mixed everywhere (see results.json).

## Caveats / post-hoc log

1. No post-hoc change to definitions, universe, or the decision rule. Only
   addition after first run: p-values, cross-correlations, coin splits and
   saving `features_dvol.parquet` (descriptive, rule untouched).
2. First-four-year sensitivity (repo selection rule uses 2021-2024 for choice):
   dvol_z90 passes 4/4 on IC and 4/4 on spread; vrp passes IC 4/4 but spread
   only 3/4 (2022 held-out -31.8 bps) — vrp's PROMISING flag relies on the
   5-year rule as assigned. The 2025 flip (z90 spread -15.6) likewise warns
   against over-reading.
3. Year-1 tercile cut-offs train on only 113 rows (2021-06-30..2021-09-24);
   q33/q67 nearly coincide for z90, leaving a 30-row mid bucket (mean -63 bps,
   noise). Spreads are top-minus-bottom only and robust to this, but the 21-22
   tercile row should not be over-interpreted.
4. Tercile profiles are rarely monotonic (e.g. z90 24-25 flat, 25-26
   decreasing; vrp mid-bucket collapses in 22-23) — the signal is a weak
   level effect, suitable at most as a sizing/context input, not a gate.
5. Multiple comparisons: 3 features x 5 years = 15 ICs; single-year p-values
   are nominal. The pre-registered sign-consistency bar (5/5 IC for two
   near-independent features, p ~ 1/16 each under null) is the actual test.
6. Causality: strict end<T as-of verified by test (truncate shift + cutoff
   audit); training/LOYO cut-offs never see the test year; no bar starting
   at/after 2026-09-24 00:00 UTC is used. Findings are in-sample walk-forward
   style and need prospective validation.

## One-line verdict

PROMISING (as assigned): high DVOL level vs 90d history and a wide DVOL-minus-realized premium predict modestly better dip-fill y1.0 with 5/5-year IC sign consistency and 4/5-year LOYO spread consistency; 24h DVOL change fails (3/5 spreads) — weak, non-monotonic effects, context-only, needs prospective validation.
