# oc_k2placebo — REPORT (2026-10-07, diagnostic only)

Question: is the Kronos K2 dip tilt's post-release gain (+0.15 %/month in
oc_kronoshidden) distinguishable from random timing? Nothing here selects or
changes anything. Dev years 2021..2024 are inside Kronos' pretraining (UPPER
BOUND); only the post-release year 2025-09-24 .. 2026-09-23 is clean.

## Reproduction gate: PASS

- `compute_placebo_dip.build_base()` verbatim: n_fills = 22312, 4-phase-mean
  base sums [0.911273, 0.832599, 2.099814, 3.197390, 0.677229], sum5y =
  7.718304 (gate 7.718304 ± 0.002). Per-coin/phase fills match REPORT exactly.
- K2 join coverage 100% (0 missing of 22,312 fills); multiset {0.75, 1.0, 1.25}.
- K2 rule: risk = -low1, fits.json per-year dir (+1 all) / q20 / q80, hi/lo =
  1.25/0.75, missing -> 1. Year y uses anchor-y fit on all 4 shifts.
- Decision-mean cross-check vs ctrl.json K2: y0 0.887055, y1 0.942249,
  y3 0.958048, y4 0.944587 exact; y2 0.983584 vs 0.983761 (diff 0.000177:
  leap-day — ctrl caps years at 365 d, this study uses [A, A_next) so y2 holds
  43,920 not 43,800 decision rows. Fills/replica unaffected; diagnostic only).

## Per-year sums (w*y units, 4-phase mean; norm = k2 / realised fill-mean)

| year | n_fills | base | k2 raw | realised_mean | norm | k2-base raw |
|---|---|---|---|---|---|---|
| 2021-09-24 | 4171 | 0.911273 | 0.803292 | 0.886718 | 0.905916 | -0.107981 |
| 2022-09-24 | 4059 | 0.832599 | 0.968161 | 0.953067 | 1.015837 | +0.135562 |
| 2023-09-24 | 5352 | 2.099814 | 2.306732 | 1.027420 | 2.245170 | +0.206918 |
| 2024-09-24 | 3958 | 3.197390 | 3.166103 | 1.004990 | 3.150383 | -0.031287 |
| 2025-09-24 (clean) | 4772 | 0.677229 | 0.704105 | 0.936976 | 0.751465 | +0.026876 |

## Placebos (1000 perms/year; pct = 100*(1+#{perm<=actual})/1001; >= 95 = signif.)

Timing (uniform bar-level shuffle within year, seed 20261007):

| year | actual_norm | p5 | p50 | p95 | percentile |
|---|---|---|---|---|---|
| 2021 | 0.905916 | 0.805204 | 0.909875 | 1.016220 | 46.85 |
| 2022 | 1.015837 | 0.731202 | 0.823594 | 0.926362 | 100.00 |
| 2023 | 2.245170 | 1.932329 | 2.011608 | 2.098033 | 100.00 |
| 2024 | 3.150383 | 2.996237 | 3.047664 | 3.099862 | 99.90 |
| 2025 clean | 0.751465 | 0.622420 | 0.683895 | 0.740609 | 97.20 |

Block (42-bar = 7 d blocks per (sym, shift), seed 20261008):

| year | actual_norm | p5 | p50 | p95 | percentile |
|---|---|---|---|---|---|
| 2021 | 0.905916 | 0.821794 | 0.925023 | 1.022859 | 38.06 |
| 2022 | 1.015837 | 0.716247 | 0.807629 | 0.908117 | 100.00 |
| 2023 | 2.245170 | 1.938105 | 2.016214 | 2.090220 | 100.00 |
| 2024 | 3.150383 | 2.984232 | 3.043110 | 3.096119 | 100.00 |
| 2025 clean | 0.751465 | 0.614617 | 0.674753 | 0.735394 | 98.70 |

## Plain statement

YES — the post-release gain is significant at 5%: the actual normalised K2 sum
beats 972/1000 timing permutations (percentile 97.20) and 987/1000
persistence-preserving block permutations (98.70). The margin is modest (actual
0.751 vs timing null median 0.684 / p95 0.741; ~28 timing perms beat it), it is
one clean year only, and dev-year extremes (100th pct in 2022/2023) are
in-pretraining upper bounds, not evidence. 2021 shows no timing skill either
year (47th/38th pct). This rejects "pure random timing" for the clean year but
does not overturn oc_kronoshidden's REJECT (4.80 < 5.0 gate still fails).

## Leakage checks

- Feature timing: Kronos forecasts use only the 400 bars closing <= T (inherited
  from oc_kronoshidden Part A; this study only reads frozen low1 at the fill's
  own bar T — no future feature). Join key is (sym, shift = phase, T = bar open).
- Label windows: no labels fit here; D0 rung outcomes are mechanical
  stop/TP/timeout exits from the replica (inherited live 16..238 strict
  trade-through, v293 settle funding).
- Fit windows: fits.json reused frozen (harness rows t_exit < A - 7 d, shift-0
  only); year y uses anchor-y fit only, never a later anchor.
- Fill timing: replica fills inherited; permutations only reassign multipliers
  across bars within the same year (timing) or within the same (sym, shift,
  year) in 42-bar blocks — no outcome, price, or future information enters the
  shuffle (seeds 20261007/20261008 + year).

## Vietnamese verdict

K2 năm sạch đạt percentile 97,2 (timing) và 98,7 (block 7 ngày): hơn timing ngẫu
nhiên ở mức 5%, nhưng biên mỏng (chỉ hơn p95 một chút, một năm duy nhất).
Dev 2021 không có skill, dev 2022-2024 nằm trong pretraining nên chỉ là cận trên.
Kết luận: KHÔNG adopt — giữ nguyên REJECT của oc_kronoshidden, cần bằng chứng prospective.
