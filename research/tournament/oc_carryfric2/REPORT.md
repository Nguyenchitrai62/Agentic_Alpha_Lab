# oc_carryfric2 REPORT — compounding carry overlay over friction scenarios

POST-HOC, REPORTING ONLY: every base row here was already scored on all five
years (oc_d13robust / v421_audit); the carry rule was fixed before any
combination (oc_cashcarry PLAN pre-registered). Combination of already-scored
rows only — no selection claim, no new predictive features.

Question: recompute the friction table for G2 (R2B1D17BFG2) and D13BF
(v424 R2B1D13BF) with the oc_carrycompound method at f in {0, 0.25}
(S1 carry fees stressed as in oc_carryfric): per scenario 5y mean, worst
year, max yearly DD, full-path DD; reproduce f = 0 exactly. Plain answers:
under which frictions does G2 + carry keep >= 5.0 %/mo, and does D13BF +
carry keep DD < 15 under any friction.

Method: ONE account A(t)=A(t-1)*(1+r_bot(t))+dU(t), reused UNCHANGED from
`oc_carrycompound/analyze_carrycompound.py` (same grid 2021-09-24 04:00 ..
2026-09-23 12:00 hourly, same causal last-CLOSED-hourly marks, same fees
spot 0.001/side + fut 0.00055/0.0002, same per-year reset to 1.0 with
spanning carry rebased to 0 at each anchor, same continuous full-path DD
with the v421 formula). ASSUMPTION (as ordered): r_bot is the stored
4-phase mix hourly return and applies to the WHOLE equity A(t-1) (UTA: the
BOT sizes on total equity, carry included); carry notional N=f x A at each
entry, held to delivery; carry leg close-marked so DD is a lower bound.
S1 carry fees stressed exactly as in oc_carryfric (labelled): spot
0.0015/side + futures taker 0.0012 entry, delivery 0.0002 unchanged (drag
0.0044 vs 0.00275); all 33 pairs stay net positive (min stressed
ret_alloc +0.00017). f=0 short-circuits to base bit-exact. Base runs are
stored per-phase equity (no engine reruns): D13BF from
`oc_d13robust/runs_D13BF_{base,S1..S5}.pkl`, G2 from
`v421_audit/runs_G2_{base,S1..S5}.pkl`. Frictions exactly as
oc_d13robust/ROBUST.md (S1 cost stress MAKER 0.0004/TAKER 0.0012, S2 latency
15/16, S3 latency 30/31, S4 stop slip 50%, S5 Bybit prices from 2021-11-15;
S5 year 2021 is a short window from 2021-11-15). Repro:
`research/tournament/oc_carryfric2/{analyze_carryfric2.py,results.json}`;
test `tests/test_oc_carryfric2.py`. 4h+1h data only, one process, no 1m.

Cross-checks: f=0 reproduces ALL TWELVE stored reference rows exactly
(max gap 0.0): G2 base/S1..S5 vs v421_audit/robust.json (base 5.410/2.588/
16.91/full 16.82), D13BF base/S1..S5 vs oc_d13robust/results.json (base
4.971/2.485/14.98/full 14.86); G2 base f=0 also matches v421_result.json
and D13BF base f=0 matches v424_result.json to the digit (asserted
in-script). G2 base f=0.25 reproduces oc_carrycompound to the digit
(5.634/2.778/16.75/full 16.66; carry add +0.224pp).
Convention note: full-path DD here is the CONTINUOUS account (v421
formula), NOT the chained-reset path of oc_carryfric — so G2 base full is
16.82 here vs 16.91 there, D13BF base full 14.86 here vs 14.98 there;
convention gaps, not findings.

## G2 (R2B1D17BFG2) compounding carry x friction (per year R %/mo / DD %)

