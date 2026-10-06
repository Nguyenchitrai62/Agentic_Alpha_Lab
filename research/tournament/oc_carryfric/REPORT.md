# oc_carryfric REPORT — frozen cash-carry sleeve overlaid on friction scenarios

POST-HOC, REPORTING ONLY: every base row here was already scored on all five
years (oc_d13robust / v411+v421 audits); the carry rule was fixed before any
combination (oc_cashcarry PLAN pre-registered). Combination of already-scored
rows only — no selection claim, no new predictive features.

Question: for each friction scenario x {D13BF, R2B1D17BFG2} x carry f in
{0, 0.25, 0.5}, what are per anchor year %/month and DD, 5y mean, worst year,
max yearly DD, full-path DD, losing years? (a) Does D13BF + carry keep max
yearly DD < 15 AND 5y >= 5.0 under each friction? (b) Does G2 + carry keep
5y >= 5.0 under each friction (G2 alone: 4.57-5.21 over S1..S5)?

Method: equity-level combination reused UNCHANGED from
`oc_carryd13/combine_carryd13.py` (imported, not modified): per anchor year,
4-phase mix reset to 1.0 (`reset_metric.year_reset`) + carry sleeve at f of
year-start equity (yearly rebalance, labelled), carry marked HOURLY causal
(last closed hourly bar strictly before t; 0 before entry-bar close; locked to
the frozen ret_alloc from settlement-bar close); combined es/ms = base es/ms +
carry curve; 5y mean = geometric mean of yearly monthly factors (same as
v424); full-path DD = chained-reset path (labelled). Base runs are stored
per-phase equity (no engine reruns): D13BF from
`oc_d13robust/runs_D13BF_{base,S1..S5}.pkl`, G2 from
`v421_audit/runs_G2_{base,S1..S5}.pkl`. Frictions exactly as
oc_d13robust/ROBUST.md (S1 cost stress MAKER 0.0004/TAKER 0.0012, S2 latency
15/16, S3 latency 30/31, S4 stop slip 50%, S5 Bybit prices from 2021-11-15;
S5 year 2021 is a short window from 2021-11-15). Carry costs also stressed in
S1 (labelled): spot 0.15%/side + futures taker 0.12% entry, delivery 0.0002
unchanged (drag 0.0044 vs 0.00275); all 33 pairs stay net positive
(min stressed ret_alloc +0.00017). Repro:
`research/tournament/oc_carryfric/{combine_carryfric.py,results.json}`;
test `tests/test_oc_carryfric.py`. 4h+1h data only, one process, no 1m.

Cross-checks: f=0 reproduces `year_reset` exactly (max gap 0.0) and the
oc_d13robust reference aggregates exactly (R gap 0.0, DD gap 0.0); D13BF base
+ carry reproduces oc_carryd13 to the digit (f=0.25: 5.104/14.85; f=0.50:
5.234/14.71). Sizing convention note: carry is f of YEAR-START equity here
(same as oc_carryd13), NOT rebalanced-only-at-rolls as in oc_carrycombo — so
G2 base + carry here is 5.533/5.654 vs oc_carrycombo's 5.413/5.418; the lift
here (+0.12/+0.24pp) is the sleeve-alone accrual on a reset base, and DD is
the chained-reset convention (G2 base full 16.91 vs official continuous-mix
16.82 — convention gap, not a finding).

## D13BF (v424 R2B1D13BF) per friction x carry (per year R %/mo / DD %)

