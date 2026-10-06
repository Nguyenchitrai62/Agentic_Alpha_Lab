# oc_discsniper REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup

Spot-perp DISCOUNT sniper (idea #75): at each 4h close T (4 clock phases
2020-08-01 +0/1/2/3h), z = (15-min mean premium using T-15..T-1 minus trailing
1440 overlapping 15-min means ending 1 min before cur, min 1200, ddof=1) with
all inputs strictly before T; if z < -2, perp BUY limit at O(T)x(1-0.001)
valid 60 min, fill only on STRICT 1m trade-through at offsets 5..59 (maker
0.02%); stop sl = fillx(1-4sg) close5 ((m+1)%5==0, next-open market taker
0.055%), premium exit at first p15 >= 0 (next-open limit maker 0.02%), else
next-bar open (taker); stop-first ties; gate funding 0.01%/settlement in
(Tfill,Texit]; size 0.25/coin (contribution c = 0.25xy; sums in portfolio
units, raw y-sums = 4x). sg = 360-bar 4h-open std (shift 1, min 120, same as
oc_b1deeper). Bars with T+240 past 2026-09-24 skipped; NaN exits dropped
(0 disc, 0 dip). Dip reference rebuilt per phase (D0 TP1/sl4-close5/bl8/timeout
+ B1 w = 1/(1+n), R2 depths, live 16..238, v399-exact n). Placebo: 300 rules,
seed 20261006, per (phase,year,coin) K = real trigger count, random bars w/o
replacement from valid-sigma/O bars, identical exits. 6175 disc fills
(BTC 987 / ETH 1062 / SOL 1302 / BNB 1524 / XRP 1300; exits time 4544 /
premium 1568 / stop 63), 22251 dip fills (win 70.2%). Ledger checksum
26a9873d3ed5da4b. All 5 years are research data (assignment override of the
old RULES.md cut); a PROMISING result would still need prospective validation.

## Per-year sleeve (4-phase means in portfolio units; per-phase detail in results.json)

| year | S_bar (4-phase-mean sum) | > 0? | per-phase n / win / sum / worst / DD |
|---|---|---|---|
| 2021 | -0.1790 | no | p0 277/.433/-0.115/-0.045/0.161; p1 294/.463/-0.151/-0.062/0.199; p2 321/.396/-0.249/-0.052/0.271; p3 300/.420/-0.202/-0.033/0.239 |
| 2022 | -0.0305 | no | p0 289/.491/+0.044/-0.019/0.045; p1 284/.447/+0.011/-0.058/0.079; p2 281/.477/-0.054/-0.057/0.107; p3 267/.479/-0.124/-0.088/0.183 |
| 2023 | -0.0773 | no | p0 315/.406/-0.112/-0.102/0.211; p1 286/.336/-0.136/-0.050/0.150; p2 310/.387/-0.028/-0.018/0.077; p3 323/.461/-0.033/-0.025/0.109 |
| 2024 | -0.1318 | no | p0 320/.441/-0.084/-0.025/0.089; p1 293/.444/-0.072/-0.023/0.109; p2 345/.403/-0.188/-0.022/0.219; p3 333/.387/-0.183/-0.031/0.186 |
| 2025 | -0.1107 | no | p0 339/.410/-0.150/-0.040/0.156; p1 330/.415/-0.151/-0.162/0.200; p2 359/.435/-0.016/-0.029/0.061; p3 309/.392/-0.126/-0.021/0.126 |

5y real total R (sum of yearly 4-phase means) = -0.5291. Disc win overall
42.5%, mean y -13.7 bps/trade. Overlap with dip (same coin, |Tf-Td| <= 240
min): 25.5% overall (20.9-30.0% per cell, see results.json).

## Correlation (daily P&L, disc c vs dip w*y; missing dates 0)

Overall pooled (phase,date) r = +0.045. Per year: 2021 +0.032, 2022 -0.001,
2023 +0.011, 2024 -0.147, 2025 +0.290. Passes the < 0.5 leg everywhere, but
the sleeve loses money so there is nothing to diversify with.

## Placebo

300 seeded WAN triggers at matched counts per (phase,year,coin), same exits:
placebo 5y totals mean -0.452, std 0.068, range [-0.620, -0.196]; real -0.529
sits at percentile 13.3 (share of placebo <= real x100). The discount rule
underperforms the average random-timing rule with identical execution.

## Decision (PROMISING = S_bar > 0 in >= 4/5 yrs AND placebo >= 95 AND corr < 0.5)

| check | score | pass? |
|---|---|---|
| S_bar > 0 | 0/5 years | NO |
| placebo percentile >= 95 | 13.3 | NO |
| corr < 0.5 | 0.045 | YES |
| PROMISING | | NO |

## Notes

- The trigger fires often (8001 triggers -> 6175 fills, 77% fill rate) but
  the edge points the wrong way: 19 of 20 phase-years sum < 0, full-path
  sums negative on every phase, win rate 34-49% throughout. Premium recovery
  exits only 25% of fills; 74% ride to the next-bar timeout.
- Repro: `research/tournament/oc_discsniper/{PLAN.md,discsniper.py,run.py,
  results.json,fills_disc.parquet,fills_dip.parquet}` +
  `tests/test_oc_discsniper.py` (7 tests pass); one process via heavy_slot,
  peak RAM ~0.5 GB (float32 1m + premium arrays).
- No post-hoc change to hypothesis, definitions, thresholds, or decision rule.

## Verdict

VERDICT: NOT PROMISING — the discount sniper loses in 0/5 years on 4-phase-mean sums (5y -0.529), sits at placebo percentile 13.3, and is closed despite low dip correlation (+0.045).
