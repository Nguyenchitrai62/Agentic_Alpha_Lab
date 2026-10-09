# oc_timesfm — REPORT (2026-10-08; all stages complete)

Third foundation model (Google TimesFM 2.5 200M PyTorch, released Sept 2025;
pretraining = GiftEvalPretrain + Wikimedia Pageviews + Google Trends + synthetic)
as a dip-size tilt, same T3 rule as K2/C2 (risk = -f_q10, x1.25 / x0.75 outer
quintiles). New information source: dev4 labelled possibly-contaminated UPPER
BOUND, post-release year scored ONCE for all rows.

STATUS: DONE. Part A DONE (258,085 rows, 20/20 groups, zero NaNs, q-order 1.0).
Stage dev (16 sims) + stage last (16 sims, once) complete. Reproduction gates
PASS (REF == v421 G2, K2 == oc_kronoshidden K2, to the digit; ledger base
sum5y == 7.718304, n == 22312). Placebo DONE.

## Part A — features (DONE, FROZEN)

- `run_timesfm_4shift.py` via heavy_slot (GTX1650, 2,644 s): context = last 512
  closes (log) ending at the bar closing at T, horizon 1, quantiles 0.1..0.9;
  f_q10/q50/q90 = (q - log C0)/sigma, sigma = SAME formula as Kronos' sigma.
  Deterministic quantile heads (seed 20261008); timesfm 3.0.2, model revision
  None (HF hub default at runtime).
- Contamination (frozen, model card fetched 2026-10-08): NO explicit crypto
  series in the card, but GiftEvalPretrain composition is undisclosed, so dev
  2021-2024 (overlapping Trends-to-EoY-2022 / Wiki-to-Nov-2023 windows) is a
  POSSIBLY-CONTAMINATED UPPER BOUND. Post-release year 2025-09-24..2026-09-23
  (after release AND all stated cutoffs) is the clean verdict.
- Causality: forecast for T uses only closes of bars closing <= T (truncation
  test in tests/test_oc_timesfm.py). Pooled Spearman(TimesFM risk, Kronos
  risk) = 0.33 harness-shift0 / 0.34 full universe — moderately related (more
  than C2's 0.22), i.e. partly overlapping but not the same signal.

## Part-B fits (harness rows only, shift-0, 7d embargo)

| anchor | dir | rho(risk,y_dep) | q20 | q80 | n |
|---|---|---|---|---|---|
| 2021 | +1 | 0.0707 | 1.4297 | 2.9152 | 2,017 |
| 2022 | +1 | 0.1081 | 1.3654 | 2.8991 | 3,826 |
| 2023 | +1 | 0.1404 | 1.2713 | 2.7326 | 5,681 |
| 2024 | +1 | 0.1342 | 1.2611 | 2.6046 | 8,024 |
| 2025 | +1 | 0.1232 | 1.2694 | 2.5530 | 9,735 |

All five anchors +1 (high risk favourable, same sign as K2/C2); train rho is
STRONGER than Kronos' (0.019..0.084) and similar to Chronos'. Coverage
9,779/10,100 majors rows; placebo join missing = 0.

## Dev results (UPPER BOUND — possibly in TimesFM pretraining)

| row | y0 | y1 | y2 | y3 | mean | WORST | DDmax |
|---|---|---|---|---|---|---|---|
| REF | 2.588 | 3.282 | 6.045 | 10.677 | 5.601 | 2.588 | 16.91 |
| T3 | 2.473 | 3.393 | 5.825 | 10.789 | 5.571 | 2.473 | 15.69 |
| K2 | 2.469 | 3.478 | 6.679 | 10.653 | 5.772 | 2.469 | 16.20 |
| T3K2 | 2.342 | 3.404 | 6.053 | 10.664 | 5.567 | 2.342 | 16.02 |

(K2 mean 5.772, WORST 2.469.) Robust pick on dev4 only (informational): T3
(all DD <= 20, no losing year, all mean >= 5; highest WORST: T3 2.473 > K2
2.469 > T3K2 2.342).

## Most-recent-year verdict (clean; scored ONCE) + 5y

| row | %/mo | DD | full-path DD | 5y geo | all win |
|---|---|---|---|---|---|
| REF | 4.648 | 12.90 | 16.82 | 5.410 | 0.6267 |
| T3 | 4.746 (+0.098) | 12.80 | 15.65 | 5.406 | 0.6273 |
| K2 | 4.801 (+0.153) | 12.10 | 16.09 | 5.577 | 0.6263 |
| T3K2 | 4.786 (+0.140) | 12.36 | 15.96 | 5.411 | 0.6268 |

T3 beats REF by +0.098 with lower DD (12.80 vs 12.90, full-path 15.65 vs
16.82), but trails K2 (+0.153); the ensemble sits between them (+0.140).
NONE reaches the 5.0 gate. The dev4 robust pick (T3) did not beat K2 in the
clean year — same lesson as v189-v197 and C2.

## Timing placebo (T3, replica ledger reused, 1000 perms)

| year | timing pct | block pct |
|---|---|---|
| 2021 | 78.82 | 75.12 |
| 2022 | 20.18 | 27.37 |
| 2023 | 100.00 | 99.90 |
| 2024 | 100.00 | 100.00 |
| 2025-09-24 clean | 98.90 | 99.30 |

T3 timing is SIGNIFICANT on the clean year (>= 95), like K2 (97.2) and C2
(99.2) — a third foundation model with different pretraining carries timing
signal. (Dev-year timing is mixed: 2021/2022 weak, 2023/2024 maxed.)

## Leakage statement

Feature timing (512 closes <= T, truncation-tested); label windows (harness
t_exit < A - 7d inherited); fit windows (shift-0 only + 7d embargo, anchor-y
fit for year y); fill timing (win_start=5 + 1m trade-through + stop-first,
engine). No statistic from any test year feeds any choice. Gate costs inside
the engine (maker 0.0002 / taker 0.00055 / longs pay 0.0001 per 8h). No
re-runs after outcomes; stage-last scored once.

## Vietnamese verdict

T3 đạt 4,75%/tháng ở năm sạch (+0,10 so với G2, timing có ý nghĩa 98,9%,
tương quan Spearman với Kronos chỉ 0,33) nhưng vẫn dưới cổng 5% và thua K2
(4,80%); ensemble T3K2 nằm giữa (4,79%).
Dev mạnh không chuyển sang năm sạch, nên không adopt tilt nào.
Kết luận: REJECT as a standalone tilt — giữ T3 làm bằng chứng độc lập thứ ba
củng cố K2 (ba foundation model khác pretraining đều có timing signal), cần
thêm bằng chứng prospective trước khi đưa vào G2.
