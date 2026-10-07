# oc_b1soft REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
SOFT correlation count vs hard B1(F) on shared static-bid fills: majors x
R2 depths (2.5/3/3.5/4/5), bars with open in [2021-09-24, 2026-09-24) (5
anchor years); d_b = (O_b-C_b(f-1))/(O_b*sg_b) at the fill minute;
n_soft = sum clip((d_b-1)/1.5,0,1), w = 1/(1+n); arms B1(F=2.5/2.0/1.5)
(w = 1/(1+#{d_b>=F})) and SOFT share identical fills/returns (D0 replica
from px=lv; maker 0.0002 / taker 0.00055; longs pay 0.0001 on settling
timeouts). Daily sums by exit date UTC; maxDD of cumulative daily-sum
path from 0; efficiency = sum/maxDD. B1(F=2.5) fills 5498 =
oc_b1deeper B1 to the tick per coin (1067/1126/952/1179/1174) plus
d-form/price-form parity on all 5498 fills — replica validated. Ledger
checksum be45add4e8bb0309. All 5 years are research data: a PROMISING
result would still need prospective validation (disclosed vs RULES.md
hidden-year rule).

## Per-year efficiency, RENORMALISED w (primary; equal exposure)
| year | B1(2.5) S/W/DD/E | B1(2.0) S/W/DD/E | B1(1.5) S/W/DD/E | SOFT S/W/DD/E |
|---|---|---|---|---|
| 2021 | 3.887/-0.720/0.720/5.40 | 3.495/-0.912/0.912/3.83 | 2.995/-1.187/1.187/2.52 | 3.200/-1.002/1.002/3.19 |
| 2022 | 0.272/-1.082/1.699/0.16 | -0.111/-1.181/1.985/-0.06 | -0.879/-1.462/2.502/-0.35 | -0.714/-1.301/2.277/-0.31 |
| 2023 | 5.725/-0.400/0.409/14.01 | 5.456/-0.453/0.464/11.76 | 5.534/-0.418/0.418/13.26 | 5.581/-0.404/0.404/13.81 |
| 2024 | 3.959/-0.332/0.332/11.92 | 4.027/-0.439/0.439/9.17 | 3.960/-0.621/0.621/6.38 | 3.923/-0.558/0.558/7.03 |
| 2025 | 1.210/-0.903/1.130/1.07 | 1.466/-0.806/0.953/1.54 | 1.860/-0.833/0.959/1.94 | 1.668/-0.860/1.010/1.65 |
| FULL | 15.138/-/1.787/8.47 | 14.274/-/2.251/6.34 | 13.147/-/3.000/4.38 | 13.432/-/2.664/5.04 |

## Per-year efficiency, RAW w (descriptive; lower mean exposure for softer counts)
| year | B1(2.5) Sr/DDr/Er | B1(2.0) Sr/DDr/Er | B1(1.5) Sr/DDr/Er | SOFT Sr/DDr/Er |
|---|---|---|---|---|
| 2021 | 2.388/0.442/5.40 | 1.611/0.420/3.83 | 1.006/0.399/2.52 | 1.137/0.356/3.19 |
| 2022 | 0.183/1.142/0.16 | -0.063/1.125/-0.06 | -0.399/1.135/-0.35 | -0.329/1.049/-0.31 |
| 2023 | 3.810/0.272/14.01 | 2.940/0.250/11.76 | 2.299/0.173/13.26 | 2.395/0.173/13.81 |
| 2024 | 2.579/0.216/11.92 | 2.025/0.221/9.17 | 1.509/0.236/6.38 | 1.541/0.219/7.03 |
| 2025 | 0.712/0.665/1.07 | 0.622/0.404/1.54 | 0.560/0.289/1.94 | 0.542/0.328/1.65 |

## Decision (PROMISING = SOFT eff > B1(2.5) AND > B1(2.0) in >=4/5 yrs, strict)
| year | SOFT>B1(2.5)? | SOFT>B1(2.0)? | PASS? (renorm / raw) |
|---|---|---|---|
| 2021 | 3.19<5.40 NO | 3.19<3.83 NO | NO / NO |
| 2022 | -0.31<0.16 NO | -0.31<-0.06 NO | NO / NO |
| 2023 | 13.81<14.01 NO | 13.81>11.76 yes | NO / NO |
| 2024 | 7.03<11.92 NO | 7.03<9.17 NO | NO / NO |
| 2025 | 1.65>1.07 yes | 1.65>1.54 yes | YES / YES |
| score | renorm 1/5, raw 1/5 | | PROMISING: NO |

## Notes
- SOFT beats both hard arms only in 2025 (the only year B1(2.5) is not
  the efficiency leader); in 2023 it beats B1(2.0) but not B1(2.5)
  (13.81 vs 14.01). Under equal exposure its renormalised DD is worse
  than B1(2.5) in 4/5 years (1.00/2.28/0.56/1.01 vs 0.72/1.70/0.33/
  1.13 in 2021/2022/2024/2025) — partial credit adds exposure exactly
  on jointly-soft days that then draw down together.
- Raw sums are lower for softer counts in every year (mean weight:
  SOFT < B1(1.5) < B1(2.0) < B1(2.5) by construction), so the verdict
  does not hinge on renormalisation (raw pass count is also 1/5).
- Repro: `research/tournament/oc_b1soft/{PLAN.md,soft.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_b1soft.py` (12 tests
  pass); one process, peak RAM ~0.4 GB (float32 1m arrays).

## Verdict
VERDICT: NOT PROMISING — SOFT's efficiency beats both B1(2.5) and B1(2.0) in only 1/5 years (2025), so the soft correlation count is rejected and hard B1(F=2.5) stands.
