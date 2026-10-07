# oc_g2k20compound REPORT — G2K20 + carry f=0.25 with the COMPOUNDED (account-realistic) method

POST-HOC, REPORTING ONLY: every base row here was already scored on all five
years (v422 / oc_g2k20robust); the carry rule was fixed before any
combination (oc_cashcarry PLAN pre-registered). Combination of already-scored
rows only — no selection claim, no new predictive features.

Question: compute G2K20 + carry f = 0.25 with the COMPOUNDED method at base
and S1-S5 (per-year %/mo and DD, 5y mean, worst year, max yearly DD,
full-path DD, losing years); reproduce f = 0 G2K20 exactly; side by side
with G2 + carry (oc_carryfric2).

Method: ONE account A(t)=A(t-1)*(1+r_bot(t))+dU(t), reused UNCHANGED from
`oc_carrycompound/analyze_carrycompound.py` (= `oc_carryfric2/analyze_carryfric2.py`:
same grid 2021-09-24 04:00 .. 2026-09-23 12:00 hourly, same causal last-CLOSED-hourly
marks, same fees spot 0.001/side + fut 0.00055/0.0002, same per-year reset to 1.0 with
spanning carry rebased to 0 at each anchor, same continuous full-path DD with the
v421 formula). ASSUMPTION (as ordered): r_bot is the stored 4-phase mix hourly return
and applies to the WHOLE equity A(t-1) (UTA: the BOT sizes on total equity, carry
included); carry notional N=f x A at each entry, held to delivery; carry leg
close-marked so DD is a lower bound. S1 carry fees stressed exactly as in oc_carryfric
(labelled): spot 0.0015/side + futures taker 0.0012 entry, delivery 0.0002 unchanged
(drag 0.0044 vs 0.00275); all 33 pairs stay net positive (min stressed ret_alloc
+0.00017). f=0 short-circuits to base bit-exact. Base runs are stored per-phase equity
(no engine reruns): G2K20 base from `v422/v422_runs.pkl` strat G2K20, S1-S5 from
`oc_g2k20robust/runs_G2K20_{S1..S5}.pkl`. G2 + carry side values are read from
`oc_carryfric2/results.json` (same compounded method). Frictions exactly as
oc_g2k20robust/ROBUST.md (S1 cost stress MAKER 0.0004/TAKER 0.0012, S2 latency 15/16,
S3 latency 30/31, S4 stop slip 50%, S5 Bybit prices from 2021-11-15; S5 year 2021 is a
short window from 2021-11-15). Repro:
`research/tournament/oc_g2k20compound/{analyze_g2k20compound.py,results.json}`;
test `tests/test_oc_g2k20compound.py`. 4h+1h data only, one process, no 1m.

Cross-checks: f=0 reproduces ALL SIX stored G2K20 reference rows exactly (max gap 0.0):
base/S1..S5 vs oc_g2k20robust/results.json baseline/configs (base 5.874/2.832/17.79/full
17.69); base f=0 also matches v422_result.json G2K20 to the digit (asserted in-script).

## G2K20 compounding carry x friction (per year R %/mo / DD %)

| scen/f | 2021 | 2022 | 2023 | 2024 | 2025 | 5y | worst | maxDD | fullDD | losing |
|---|---|---|---|---|---|---|---|---|---|---|
| base f=0 (= G2K20) | 2.832 / 12.01 | 3.272 / 17.79 | 7.149 / 15.79 | 11.644 / 9.34 | 4.716 / 13.65 | 5.874 | 2.832 | 17.79 | 17.69 | 0 |
| base f=0.25 | 3.021 / 11.99 | 3.344 / 17.64 | 7.690 / 15.67 | 11.922 / 9.27 | 4.766 / 13.41 | 6.097 | 3.021 | 17.64 | 17.54 | 0 |
| S1 f=0 | 2.194 / 12.38 | 2.556 / 18.01 | 5.580 / 15.98 | 10.568 / 9.35 | 3.833 / 15.17 | 4.903 | 2.194 | 18.01 | 17.92 | 0 |
| S1 f=0.25 | 2.366 / 12.34 | 2.617 / 17.86 | 6.097 / 15.86 | 10.819 / 9.28 | 3.875 / 14.71 | 5.109 | 2.366 | 17.86 | 17.76 | 0 |
| S2 f=0 | 2.773 / 11.95 | 3.123 / 17.80 | 6.783 / 15.84 | 11.448 / 9.35 | 4.559 / 13.76 | 5.690 | 2.773 | 17.80 | 17.72 | 0 |
| S2 f=0.25 | 2.962 / 11.93 | 3.195 / 17.65 | 7.324 / 15.72 | 11.726 / 9.28 | 4.609 / 13.53 | 5.913 | 2.962 | 17.65 | 17.57 | 0 |
| S3 f=0 | 2.205 / 12.86 | 2.616 / 17.90 | 4.953 / 15.91 | 10.664 / 9.45 | 4.394 / 13.53 | 4.924 | 2.205 | 17.90 | 17.82 | 0 |
| S3 f=0.25 | 2.394 / 12.83 | 2.688 / 17.75 | 5.498 / 15.78 | 10.943 / 9.38 | 4.443 / 13.30 | 5.149 | 2.394 | 17.75 | 17.66 | 0 |
| S4 f=0 | 2.665 / 12.76 | 3.049 / 17.95 | 5.118 / 17.08 | 11.447 / 9.34 | 4.555 / 14.40 | 5.320 | 2.665 | 17.95 | 17.86 | 0 |
| S4 f=0.25 | 2.854 / 12.72 | 3.121 / 17.80 | 5.666 / 16.96 | 11.725 / 9.27 | 4.606 / 14.16 | 5.546 | 2.854 | 17.80 | 17.70 | 0 |
| S5 f=0 | 2.338 / 12.83 | 2.678 / 18.76 | 6.002 / 16.70 | 11.450 / 10.47 | 4.494 / 13.27 | 5.342 | 2.338 | 18.76 | 19.61 | 0 |
| S5 f=0.25 | 2.529 / 12.83 | 2.753 / 18.60 | 6.550 / 16.48 | 11.726 / 10.40 | 4.544 / 13.04 | 5.567 | 2.529 | 18.60 | 19.02 | 0 |

