# oc_deeptp REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
B1 fills (static bid at lv, size x 1/(1+n), v399-exact n) x R2 depths
(2.5/3/3.5/4/5) on majors, bars with open in [2021-09-24, 2026-09-24)
(5 anchor years); exits = D0 replica from the fill px (sl 4sg, bl 8sg,
timeout next open; maker 0.0002 / taker 0.00055; longs pay 0.0001 on
settling timeouts). BASE: TP 1.0 sigma on all rungs (agent-TP-proxy).
QUICK: TP 0.5 sigma on deep rungs (k >= 4.0), TP 1.0 on shallow.
NODEEP: shallow rungs only (deep removed), TP 1.0. BASE and QUICK share
identical fills/sizes (only deep-rung exit nets differ); NODEEP is the
shallow subset. Weights w = 1/(1+n_fill), renormalised per year-variant
to mean 1 (primary); daily sums by exit date UTC; maxDD of cumulative
daily-sum path from 0. BASE replica validated tick-for-tick vs
oc_b1deeper B1: 5498 fills (1067/1126/952/1179/1174 per coin). Ledger
checksum 143b11a3976dc0ff. All 5 years are research data: any PROMISING
result would still need prospective validation (disclosed vs RULES.md
hidden-year rule).

## Per-year whole ladder (renormalised w; mean in bps, win = net>0 share)
| year | BASE n/mean/win/sum/worst/DD | QUICK n/mean/win/sum/worst/DD | NODEEP n/mean/win/sum/worst/DD |
|---|---|---|---|
| 2021 | 990/38.1/.688/3.887/-0.720/0.720 | 990/33.1/.706/3.532/-0.624/0.624 | 813/29.6/.662/2.672/-0.630/0.630 |
| 2022 | 1045/3.8/.695/0.272/-1.082/1.699 | 1045/2.9/.720/0.466/-1.087/1.603 | 855/1.4/.689/0.030/-0.823/1.444 |
| 2023 | 1330/39.7/.773/5.725/-0.400/0.409 | 1330/35.6/.787/5.261/-0.423/0.441 | 1103/42.4/.769/4.922/-0.313/0.339 |
| 2024 | 989/41.1/.699/3.959/-0.332/0.332 | 989/34.1/.707/3.400/-0.372/0.372 | 835/33.4/.675/2.692/-0.389/0.389 |
| 2025 | 1144/13.4/.656/1.210/-0.903/1.130 | 1144/10.4/.671/0.912/-0.916/1.143 | 965/9.7/.630/0.557/-0.782/1.077 |
| FULL | 5498/27.4/.705/15.138/-1.138/1.787 | 5498/23.4/.721/13.674/-1.144/1.687 | 4571/23.9/.688/11.005/-0.857/1.503 |

## Deep-subset descriptive (same k>=4.0 fills, raw w*y; BASE TP1.0 vs QUICK TP0.5)
| year | n | base mean/win/raw | quick mean/win/raw |
|---|---|---|---|
| 2021 | 177 | 77.5bps/.808/0.619 | 49.1bps/.910/0.401 |
| 2022 | 190 | 14.6bps/.721/0.161 | 10.0bps/.858/0.292 |
| 2023 | 227 | 26.5bps/.793/0.350 | 2.7bps/.877/0.041 |
| 2024 | 154 | 83.1bps/.825/0.733 | 38.3bps/.877/0.369 |
| 2025 | 179 | 33.9bps/.793/0.363 | 14.2bps/.894/0.188 |

## Decision (PROMISING = QUICK sum >= BASE AND >= NODEEP in >=4/5 yrs AND QUICK maxDD <= both in >=4/5)
| check | score | pass? |
|---|---|---|
| S_QUICK >= S_BASE AND S_QUICK >= S_NODEEP | 1/5 (only 2022, +0.19/+0.44) | NO |
| DD_QUICK <= DD_BASE AND DD_QUICK <= DD_NODEEP | 1/5 (only 2021) | NO |
| PROMISING | | NO |

## Notes
- The quick exit works as designed on hit rate (deep win rate rises every
  year, 0.72-0.82 -> 0.86-0.91) but banks a smaller gain every year
  (deep mean falls in 5/5; raw deep sum beats TP1.0 only in 2022), so the
  whole-ladder sum loses to BASE in 4/5 years (-0.36/-0.46/-0.56/-0.30 in
  2021/2023/2024/2025). Faster exits win more rungs yet give up more upside
  than they save — the same trade seen in oc_beartp.
- Deep rungs here still earn their keep: QUICK beats NODEEP on the sum in
  5/5 years, and BASE beats NODEEP in 5/5, so removing deep rungs is worse
  than either exit. (This B1+D0 replica's deep fills are positive every
  year, unlike oc_contrib's engine deep bucket — different fills/sizes,
  not a contradiction: the engine's deep losses come with agent sizing
  and live R2 TP selection.)
- Tails: QUICK cuts DD vs BASE in 2/5 (2021-22) but NODEEP is the
  smallest tail in 3/5 (2022/2023/2025); QUICK is not-worse than BOTH in
  only 2021. Raw (non-renormalised) sums show the same 1/5 pattern
  (BASE vs QUICK: 2.39/0.18/3.81/2.58/0.71 vs
  2.17/0.31/3.50/2.22/0.54), so the verdict does not hinge on
  renormalisation.
- Repro: `research/tournament/oc_deeptp/{PLAN.md,quick.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_deeptp.py` (12 tests
  pass); one process, peak RAM ~0.4 GB (float32 1m arrays).

## Verdict
VERDICT: NOT PROMISING — deep-rung TP 0.5 sigma beats both the TP-1.0 base and deep-removal on the yearly sum in only 1/5 years with maxDD not worse than both in only 1/5, so the quick deep exit is rejected and deep rungs keep the agent TP.