| scen/f | 2021 | 2022 | 2023 | 2024 | 2025 | 5y | worst | maxDD | fullDD | losing |
|---|---|---|---|---|---|---|---|---|---|---|
| base f=0 | 2.485 / 10.21 | 3.286 / 14.98 | 4.975 / 14.76 | 9.526 / 7.33 | 4.723 / 10.97 | 4.971 | 2.485 | 14.98 | 14.98 | 0 |
| base f=0.25 | 2.634 / 10.05 | 3.338 / 14.85 | 5.292 / 14.63 | 9.640 / 7.33 | 4.754 / 10.84 | 5.104 | 2.634 | 14.85 | 14.85 | 0 |
| base f=0.50 | 2.781 / 9.88 | 3.390 / 14.71 | 5.599 / 14.58 | 9.754 / 7.32 | 4.785 / 10.72 | 5.234 | 2.781 | 14.71 | 14.71 | 0 |
| S1 f=0 | 1.986 / 10.35 | 2.593 / 15.51 | 4.076 / 15.05 | 8.759 / 7.43 | 4.065 / 11.87 | 4.269 | 1.986 | 15.51 | 15.51 | 0 |
| S1 f=0.25 | 2.129 / 10.18 | 2.641 / 15.38 | 4.407 / 14.92 | 8.872 / 7.36 | 4.093 / 11.62 | 4.402 | 2.129 | 15.38 | 15.38 | 0 |
| S1 f=0.50 | 2.270 / 10.03 | 2.689 / 15.24 | 4.728 / 14.79 | 8.983 / 7.35 | 4.121 / 11.38 | 4.531 | 2.270 | 15.24 | 15.24 | 0 |
| S2 f=0 | 2.418 / 10.48 | 3.138 / 15.08 | 4.627 / 14.96 | 9.341 / 7.35 | 4.578 / 11.01 | 4.793 | 2.418 | 15.08 | 15.08 | 0 |
| S2 f=0.25 | 2.568 / 10.30 | 3.191 / 14.94 | 4.956 / 14.82 | 9.457 / 7.34 | 4.609 / 10.89 | 4.929 | 2.568 | 14.94 | 14.94 | 0 |
| S2 f=0.50 | 2.716 / 10.14 | 3.244 / 14.80 | 5.274 / 14.73 | 9.573 / 7.33 | 4.641 / 10.77 | 5.062 | 2.716 | 14.80 | 14.80 | 0 |
| S3 f=0 | 2.033 / 10.56 | 2.600 / 15.62 | 3.161 / 14.88 | 8.678 / 7.46 | 4.441 / 11.34 | 4.156 | 2.033 | 15.62 | 15.62 | 0 |
| S3 f=0.25 | 2.189 / 10.38 | 2.657 / 15.48 | 3.544 / 14.76 | 8.803 / 7.45 | 4.473 / 11.09 | 4.307 | 2.189 | 15.48 | 15.48 | 0 |
| S3 f=0.50 | 2.343 / 10.20 | 2.712 / 15.33 | 3.912 / 14.71 | 8.926 / 7.44 | 4.505 / 10.85 | 4.453 | 2.343 | 15.33 | 15.33 | 0 |
| S4 f=0 | 2.320 / 10.23 | 2.959 / 15.38 | 3.792 / 15.90 | 9.345 / 7.33 | 4.544 / 11.87 | 4.563 | 2.320 | 15.90 | 15.90 | 0 |
| S4 f=0.25 | 2.472 / 10.06 | 3.013 / 15.24 | 4.150 / 15.86 | 9.461 / 7.33 | 4.575 / 11.62 | 4.705 | 2.472 | 15.86 | 15.86 | 0 |
| S4 f=0.50 | 2.621 / 9.89 | 3.067 / 15.11 | 4.496 / 15.82 | 9.577 / 7.32 | 4.607 / 11.49 | 4.845 | 2.621 | 15.82 | 15.82 | 0 |
| S5 f=0 | 1.945 / 9.88 | 2.889 / 16.00 | 4.054 / 15.98 | 9.228 / 7.57 | 4.443 / 10.75 | 4.482 | 1.945 | 16.00 | 16.00 | 0 |
| S5 f=0.25 | 2.103 / 9.71 | 2.944 / 15.86 | 4.403 / 15.85 | 9.346 / 7.46 | 4.475 / 10.55 | 4.625 | 2.103 | 15.86 | 15.86 | 0 |
| S5 f=0.50 | 2.258 / 9.55 | 2.998 / 15.73 | 4.740 / 15.81 | 9.462 / 7.38 | 4.507 / 10.43 | 4.763 | 2.258 | 15.81 | 15.81 | 0 |

## G2 (R2B1D17BFG2) per friction x carry (per year R %/mo / DD %)

