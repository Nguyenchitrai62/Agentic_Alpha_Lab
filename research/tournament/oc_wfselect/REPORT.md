# oc_wfselect REPORT — does variant SELECTION generalise? (2026-10-06)

## Setup
31 unique rows with cached 4-phase runs (v406/v411/v415/v417/v418/v419/v420/
v421/v422/v423 + oc_plateau; duplicates R2B1D17BF/R2B1D16/G2 verified
identical, kept once; R2B1D17BF_F20 == R2B1F20K17 numerically, kept as two
names). Per-year stats = reset_metric.year_reset y=0..4
(anchors 2021-09-24..2025-09-24 +365 d, reset 1/4 capital; R %/mo, DD %).
Rule A = AGENTS robust (DD<=20 every sel year, no losing year; prefer mean>=5;
then highest worst year; ties higher mean, then name). Rule B = highest mean
among DD<=18 rows. Pick for k uses ONLY years<k; scored on k. No fallback
triggered (eligible set never empty). Repro:
research/tournament/oc_wfselect/{PLAN.md,run_wfselect.py,results.json}.

## Walk-forward picks (Rule A, AGENTS robust)
| test year k | sel years | pick | R %/mo | DD % | base R2B1D17BF | excess |
|---|---|---|---|---|---|---|
| 2022 (k=1) | 2021 | R2B1D17BFCX | 3.665 | 16.56 | 3.505 | +0.160 |
| 2023 (k=2) | 2021-22 | R2B1D17BFCX | 4.654 | 18.55 | 4.669 | -0.015 |
| 2024 (k=3) | 2021-23 | R2B1D17BFCX | 11.139 | 8.25 | 11.270 | -0.131 |
| 2025 (k=4) | 2021-24 | R2B1D17BFCX | 4.811 | 13.83 | 5.060 | -0.249 |
Same-sign (positive excess): 1/4 (need >=3/4).

## Chains over test years 1..4 (geo mean R | max yearly DD | losing)
| chain | R_geo %/mo | maxDD | losing | years [R,DD] 2022..2025 |
|---|---|---|---|---|
| WF Rule A | 6.027 | 18.55 | 0 | [3.665,16.56] [4.654,18.55] [11.139,8.25] [4.811,13.83] |
| WF Rule B (DD18) | 6.000 | 18.55 | 0 | [3.665,16.56] [4.654,18.55] [11.129,9.02] [4.716,13.65] |
| always-R2B1D17BF | 6.084 | 18.33 | 0 | [3.505,16.23] [4.669,18.33] [11.270,8.26] [5.060,12.81] |
| best-in-hindsight G2K20 | 6.649 | 17.79 | 0 | [3.272,17.79] [7.149,15.79] [11.644,9.34] [4.716,13.65] |
Rule B picks: k=1 R2B1D17BFCX, k=2 R2B1D17BFCX, k=3 G15K20, k=4 G2K20.
WF-A trails base by 0.057 pts; oracle beats base by 0.565 pts.

## LOO stability (Rule A; k=1 N/A)
| k | main | LOO picks | stable |
|---|---|---|---|
| k=2 | R2B1D17BFCX | drop2021->R2B1_130, drop2022->R2B1D17BFCX | NO |
| k=3 | R2B1D17BFCX | drop2021->R2B1F15K23, drop2022->G15K20, drop2023->CX | NO |
| k=4 | R2B1D17BFCX | drop2021->R2B1_130, others->CX | NO |
Stable: 0/3 (need 3/3).

## Verdict
VERDICT: NOT PROMISING — walk-forward robust selection sticks to R2B1D17BFCX
but beats always-R2B1D17BF in only 1/4 test years, trails it by 0.06 pts geo,
and is LOO-unstable (0/3); the DD18 rule also trails the base.
NOTE: these candidates were all designed after seeing the five years, so even
this walk-forward chain is optimistic. Reset-metric DD shown (max yearly);
full-path DD not recomputed for the chain.