Carry lift (compounded, f=0.25 minus f=0): base +0.223, S1 +0.206, S2 +0.223,
S3 +0.225, S4 +0.226, S5 +0.225 pp/mo; maxDD trim 0.15-0.16pp, full-path trim
0.15-0.16pp except S5 full 19.61->19.02 (-0.59pp). No losing year appears or
disappears anywhere (0 in all 12 combos). Old book-keeping overlay (oc_g2k20robust
carry_f025, chained-reset) gave only +0.115-0.132pp (base 5.874->5.989, S1 4.903->5.022);
compounding adds ~+0.10pp more because notionals size on live A and carry profits earn
BOT return. Win rate note: the overlay is equity-level and adds zero BOT trades; carry
pairs are 33/33 net positive on allocated capital per oc_cashcarry (min +0.00017 even
under S1 stress), reported separately, not mixed into a trade win rate.

## Side by side with G2 + carry f=0.25 (oc_carryfric2, same compounded method)

| scen | G2+carry f=0.25 (5y / maxDD / fullDD) | G2K20+carry f=0.25 (5y / maxDD / fullDD) | gaps G2K20-G2 (R pp/mo / maxDD pp / fullDD pp) |
|---|---|---|---|
| base | 5.634 / 16.75 / 16.66 | 6.097 / 17.64 / 17.54 | +0.463 / +0.89 / +0.88 |
| S1 | 4.780 / 17.29 / 17.22 | 5.109 / 17.86 / 17.76 | +0.329 / +0.57 / +0.54 |
| S2 | 5.438 / 16.75 / 16.71 | 5.913 / 17.65 / 17.57 | +0.475 / +0.90 / +0.86 |
| S3 | 4.806 / 17.16 / 17.08 | 5.149 / 17.75 / 17.66 | +0.343 / +0.59 / +0.58 |
| S4 | 5.125 / 17.16 / 17.08 | 5.546 / 17.80 / 17.70 | +0.421 / +0.64 / +0.62 |
| S5 | 5.111 / 17.95 / 17.93 | 5.567 / 18.60 / 19.02 | +0.456 / +0.65 / +1.09 |

## Plain answer

YES — G2K20 + carry f=0.25 (compounded method) keeps 5y >= 5.0 %/mo AND DD < 20
under EVERY friction (base 6.097, S1 5.109, S2 5.913, S3 5.149, S4 5.546, S5 5.567;
worst S1 at 5.109; max yearly DD 18.60, max full-path DD 19.02 at S5; no losing year
anywhere). It costs more DD than G2 + carry everywhere: +0.57 to +0.90pp on max yearly
DD (base +0.89, S1 +0.57, S2 +0.90, S3 +0.59, S4 +0.64, S5 +0.65) and +0.54 to +1.09pp
on full-path DD (base +0.88, S1 +0.54, S2 +0.86, S3 +0.58, S4 +0.62, S5 +1.09), in
exchange for +0.33 to +0.48pp/mo more return. Honest context: still a carry overlay on
the same five research years (post-hoc combo, needs prospective paper); carry leg
close-marked so DD is a lower bound; G2K20 alone already passes everywhere except S1/S3
(4.903/4.924), the carry pushes those two over 5.0.