| scen/f | 2021 | 2022 | 2023 | 2024 | 2025 | 5y | worst | maxDD | fullDD | losing |
|---|---|---|---|---|---|---|---|---|---|---|
| base f=0 | 2.588 / 10.86 | 3.282 / 16.91 | 6.045 / 15.81 | 10.677 / 8.27 | 4.648 / 12.90 | 5.410 | 2.588 | 16.91 | 16.91 | 0 |
| base f=0.25 | 2.736 / 10.68 | 3.334 / 16.78 | 6.329 / 15.77 | 10.779 / 8.17 | 4.680 / 12.65 | 5.533 | 2.736 | 16.78 | 16.78 | 0 |
| base f=0.50 | 2.881 / 10.52 | 3.386 / 16.64 | 6.605 / 15.73 | 10.880 / 8.11 | 4.711 / 12.41 | 5.654 | 2.881 | 16.64 | 16.64 | 0 |
| S1 f=0 | 1.975 / 11.18 | 2.592 / 17.45 | 4.853 / 16.01 | 9.712 / 8.31 | 3.900 / 13.61 | 4.571 | 1.975 | 17.45 | 17.45 | 0 |
| S1 f=0.25 | 2.118 / 11.01 | 2.640 / 17.31 | 5.159 / 15.98 | 9.814 / 8.21 | 3.929 / 13.37 | 4.696 | 2.118 | 17.31 | 17.31 | 0 |
| S1 f=0.50 | 2.260 / 10.84 | 2.688 / 17.18 | 5.456 / 15.94 | 9.916 / 8.14 | 3.958 / 13.13 | 4.820 | 2.260 | 17.18 | 17.18 | 0 |
| S2 f=0 | 2.513 / 11.09 | 3.132 / 16.91 | 5.624 / 15.82 | 10.479 / 8.29 | 4.501 / 12.98 | 5.212 | 2.513 | 16.91 | 16.91 | 0 |
| S2 f=0.25 | 2.662 / 10.91 | 3.185 / 16.77 | 5.921 / 15.78 | 10.583 / 8.18 | 4.533 / 12.73 | 5.339 | 2.662 | 16.77 | 16.77 | 0 |
| S2 f=0.50 | 2.808 / 10.74 | 3.238 / 16.64 | 6.209 / 15.73 | 10.686 / 8.13 | 4.565 / 12.49 | 5.463 | 2.808 | 16.64 | 16.64 | 0 |
| S3 f=0 | 2.070 / 11.85 | 2.476 / 17.32 | 4.346 / 16.03 | 9.798 / 8.36 | 4.380 / 12.75 | 4.578 | 2.070 | 17.32 | 17.32 | 0 |
| S3 f=0.25 | 2.226 / 11.65 | 2.533 / 17.18 | 4.684 / 15.98 | 9.910 / 8.25 | 4.412 / 12.51 | 4.717 | 2.226 | 17.18 | 17.18 | 0 |
| S3 f=0.50 | 2.379 / 11.46 | 2.590 / 17.04 | 5.011 / 15.94 | 10.020 / 8.18 | 4.444 / 12.27 | 4.853 | 2.379 | 17.04 | 17.04 | 0 |
| S4 f=0 | 2.363 / 11.06 | 2.915 / 17.31 | 4.422 / 17.08 | 10.460 / 8.27 | 4.522 / 13.54 | 4.898 | 2.363 | 17.31 | 17.31 | 0 |
| S4 f=0.25 | 2.514 / 10.82 | 2.969 / 17.18 | 4.758 / 17.04 | 10.565 / 8.17 | 4.553 / 13.29 | 5.033 | 2.514 | 17.18 | 17.18 | 0 |
| S4 f=0.50 | 2.663 / 10.58 | 3.023 / 17.04 | 5.083 / 17.00 | 10.668 / 8.10 | 4.585 / 13.05 | 5.166 | 2.663 | 17.04 | 17.04 | 0 |
| S5 f=0 | 2.129 / 12.36 | 2.735 / 18.11 | 4.932 / 16.89 | 10.377 / 9.22 | 4.443 / 12.37 | 4.883 | 2.129 | 18.11 | 18.11 | 0 |
| S5 f=0.25 | 2.284 / 12.16 | 2.790 / 17.98 | 5.250 / 16.75 | 10.482 / 9.12 | 4.475 / 12.12 | 5.016 | 2.284 | 17.98 | 17.98 | 0 |
| S5 f=0.50 | 2.436 / 11.96 | 2.845 / 17.85 | 5.559 / 16.71 | 10.587 / 9.04 | 4.507 / 11.88 | 5.147 | 2.436 | 17.85 | 17.85 | 0 |

Win rate note (all 36 combos): BOT all-trade win rate UNCHANGED — the overlay
is equity-level and adds zero trades; carry pairs are 33/33 net positive on
allocated capital per oc_cashcarry (min +0.00017 even under S1 stress),
reported separately, not mixed into a trade win rate. No losing year appears
or disappears anywhere (losing years 0 in all 36 combos).

## Plain answers

(a) NO, with one narrow exception: D13BF + carry does NOT keep max yearly
DD < 15 AND 5y >= 5.0 under each friction. It keeps both bars only at base
(f=0.25: 5.104/14.85; f=0.50: 5.234/14.71) and at S2 f=0.50 (5.062/14.80).
S2 f=0.25 recovers DD < 15 (14.94) but not the return (4.929). Under S1, S3,
S4, S5 even f=0.50 fails both bars (best: S4 f=0.50 at 4.845/15.82; worst DD
S5 f=0.50 at 15.81; worst return S3 f=0.50 at 4.453). The sleeve helps on both
margins everywhere (+0.13-0.15pp 5y at f=0.25, +0.26-0.30pp at f=0.50;
DD -0.1-0.3pp) but cannot offset friction-level DD breaches that start at
15.08-16.00.

(b) MOSTLY, but not S1 or S3: G2 + carry keeps 5y >= 5.0 at base (5.533/5.654),
S2 (5.339/5.463), S4 f=0.25/0.50 (5.033/5.166), S5 f=0.25/0.50 (5.016/5.147).
It FAILS at S1 even at f=0.50 (4.820; carry-stress drag included) and at S3
even at f=0.50 (4.853). G2 alone over frictions is 4.571-5.212 as stated;
carry adds +0.12-0.15pp (f=0.25) / +0.25-0.28pp (f=0.50) and trims DD
0.1-0.3pp, with no losing year anywhere — a small, honest, nearly risk-free
lift, not a friction cure.
