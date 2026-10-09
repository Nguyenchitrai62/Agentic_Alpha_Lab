# oc_toto — REPORT (2026-10-08; all stages complete, pytest 7/7)

Third foundation model (Datadog Toto-Open-Base-1.0, observability + public +
synthetic pretraining — likely the least crypto-contaminated of the three) as
a dip-size tilt, same T3 rule as K2/C2 (risk = -f_q10, x1.25 / x0.75 outer
quintiles). New information source: dev4 labelled nearly-clean (small residual
caveat), post-release year scored ONCE for all rows.

STATUS: DONE. Part A DONE (258,085 rows, 20/20 groups, zero NaNs, q-order 1.0).
Stage dev (16 sims) + stage last (16 sims, once) complete. Reproduction gates
PASS (REF == v421 G2, K2 == oc_kronoshidden K2, to the digit). Placebo DONE.

## Part A — features (DONE, FROZEN)

- `run_toto_4shift.py` via heavy_slot (GTX1650, 1063 s + queue): context = last
  512 log closes ending at the bar closing at T, horizon 1; f_q10/q50/q90 =
  (q - log C0)/sigma, sigma = SAME formula as Kronos' sigma. risk = -f_q10.
- Predictive-distribution sampling (PLAN-registered): one backbone forward per
  batch gives the next-patch Student-T-mixture distribution; 256 i.i.d. samples
  drawn from it with replace_extreme_values (same as TotoForecaster), sample
  quantiles as q10/q50/q90. Same distribution the forecaster's single patch
  iteration samples (horizon 1); dummy + real-BTC equivalence checked pre-run
  (within 256-sample noise). torch seed 20261008; toto-ts 0.2.0 (--no-deps +
  minimal pure-python adds: jaxtyping, beartype, gluonts 0.17.0, rotary-embedding,
  lightning + lightning-utilities + torchmetrics + toolz; .venv torch 2.12.1+cu126
  used, no shadow). Timestamps: zeros + constant 14400 s (quick-start convention).
- Causality: forecast for T uses only closes of bars closing <= T (truncation /
  timing tests in tests/test_oc_toto.py). Pooled Spearman(Toto risk, Kronos risk)
  = 0.29 — weakly related, i.e. genuinely different signals (per-year 0.16 / 0.37
  / 0.34 / 0.30 / 0.17).

## Part-B fits (harness rows only, shift-0, 7d embargo)

| anchor | dir | rho(risk,y_dep) | q20 | q80 | n |
|---|---|---|---|---|---|
| 2021 | +1 | 0.0275 | 1.0018 | 2.0008 | 2,017 |
| 2022 | +1 | 0.0606 | 0.9848 | 1.9809 | 3,826 |
| 2023 | +1 | 0.0920 | 0.9204 | 1.9220 | 5,681 |
| 2024 | +1 | 0.0937 | 0.8982 | 1.8661 | 8,024 |
| 2025 | +1 | 0.0784 | 0.9030 | 1.8256 | 9,735 |

All five anchors +1 (high risk favourable, same sign as K2/C2); train rho is
the WEAKEST of the three models (Kronos 0.019..0.084, Chronos 0.036..0.129).
Coverage 9,779/10,100 majors rows.

## Dev results (NEARLY CLEAN — small residual public-corpus caveat, upper bound)

| row | y0 | y1 | y2 | y3 | mean | WORST | DDmax |
|---|---|---|---|---|---|---|---|
| REF | 2.588 | 3.282 | 6.045 | 10.677 | 5.601 | 2.588 | 16.91 |
| T3 | 2.486 | 3.254 | 5.996 | 10.684 | 5.557 | 2.486 | 15.65 |
| K2 | 2.469 | 3.478 | 6.679 | 10.653 | 5.772 | 2.469 | 16.20 |
| T3K2 | 2.354 | 3.374 | 6.467 | 10.606 | 5.652 | 2.354 | 15.84 |

Robust pick on dev4 only (informational): T3 (all DD <= 20, no losing year, all
mean >= 5; highest WORST: T3 2.486 > K2 2.469 > T3K2 2.354) — but T3's mean
(5.557) trails REF (5.601); the tilt adds nothing on dev mean.

## Most-recent-year verdict (clean; scored ONCE)

| row | %/mo | DD | full-path DD | all win |
|---|---|---|---|---|
| REF | 4.648 | 12.90 | 16.82 | 0.6267 |
| T3 | 4.811 (+0.163) | 13.13 | 15.57 | 0.6273 |
| K2 | 4.801 (+0.153) | 12.10 | 16.09 | 0.6263 |
| T3K2 | 4.829 (+0.181) | 12.45 | 15.78 | 0.6269 |

5y geo mean: REF 5.410 / T3 5.407 / K2 5.577 / T3K2 5.487, no losing year
anywhere, full-path DD <= 20 everywhere. T3 beats REF by +0.163 with lower
full-path DD; the pre-registered T3K2 ensemble is best (+0.181, DD 15.78).
NONE reaches the 5.0 gate on the clean year.

## Timing placebo (T3, replica ledger reused, 1000 perms)

| year | timing pct | block pct |
|---|---|---|
| 2021 | 37.26 | 27.37 |
| 2022 | 0.50 | 0.50 |
| 2023 | 100.00 | 100.00 |
| 2024 | 100.00 | 100.00 |
| 2025-09-24 clean | 100.00 | 100.00 |

T3 timing is SIGNIFICANT on the clean year (>= 95), like K2 (97.2) and C2
(99.2) — a third foundation model with different pretraining carries timing
signal. (2022 replica-ledger placebo is at the floor for all three models'
tilts; engine-year y1 stays positive.)

## Leakage statement

Feature timing (512 closes <= T, truncation-tested); label windows (harness
t_exit < A - 7d inherited); fit windows (shift-0 only + 7d embargo, anchor-y
fit for year y); fill timing (win_start=5 + 1m trade-through + stop-first,
engine). No statistic from any test year feeds any choice. Gate costs inside
the engine (maker 0.0002 / taker 0.00055 / longs pay 0.0001 per 8h).

## Vietnamese verdict

T3 đạt 4,81%/tháng ở năm sạch (+0,16 so với G2, timing có ý nghĩa 100%),
ensemble T3K2 tốt nhất (+0,18, DD 15,78) nhưng TẤT CẢ vẫn dưới cổng 5%.
Ba foundation model khác pretraining (Kronos, Chronos, Toto) đều có timing
signal độc lập — tín hiệu "next-bar low risk" là generic, không phải đặc thù Kronos.
Kết luận: REJECT as a standalone tilt — giữ T3/T3K2 làm bằng chứng độc lập thứ ba
củng cố K2/C2, cần thêm bằng chứng prospective trước khi đưa vào G2.
