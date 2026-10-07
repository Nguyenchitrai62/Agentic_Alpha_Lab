# oc_bookbrake REPORT — BOOK loss-cluster brake, idea #17 (2026-10-05; PLAN pre-registered before any outcome)

## Setup
Book = `forward_v205.research_books_d2` (rebuilt exactly); opens = v154 4h
opens. Grid 2021-09-24 00:00 .. 2026-09-23 20:00 (10956 scored 4h bars;
`r[t] = open[t+4h]/open[t]-1`, next open <= 2026-09-24 00:00 UTC bound).
Rule (fixed, single value): at bar start T, `scale[t] = 0.5` iff >= 3 losing
BASE book trades closed in `[T-72h, T)` (any coin), else 1.0; a book trade =
maximal constant-sign run per coin, `net = gross - 0.0005*(|w[a]|+intra+|w[b]|)`,
loss iff net < 0, closure = next bar open (strictly before T). Braked net =
scaled weights x returns minus 0.05% L1 turnover; legs = gross before costs.
Repro: `research/tournament/oc_bookbrake/{PLAN.md,compute_bookbrake.py,results.json}`.

## Trade census (base book, 5y)
1177 trades, 636 with net < 0 (closures scored: 635 — one trade ends on the
last bar, no closure event). Per coin (n / n_loss / 5y trade-net):
BNB 245/136/+0.425, BTC 200/114/+0.579, ETH 197/97/+0.375, SOL 235/130/+0.280,
XRP 300/159/+0.452. Brake-on share 13.6% full-period (9–20% per year).

## Per anchor year: book net P&L, maxDD (year-rebased), worst 42-bar week
| year | bars | brake% | ret base -> brake | maxDD base -> brake | worst-week base -> brake |
|---|---|---|---|---|---|
| 2021-09-24 | 2190 | 20.3 | +0.3058 -> +0.2826 | 0.1384 -> 0.1279 | -0.1037 -> -0.1089 |
| 2022-09-24 | 2190 | 9.1 | +0.3142 -> +0.3287 | 0.0723 -> 0.0714 | -0.0473 -> -0.0476 |
| 2023-09-24 | 2196 | 11.3 | +0.6869 -> +0.6223 | 0.0867 -> 0.0845 | -0.0690 -> -0.0690 |
| 2024-09-24 | 2190 | 16.3 | +0.6819 -> +0.5882 | 0.0653 -> 0.0600 | -0.0459 -> -0.0459 |
| 2025-09-24 | 2190 | 10.8 | +0.5401 -> +0.5047 | 0.0798 -> 0.0798 | -0.0696 -> -0.0696 |

## Same on the legs (gross, costs not allocated)
Long-leg ret base -> brake: 2021 +0.164->+0.143, 2022 +0.317->+0.362,
2023 +0.817->+0.702, 2024 +0.658->+0.568, 2025 +0.336->+0.336.
Long-leg maxDD: 2021 0.166->0.158, 2022 0.0747->0.0744, 2023 0.0566->0.0566,
2024 0.0730->0.0658, 2025 0.0958->0.0958.
Short-leg ret: 2021 +0.151->+0.151, 2022 +0.025->+0.004, 2023 -0.041->-0.015,
2024 +0.048->+0.048, 2025 +0.196->+0.170.
Short-leg maxDD: 2021 0.031->0.025, 2022 0.070->0.072 (worse), 2023 0.094->0.093,
2024 0.068->0.068, 2025 0.068->0.068.

## Decision
maxDD improves in 4/5 years (2025 tied, not strict); book P&L not lower in
1/5 (only 2022). Required >= 4/5 AND >= 3/5. Full-period net +6.50 base vs
+5.61 braked; full-path maxDD 0.138 -> 0.131.

## Verdict
VERDICT: NOT PROMISING — the brake trims book maxDD in 4/5 years but only by
<= 1.1pp while giving up 2–9pp of yearly net P&L in 4/5 years (worst week
never improves).

## Caveats
Vectorised open-to-open P&L only (0.05%/turnover, no vol target/governor,
SL/TP, funding, sleeve, or cross-year compounding; year stats year-rebased);
brake signal derived from BASE trades only (no recursion into braked sizes —
disclosed); leg paths gross only; tests `tests/test_oc_bookbrake.py` (4 pass:
trade split/flip-cost partition, window edges incl. strict-before-T,
brake causality under future perturbation, year-partition cover).
