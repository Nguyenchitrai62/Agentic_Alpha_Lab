# oc_jitter REPORT — joint +-10% jitter around R2B1D17BFG2

## Setup
Job jitter_g2_joint: BASE R2B1D17BFG2 (deployed v421 settings: rule inv, k 1.0, kd 1.7, bear true, G 2.0, book_hook bear) + 12 seeded joint uniform draws within +-10% of kd/G/k (numpy default_rng seed 20261006, draws consumed in kd,G,k order per row J01..J12, rounded to 4 decimals; see artifacts/kaggle_stage/engine_kernel/jobs/jitter_g2.json). Harness = artifacts/kaggle_stage/engine_kernel/engine_harness.py (4-phase reset-metric scoring, v388.mix full-path DD). One-at-a-time plateau: research/diagnostics/oc_plateau2/REPORT.md. Diagnostic only; deployment pick stays R2B1D17BFG2 regardless.

## Gate
BASE reproduces v421 (5y 5.41 / worst 2.588 / max yearly DD 16.91 / full-path DD 16.82 within rounding): PASS.

## Per-row summary (params kd/G/k | 5y %/mo | worst year | max yearly DD | full-path DD | losing years)
| row | kd | G | k | 5y %/mo | worst | maxDD | fullDD | losing |
|---|---|---|---|---|---|---|---|---|
| R2B1D17BFG2 | 1.7 | 2.0 | 1.0 | 5.41 | 2.588 | 16.91 | 16.82 | 0 |
| R2B1D17BFG2_J01 | 1.8058 | 1.929 | 1.0989 | 5.954 | 2.883 | 18.15 | 18.04 | 0 |
| R2B1D17BFG2_J02 | 1.6059 | 2.0194 | 0.9421 | 5.092 | 2.433 | 16.36 | 16.3 | 0 |
| R2B1D17BFG2_J03 | 1.7306 | 1.9083 | 1.0776 | 5.799 | 2.721 | 17.64 | 17.56 | 0 |
| R2B1D17BFG2_J04 | 1.8393 | 1.866 | 0.9611 | 5.579 | 2.692 | 17.13 | 17.06 | 0 |
| R2B1D17BFG2_J05 | 1.8347 | 2.1287 | 1.0131 | 5.573 | 2.752 | 17.43 | 17.34 | 0 |
| R2B1D17BFG2_J06 | 1.8685 | 1.8108 | 1.0793 | 5.93 | 2.776 | 18.18 | 18.07 | 0 |
| R2B1D17BFG2_J07 | 1.7328 | 1.93 | 1.0096 | 5.512 | 2.62 | 17.27 | 17.21 | 0 |
| R2B1D17BFG2_J08 | 1.6342 | 1.8926 | 1.0205 | 5.45 | 2.58 | 17.07 | 16.97 | 0 |
| R2B1D17BFG2_J09 | 1.7413 | 2.1144 | 1.0667 | 5.494 | 2.849 | 17.69 | 17.6 | 0 |
| R2B1D17BFG2_J10 | 1.823 | 2.1428 | 1.0714 | 5.639 | 2.889 | 17.83 | 17.75 | 0 |
| R2B1D17BFG2_J11 | 1.6254 | 1.9996 | 0.9807 | 5.204 | 2.572 | 16.69 | 16.61 | 0 |
| R2B1D17BFG2_J12 | 1.6651 | 1.8083 | 0.9061 | 5.138 | 2.44 | 16.33 | 16.28 | 0 |

## Distribution over the 12 jitter rows
5y %/mo: min 5.092, median 5.5425, max 5.954.
max yearly DD: min 16.33, median 17.35, max 18.18.
full-path DD: min 16.28, median 17.275, max 18.07.
share 5y >= 5.0: 1.000; share DD < 20 (both DDs): 1.000; share no losing year: 1.000; share all three: 1.000.

## Verdict
VERDICT: ROBUST — all 12 joint jitters keep 5y >= 5.0, DD < 20 and no losing year; the deployed point sits on a joint plateau.
