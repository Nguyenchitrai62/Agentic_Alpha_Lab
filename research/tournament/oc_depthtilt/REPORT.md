# oc_depthtilt REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup

Exact oc_dipexit D0 replica (TP 1sg, close5 stop 4sg, 8sg backstop, timeout
at next-bar open; maker 0.0002 / taker 0.00055; v293 settle funding) with
oc_b1deeper B1 sizes w_base = 1/(1+n_fill), majors x R2 depths 2.5..5.0,
live offsets 16..238 strict trade-through, 5 anchor years 2021-09-24..
2025-09-24, all four clock phases (4h grid from 2020-08-01 00:00 UTC +
0/1/2/3h). RULE: depth tilt w_rule = w_base * t(k) with frozen
t = k/2.5 renormalised per coin-bar to sum 5.0 (0.6944/0.8333/0.9722/1.1111/
1.3889; ex-ante exposure neutral). Fills/lv/y/n identical across arms (same
membership); only sizing differs. Both arms pass through a v421-style
G = 2.0 gross-cap walk per (phase, bar) ordered by (f, k, coin), cut to
room, skip when full (equity = 1). PRIMARY = cap-adjusted wk*y 4-phase
means; uncapped w*y is a side row. Control per year: S_ctrl_bar =
R(Y) * S_base_bar with R(Y) = realised_rule(Y)/realised_base(Y) pooled.
POST-HOC origin labelled: motivated by oc_saturation (0.19%/unit at 2.5sg
vs 0.51-0.58% at 5sg). All 5 years are research data: a PROMISING result
would still need prospective validation (disclosed vs RULES.md hidden-year
rule).

## Fidelity

n_candidates 22312 (= oc_bidttl/oc_placebo_dip ledger exactly); phase-0
uncapped base raw sums 2.388052/0.182865/3.809764/2.579274/0.711509 =
placebo ref to 1e-6; pooled cap base n=8945 sum=13.2304 DD=1.4857
win=67.4% = oc_bidttl base exactly. Checksum ae59061350564158.

## Results per year (4-phase means, PRIMARY cap-adjusted wk*y)

| year | S_base -> S_rule (delta) | DD_base -> DD_rule | W_base -> W_rule | N_base -> N_rule (R) | ppf_base -> ppf_rule | ctrl S_ctrl (gain) | sum | dd | ctrl |
|---|---|---|---|---|---|---|---|---|---|
| 2021-09-24 | 0.5069 -> 0.4898 (-0.0171) | 0.3463 -> 0.2939 | -0.2638 -> -0.2350 | 333.61 -> 299.97 (0.899) | 0.00152 -> 0.00163 | 0.4558 (+0.0340) | no | yes | yes |
| 2022-09-24 | 0.2708 -> 0.2852 (+0.0144) | 0.4639 -> 0.3910 | -0.2432 -> -0.2264 | 351.08 -> 319.71 (0.911) | 0.00077 -> 0.00089 | 0.2466 (+0.0386) | yes | yes | yes |
| 2023-09-24 | 1.2960 -> 1.1519 (-0.1441) | 0.2379 -> 0.1992 | -0.1925 -> -0.1792 | 457.55 -> 411.20 (0.899) | 0.00283 -> 0.00280 | 1.1647 (-0.0128) | no | yes | NO |
| 2024-09-24 | 1.1702 -> 1.2045 (+0.0343) | 0.2409 -> 0.2141 | -0.1816 -> -0.1641 | 365.40 -> 328.53 (0.899) | 0.00320 -> 0.00367 | 1.0522 (+0.1523) | yes | yes | yes |
| 2025-09-24 | 0.0637 -> 0.1099 (+0.0462) | 0.3105 -> 0.2881 | -0.1648 -> -0.1689 | 349.81 -> 318.70 (0.911) | 0.00018 -> 0.00034 | 0.0581 (+0.0519) | yes | yes | yes |

Full pooled path (all phases, cap-adjusted): base n=8945 realised=7429.8
sum=13.2304 ppf=0.00178 DD=1.4857 win=67.4%; rule n=12005 realised=6712.4
sum=12.9653 ppf=0.00193 DD=1.3977 win=67.9%. 5y 4-phase-mean sum delta
dSum5y_cap = -0.0663 (gate +0.273). Legs: sum 3/5, DD 5/5, ctrl 4/5.

## Uncapped side row (w*y 4-phase means; same four checks, descriptive only)

| year | S_base -> S_rule (delta) | DD_base -> DD_rule | gain over ctrl | sum/dd/ctrl |
|---|---|---|---|---|
| 2021 | 0.9113 -> 0.8094 (-0.1019) | 0.8559 -> 0.7454 | +0.0603 | no/yes/yes |
| 2022 | 0.8326 -> 0.7401 (-0.0925) | 0.9506 -> 0.8482 | +0.0359 | no/yes/yes |
| 2023 | 2.0998 -> 1.8040 (-0.2958) | 0.8000 -> 0.6643 | +0.0473 | no/yes/yes |
| 2024 | 3.1974 -> 2.8363 (-0.3611) | 0.3545 -> 0.2941 | +0.2098 | no/yes/yes |
| 2025 | 0.6772 -> 0.6532 (-0.0240) | 0.6073 -> 0.5402 | +0.1010 | no/yes/yes |

dSum5y_unc = -0.8753. Full pooled uncapped: base sum=30.8732 ppf=0.00219
DD=3.1266; rule sum=27.3721 ppf=0.00234 DD=2.8744 (same 22312 fills).

## Tilt mechanics (uncapped, pooled phases; confirms the motive, refutes the trade)

| k | tilt t(k) | fills n | ppf_base (=ppf_rule, same fills) |
|---|---|---|---|
| 2.5 | 0.6944 | 9028 | 0.00151 (0.151%) |
| 3.0 | 0.8333 | 5690 | 0.00236 (0.236%) |
| 3.5 | 0.9722 | 3737 | 0.00296 (0.296%) |
| 4.0 | 1.1111 | 2562 | 0.00355 (0.355%) |
| 5.0 | 1.3889 | 1295 | 0.00393 (0.392%) |

P&L per unit filled notional rises monotonically with depth (same direction
as the oc_saturation motive), and the rule's pooled ppf beats base pooled
(0.00193 vs 0.00178 capped; 0.00234 vs 0.00219 uncapped). But fills
concentrate shallow (9028 at 2.5sg vs 1295 at 5sg), so realised exposure
falls ~10% every year (R = 0.899-0.911) and total sums lose: 0/5 uncapped,
3/5 capped. Under the cap the rule keeps MORE fills (12005 vs 8945, cheap
shallow rungs fit better) yet still loses 2021/2023 sums.

## Notes

- DD improves in 5/5 years in both regimes (lower realised exposure), and
  the rule beats its exposure-matched control in 4/5 capped (all but 2023)
  and 5/5 uncapped — allocation helps per-unit, but not enough in totals.
- 2023 is the double failure (sum -0.144 capped, control -0.013): the one
  year where even per-unit ppf does not improve (0.00283 -> 0.00280).
- Repro: `research/tournament/oc_depthtilt/{PLAN.md,depthtilt.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_depthtilt.py` (11 tests
  pass); one process, peak RAM < 3 GB (float32 1m arrays), full run via
  scripts/heavy_slot.py --tag oc_depthtilt.

## Verdict

VERDICT: NOT PROMISING — depth-tilted rung sizing wins capped sums in only 3/5 years with 5y delta -0.066 (gate +0.273); deep rungs earn more per unit notional (0.15% -> 0.39%) but fill too rarely, so the tilt loses ~10% realised exposure and total P&L.
