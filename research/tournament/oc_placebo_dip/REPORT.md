# oc_placebo_dip REPORT (2026-10-06)

## Setup
False-positive rate of the dip-screen PROMISING criterion. Replica: exact
oc_dipexit D0 rung outcomes (TP 1sg, close5 stop 4sg, 8sg backstop, timeout at
next-bar open; maker 0.0002 / taker 0.00055; v293 settle funding) with
oc_b1deeper B1 sizes w = 1/(1+n_fill), on all four clock phases (4h grid from
2020-08-01 00:00 UTC + 0/1/2/3h), majors x R2 depths 2.5..5.0, live offsets
16..238 strict trade-through, bars with open in [2021-09-24, 2026-09-24).
300 seeded placebo rules (seed 20261006), 100 per shape, selection by
splitmix64 hash of (rule, phase, bar time, coin, rung) + seed — never returns:
(A) weight x0.8/x1.2 (one per rule) on a random 10-20% of bars;
(B) skip 10% of fills; (C) TP x0.9/x1.1 (one per rule) on a random 20% of
fills (exact y0.9/y1.1 legs, same race/fees). Criterion per year on 4-phase
means: sum >= base AND maxDD not worse by > 1pp (0.01); PROMISING iff both in
>= 4/5 years. dSum5y = 5y 4-phase-mean sum delta; base 5y sum = 7.718.

## Replica fidelity (base, B1 raw w*y sums)
Phase-0 fills/coin 1067/1126/952/1179/1174 and sums 2.388/0.183/3.810/2.579/
0.712 = oc_dipexit/oc_stoptf to 1e-3; 4-phase-mean sums 0.911/0.833/2.100/
3.197/0.677 and DDs 0.856/0.951/0.800/0.355/0.607 = oc_stoptf D0 exactly.
Ledger 22312 fills (= oc_stoptf n_rungs), checksum 902c5bbfe8fed3c0.

## Pass rates per shape (n=100 each; pooled full FPR 20/300 = 6.7%)
| shape | full PROMISING | sum-half >=4/5 | DD-half >=4/5 |
|---|---|---|---|
| A size tilt | 6% (6) | 40% (40) | 54% (54) |
| B skip 10% | 0% (0) | 0% (0) | 100% (100) |
| C TP jitter | 14% (14) | 15% (15) | 81% (81) |

## Placebo distributions (w*y units)
| shape | dSum5y mean/sd/p5/p50/p95/max | dDDmean mean/p95 | dDDfull mean/p95 |
|---|---|---|---|
| A | -0.006/0.259/-0.393/-0.015/+0.342/+0.449 | +0.002/+0.043 | -0.012/+0.230 |
| B | -0.782/0.147/-1.000/-0.779/-0.493/-0.361 | -0.064/-0.040 | -0.277/-0.046 |
| C | -0.036/0.090/-0.166/-0.033/+0.102/+0.137 | +0.002/+0.015 | -0.041/+0.052 |

## Stricter gates (pre-registered)
Pooled dSum5y p95 = +0.273 (A +0.342, B -0.493, C +0.102); 2%-of-base = +0.154.
| rule | A | B | C | pooled |
|---|---|---|---|---|
| S1 full legs + dSum >= pooled p95 | 2% | 0% | 0% | 0.7% |
| S1 full legs + dSum >= max shape p95 | 1% | 0% | 0% | 0.3% |
| S1 full legs + dSum >= 2% of base | 6% | 0% | 0% | 2.0% |
| S2 sum-half + dSum >= pooled p95 | 15% | 0% | 0% | — |

## Notes
- The sum-half alone is weak: random size tilts win 4/5 years 40% of the time
  (context: the real S15 close15 stop won sums 4/5 yet failed DD and was
  rejected — a 4/5 sum win without the DD leg proves little).
- The DD-half alone is toothless against smaller books: skipping 10% of fills
  passes it 100/100 (less exposure = lower DD); it only bites when the full
  legs are required jointly (B full FPR 0%).
- S2 (sum-half + tail) still lets 15% of shape-A placebos through, so the DD
  leg must be kept: only S1 variants hold every shape <= 5%.

## Verdict
VERDICT: The dip screen's joint criterion lets 6.7% of placebo rules through (up to 14% for TP-jitter shapes, 40% on the sum-half alone) — require the full PROMISING legs PLUS 5y 4-phase-mean sum delta >= pooled placebo p95 (+0.273, ~3.5% of base), which cuts the false-positive rate to 0.7% pooled (<= 2% per shape).