| scen/f | 2021 | 2022 | 2023 | 2024 | 2025 | 5y | worst | maxDD | fullDD | losing |
|---|---|---|---|---|---|---|---|---|---|---|
| base f=0 | 2.588 / 10.86 | 3.282 / 16.91 | 6.045 / 15.81 | 10.677 / 8.27 | 4.648 / 12.90 | 5.410 | 2.588 | 16.91 | 16.82 | 0 |
| base f=0.25 | 2.778 / 10.86 | 3.353 / 16.75 | 6.590 / 15.69 | 10.956 / 8.20 | 4.698 / 12.66 | 5.634 | 2.778 | 16.75 | 16.66 | 0 |
| S1 f=0 | 1.975 / 11.18 | 2.592 / 17.45 | 4.853 / 16.01 | 9.712 / 8.31 | 3.900 / 13.61 | 4.571 | 1.975 | 17.45 | 17.37 | 0 |
| S1 f=0.25 | 2.147 / 11.18 | 2.653 / 17.29 | 5.375 / 15.89 | 9.965 / 8.23 | 3.943 / 13.38 | 4.780 | 2.147 | 17.29 | 17.22 | 0 |
| S2 f=0 | 2.513 / 11.09 | 3.132 / 16.91 | 5.624 / 15.82 | 10.479 / 8.29 | 4.501 / 12.98 | 5.212 | 2.513 | 16.91 | 16.86 | 0 |
| S2 f=0.25 | 2.702 / 11.09 | 3.203 / 16.75 | 6.170 / 15.70 | 10.759 / 8.21 | 4.551 / 12.74 | 5.438 | 2.702 | 16.75 | 16.71 | 0 |
| S3 f=0 | 2.070 / 11.85 | 2.476 / 17.32 | 4.346 / 16.03 | 9.798 / 8.36 | 4.380 / 12.75 | 4.578 | 2.070 | 17.32 | 17.24 | 0 |
| S3 f=0.25 | 2.260 / 11.85 | 2.549 / 17.16 | 4.896 / 15.91 | 10.079 / 8.28 | 4.430 / 12.52 | 4.806 | 2.260 | 17.16 | 17.08 | 0 |
| S4 f=0 | 2.363 / 11.06 | 2.915 / 17.31 | 4.422 / 17.08 | 10.460 / 8.27 | 4.522 / 13.54 | 4.898 | 2.363 | 17.31 | 17.24 | 0 |
| S4 f=0.25 | 2.553 / 11.02 | 2.987 / 17.16 | 4.974 / 16.96 | 10.740 / 8.20 | 4.572 / 13.30 | 5.125 | 2.553 | 17.16 | 17.08 | 0 |
| S5 f=0 | 2.129 / 12.36 | 2.735 / 18.11 | 4.932 / 16.89 | 10.377 / 9.22 | 4.443 / 12.37 | 4.883 | 2.129 | 18.11 | 18.09 | 0 |
| S5 f=0.25 | 2.321 / 12.36 | 2.808 / 17.95 | 5.484 / 16.67 | 10.656 / 9.15 | 4.493 / 12.13 | 5.111 | 2.321 | 17.95 | 17.93 | 0 |

## D13BF (v424 R2B1D13BF) compounding carry x friction (per year R %/mo / DD %)

