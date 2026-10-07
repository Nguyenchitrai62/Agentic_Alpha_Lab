# oc_qbasis REPORT

Feature: F(T) = BTC quarterly-basis (annualised front-delivery basis) z-score
vs trailing 90d, from 4h closes strictly before T (min 300/540 bars).
Terciles use strictly previous-data cut-offs. Expected sign: NEGATIVE
(Hi-Lo < 0) for book longs and dip y1.0.

## Book long leg: next-bar gross P&L per (bar, coin) row, bps

| year | Lo mean (n) | Mid mean (n) | Hi mean (n) | Hi-Lo |
|---|---|---|---|---|
| 2021-09-24 | NO CUTOFFS (grid starts at anchor; 0 training times -> FAIL per PLAN) | | | NaN |
| 2022-09-24 | 0.15 (589) | 0.42 (1373) | 0.67 (3357) | +0.52 |
| 2023-09-24 | 0.51 (718) | 0.80 (2234) | 1.12 (3559) | +0.61 |
| 2024-09-24 | 0.60 (1534) | 0.41 (1925) | 1.13 (3090) | +0.54 |
| 2025-09-24 | 0.13 (1398) | 0.84 (1238) | 1.20 (1534) | +1.07 |
| LOYO heldout 21/22/23/24/25 | | | | +1.71/+0.26/+0.63/+0.66/+1.07 |

Book decision: year_neg 0/5, loyo_neg 0/5 -> FAIL (sign is consistently
POSITIVE, opposite of the pre-registered hypothesis).

## Dip rungs: mean y1.0 net, bps (majors-R2, 6876 rows)

| year | Lo mean (n) | Mid mean (n) | Hi mean (n) | Hi-Lo |
|---|---|---|---|---|
| 2021-09-24 | 38.24 (715) | 20.76 (229) | 123.24 (46) | +85.00 |
| 2022-09-24 | 21.96 (138) | 35.50 (319) | -17.73 (588) | -39.69 |
| 2023-09-24 | 7.18 (293) | 43.02 (453) | 53.37 (584) | +46.19 |
| 2024-09-24 | 23.36 (331) | 35.79 (206) | 56.53 (452) | +33.17 |
| 2025-09-24 | 26.73 (384) | 3.12 (629) | 24.07 (131) | -2.65 |
| LOYO heldout 21/22/23/24/25 | | | | +83.95/-55.66/+47.96/+30.81/+5.65 |

Dip decision: year_neg 2/5, loyo_neg 1/5 -> FAIL (sign flips year to year).

## Secondary (descriptive, not gating)

ETH z90 book long-leg Hi-Lo: 22:+0.21, 23:+0.55, 24:+1.14, 25:+0.25 (same
positive direction as BTC). ETH z90 dip Hi-Lo: +70.02/-10.89/+37.67/+14.64/
+34.69. Raw BTC level medians rise monotonically Lo->Hi every year
(e.g. 2024 dips 6.2/7.2/14.7%), so the z-terciles also sort the level.

## Caveats

- Book year-1 has no cut-offs by construction (grid starts 2021-09-24; PLAN
  fixed training on grid times < A_k, no clock backfill) -> FAIL; it could not
  have passed even with a good sign, but years 2-5 and all LOYO folds are
  valid and uniformly positive, so the verdict does not hinge on it.
- No post-hoc changes: definitions frozen in PLAN.md before results were run.
- v351 context: QB1 member fit dev4 (+0.32 R) but failed transfer with higher
  DD; this regime study is consistent — raw basis sorts returns the wrong way
  for a short-euphoria rule.

## Verdict

NOT PROMISING — high quarterly basis predicts better (not worse) book-long
returns and has no sign-stable dip effect; close this direction.
