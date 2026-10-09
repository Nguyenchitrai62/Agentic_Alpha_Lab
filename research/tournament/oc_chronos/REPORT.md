# oc_chronos — REPORT (2026-10-08; all stages complete, pytest 6/6)

Second foundation model (Amazon Chronos-Bolt-small, released 2024-11, mostly
non-crypto + synthetic pretraining) as a dip-size tilt, same C2 rule as K2
(risk = -ch_q10, x1.25 / x0.75 outer quintiles). New information source: dev4
labelled possibly-contaminated, post-release year scored ONCE for all rows.

STATUS: DONE. Part A DONE (258,085 rows, 20/20 groups, zero NaNs, q-order 1.0).
Stage dev (16 sims) + stage last (16 sims, once) complete. Reproduction gates
PASS (REF == v421 G2, K2 == oc_kronoshidden K2, to the digit). Placebo DONE.

## Part A — features (DONE, FROZEN)

- `run_chronos_4shift.py` via heavy_slot (GTX1650, 734 s): context = last 512
  closes (log) ending at the bar closing at T, horizon 1, quantiles 0.1..0.9;
  ch_q10/q50/q90 = (q - log C0)/sigma, sigma = SAME formula as Kronos' sigma.
  Deterministic quantile heads (seed 20261007); chronos-forecasting 2.3.2,
  transformers 5.19.0, model revision None (HF hub default).
- Env repair (before any outcome, no result affected): pylib had pulled a
  broken torch 2.14.1 shadowing .venv's working CUDA torch; removed the
  torch/numpy/pandas shadows from pylib so .venv torch 2.12.1+cu126 is used.
- Causality: forecast for T uses only closes of bars closing <= T (truncation
  test in tests/test_oc_chronos.py). Pooled Spearman(Chronos risk, Kronos
  risk) = 0.22 — weakly related, i.e. genuinely different signals.

## Part-B fits (harness rows only, shift-0, 7d embargo)

| anchor | dir | rho(risk,y_dep) | q20 | q80 | n |
|---|---|---|---|---|---|
| 2021 | +1 | 0.0364 | 1.1101 | 2.8608 | 2,017 |
| 2022 | +1 | 0.0760 | 1.1847 | 3.0251 | 3,826 |
| 2023 | +1 | 0.1287 | 1.0736 | 2.7737 | 5,681 |
| 2024 | +1 | 0.1187 | 1.0644 | 2.6502 | 8,024 |
| 2025 | +1 | 0.1126 | 1.0743 | 2.5977 | 9,735 |

All five anchors +1 (high risk favourable, same sign as K2); train rho is
STRONGER than Kronos' (0.019..0.084). Coverage 9,779/10,100 majors rows.

## Dev results (UPPER BOUND — possibly in Chronos pretraining)

| row | y0 | y1 | y2 | y3 | mean | WORST | DDmax |
|---|---|---|---|---|---|---|---|
| REF | 2.588 | 3.282 | 6.045 | 10.677 | 5.601 | 2.588 | 16.91 |
| C2 | 2.711 | 3.460 | 6.250 | 10.721 | 5.739 | 2.711 | 15.48 |
| K2 | 2.469 | 3.478 | 6.679 | 10.653 | 5.772 | 2.469 | 16.20 |
| C2K2 | 2.452 | 3.440 | 6.593 | 10.717 | 5.752 | 2.452 | 15.61 |

Robust pick on dev4 only (informational): C2 (all DD <= 20, no losing year,
all mean >= 5; highest WORST: C2 2.711 > K2 2.469 > C2K2 2.452).

## Most-recent-year verdict (clean; scored ONCE)

| row | %/mo | DD | full-path DD | all win |
|---|---|---|---|---|
| REF | 4.648 | 12.90 | 16.82 | 0.6267 |
| C2 | 4.754 (+0.106) | 12.86 | 15.42 | 0.6276 |
| K2 | 4.801 (+0.153) | 12.10 | 16.09 | 0.6263 |
| C2K2 | 4.776 (+0.128) | 12.38 | 15.52 | 0.6268 |

C2 beats REF by +0.106 with lower DD, but trails K2 (+0.153); the ensemble
sits between them. NONE reaches the 5.0 gate. The dev4 robust pick (C2) did
not transfer to the clean year — same lesson as v189-v197.

## Timing placebo (C2, replica ledger reused, 1000 perms)

| year | timing pct | block pct |
|---|---|---|
| 2021 | 90.11 | 85.61 |
| 2022 | 88.31 | 89.01 |
| 2023 | 100.00 | 100.00 |
| 2024 | 100.00 | 100.00 |
| 2025-09-24 clean | 99.20 | 98.90 |

C2 timing is SIGNIFICANT on the clean year (>= 95), like K2 (97.2) — a second
foundation model with different pretraining carries timing signal.

## Leakage statement

Feature timing (512 closes <= T, truncation-tested); label windows (harness
t_exit < A - 7d inherited); fit windows (shift-0 only + 7d embargo, anchor-y
fit for year y); fill timing (win_start=5 + 1m trade-through + stop-first,
engine). No statistic from any test year feeds any choice. Gate costs inside
the engine (maker 0.0002 / taker 0.00055 / longs pay 0.0001 per 8h).

## Vietnamese verdict

C2 đạt 4,75%/tháng ở năm sạch (+0,11 so với G2, timing có ý nghĩa 99,2%)
nhưng vẫn dưới cổng 5% và thua K2 (4,80%); ensemble C2K2 nằm giữa (4,78%).
Dev mạnh không chuyển sang năm sạch, nên không adopt tilt nào.
Kết luận: REJECT as a standalone tilt — giữ C2 làm bằng chứng độc lập củng
cố K2 (hai foundation model khác pretraining đều có timing signal), cần thêm
bằng chứng prospective trước khi đưa vào G2.
