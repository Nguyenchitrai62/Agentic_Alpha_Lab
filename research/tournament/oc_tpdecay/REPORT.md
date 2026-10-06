# oc_tpdecay REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
B1 replica fills (static lv, strict low < lv, size 1/(1+n), v399-exact n) on
majors x R2 depths (2.5/3/3.5/4/5), bars with open in [2021-09-24, 2026-09-24)
(5 anchor years); paired exits from the same fill px: BASE = D0 fixed
TP px*(1+sg), DECAY = TP(t) = px*(1+sg*(1-0.5*(t-f)/(240-f))) on strict
high(t) > TP(t), exit at TP(t) maker; stops/backstop/timeout/funding
(0.0001 settling) and stop-first priority identical. Weights w = 1/(1+n),
renormalised per year pooled to mean 1 (primary); daily sums by exit date UTC
(per arm); maxDD of cumulative daily-sum path from 0. BASE replicates
oc_b1deeper B1 to the tick (per-year sums/means/win rates identical;
1067/1126/952/1179/1174 per coin, 5498 paired fills, 0 unpaired drops).
Ledger checksum 66936d0b894018af. All 5 years are research data: a PROMISING
result would still need prospective validation (disclosed vs RULES.md
hidden-year rule).

## Per-year BASE vs DECAY (renormalised w; mean in frac, win = net>0, to = timeout share)
| year | BASE n/mean/win/to/sum/worst/DD | DECAY n/mean/win/to/sum/worst/DD |
|---|---|---|
| 2021 | 990/38.1bp/.688/.445/3.887/-0.720/0.720 | 990/38.7bp/.703/.344/3.975/-0.723/0.723 |
| 2022 | 1045/3.8bp/.695/.396/0.272/-1.082/1.699 | 1045/5.1bp/.710/.286/0.456/-1.086/1.717 |
| 2023 | 1330/39.7bp/.773/.328/5.725/-0.400/0.409 | 1330/37.4bp/.783/.233/5.443/-0.398/0.398 |
| 2024 | 989/41.1bp/.699/.433/3.959/-0.332/0.332 | 989/43.3bp/.735/.313/4.157/-0.358/0.358 |
| 2025 | 1144/13.4bp/.656/.467/1.210/-0.903/1.130 | 1144/13.4bp/.679/.371/1.175/-0.913/1.146 |
| FULL | 5498/27.4bp/.705/.410/15.138/-1.138/1.787 | 5498/27.5bp/.725/.306/15.292/-1.142/1.807 |

## Leave-one-year-out sums (renormalised over kept 4 years; pass = dec >= base)
| drop | base | dec | pass? |
|---|---|---|---|
| 2021 | 11.305 | 11.374 | YES |
| 2022 | 15.036 | 14.996 | no |
| 2023 | 9.298 | 9.752 | YES |
| 2024 | 11.149 | 11.101 | no |
| 2025 | 13.737 | 13.920 | YES |
| LOYO pass rate | | | 3/5 |

## Decision (PROMISING = sum not lower in >=4/5 yrs AND maxDD not worse in >=4/5)
| check | score | pass? |
|---|---|---|
| S_dec >= S_base | 3/5 (2021 +0.09, 2022 +0.18, 2024 +0.20; 2023 -0.28, 2025 -0.04) | NO |
| DD_dec <= DD_base | 1/5 (only 2023, -0.01; worse by <=0.03 in 2021/2022/2024/2025) | NO |
| PROMISING | | NO |

## Notes
- The decaying TP does what it claims: timeout share falls ~10pp every year
  (full 41% -> 31%) and win rate rises every year (+1 to +4pp), converting
  timeouts into earlier smaller maker TPs.
- But the smaller TPs do not pay: full-path sum is only +0.15 above base
  (+1%), and the yearly-sum test fails in the two years that matter most for
  robustness (2023 strong-trend year -0.28, most-recent year -0.04); LOYO 3/5.
- Tails do not improve either: worst day is worse in 4/5 years (equal-ish,
  +/-0.03) and maxDD is worse in 4/5 years (only 2023 improves), so the
  timeout-to-TP conversion adds path risk rather than cutting it.
- Repro: `research/tournament/oc_tpdecay/{PLAN.md,tpdecay.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_tpdecay.py` (13 tests pass);
  one process, peak RAM ~0.4 GB (float32 1m arrays).

## Verdict
VERDICT: NOT PROMISING — decaying dip TP (1.0sg -> 0.5sg) cuts timeouts and lifts win rate every year but its yearly sum is not lower in only 3/5 years and its maxDD is not worse in only 1/5 years, so the fixed +1.0sg TP stands.