| scen/f | 2021 | 2022 | 2023 | 2024 | 2025 | 5y | worst | maxDD | fullDD | losing |
|---|---|---|---|---|---|---|---|---|---|---|
| base f=0 | 2.485 / 10.21 | 3.286 / 14.98 | 4.975 / 14.76 | 9.526 / 7.33 | 4.723 / 10.97 | 4.971 | 2.485 | 14.98 | 14.86 | 0 |
| base f=0.25 | 2.677 / 10.21 | 3.357 / 14.82 | 5.521 / 14.72 | 9.808 / 7.32 | 4.772 / 10.84 | 5.198 | 2.677 | 14.82 | 14.71 | 0 |
| S1 f=0 | 1.986 / 10.35 | 2.593 / 15.51 | 4.076 / 15.05 | 8.759 / 7.43 | 4.065 / 11.87 | 4.269 | 1.986 | 15.51 | 15.39 | 0 |
| S1 f=0.25 | 2.160 / 10.35 | 2.654 / 15.36 | 4.598 / 15.01 | 9.014 / 7.35 | 4.107 / 11.63 | 4.479 | 2.160 | 15.36 | 15.23 | 0 |
| S2 f=0 | 2.418 / 10.48 | 3.138 / 15.08 | 4.627 / 14.96 | 9.341 / 7.35 | 4.578 / 11.01 | 4.793 | 2.418 | 15.08 | 14.97 | 0 |
| S2 f=0.25 | 2.610 / 10.48 | 3.210 / 14.92 | 5.174 / 14.92 | 9.623 / 7.33 | 4.627 / 10.89 | 5.020 | 2.610 | 14.92 | 14.81 | 0 |
| S3 f=0 | 2.033 / 10.56 | 2.600 / 15.62 | 3.161 / 14.88 | 8.678 / 7.46 | 4.441 / 11.34 | 4.156 | 2.033 | 15.62 | 15.53 | 0 |
| S3 f=0.25 | 2.225 / 10.56 | 2.672 / 15.46 | 3.713 / 14.84 | 8.962 / 7.44 | 4.490 / 11.10 | 4.385 | 2.225 | 15.46 | 15.37 | 0 |
| S4 f=0 | 2.320 / 10.23 | 2.959 / 15.38 | 3.792 / 15.90 | 9.345 / 7.33 | 4.544 / 11.87 | 4.563 | 2.320 | 15.90 | 15.25 | 0 |
| S4 f=0.25 | 2.511 / 10.23 | 3.030 / 15.22 | 4.343 / 15.78 | 9.627 / 7.32 | 4.594 / 11.63 | 4.791 | 2.511 | 15.78 | 15.09 | 0 |
| S5 f=0 | 1.945 / 9.88 | 2.889 / 16.00 | 4.054 / 15.98 | 9.228 / 7.57 | 4.443 / 10.75 | 4.482 | 1.945 | 16.00 | 15.95 | 0 |
| S5 f=0.25 | 2.139 / 9.88 | 2.962 / 15.84 | 4.606 / 15.77 | 9.510 / 7.49 | 4.492 / 10.55 | 4.711 | 2.139 | 15.84 | 15.79 | 0 |

Win rate note (all 24 combos): BOT all-trade win rate UNCHANGED — the overlay
is equity-level and adds zero trades; carry pairs are 33/33 net positive on
allocated capital per oc_cashcarry (min +0.00017 even under S1 stress),
reported separately, not mixed into a trade win rate. No losing year appears
or disappears anywhere (losing years 0 in all 24 combos).

## Plain answers

G2 + carry (f=0.25, compounding) keeps >= 5.0 %/mo at base (5.634), S2
(5.438), S4 (5.125) and S5 (5.111). It FAILS at S1 (4.780, carry-stress
drag included) and at S3 (4.806) — same two failures as the year-start
(book-keeping) overlay in oc_carryfric, with ~+0.09pp more lift from
compounding everywhere (base +0.224pp over G2 alone; frictions +0.21-0.23pp).
G2 alone over frictions is 4.571-5.212; carry adds +0.21-0.23pp and trims
max DD 0.15-0.16pp and full-path DD 0.15-0.16pp, with no losing year
anywhere — a small, honest, nearly risk-free lift, not a friction cure.

D13BF + carry (f=0.25, compounding) keeps BOTH 5y >= 5.0 AND max yearly DD <
15 at base (5.198/14.82) and at S2 (5.020/14.92) — and nowhere else. So YES,
it keeps DD < 15 under one friction (S2, 14.92; base 14.82 is the
no-friction reference), but NO under S1 (15.36), S3 (15.46), S4 (15.78) or
S5 (15.84) even at f=0.25. The sleeve helps on both margins everywhere
(+0.21-0.23pp 5y, DD -0.12-0.16pp) but cannot offset friction-level DD
breaches that start at 15.08-16.00.
