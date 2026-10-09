# oc_presamplebook REPORT (2026-10-07; PLAN pre-registered before any outcome)

## Setup (descriptive generality test; NOT the deployed book)

Pooled HistGradientBoostingRegressor with v92 hyperparameters (max_depth=4,
lr=0.03, iter=400, min_leaf=300, l2=1.0, seed=0) on the 17 TV features only
(`v231/tv_indicators.py`, imported unchanged; no flow, no premium, no asset
dummies). Label = v92 copy: 42-bar (7-day) log open-to-open forward return
from the next bar's open, divided by trailing 42-bar close-vol * sqrt(42),
clipped to [-4, 4]. One pooled fit per anchor over BTC/ETH/BNB/XRP (SOL
excluded: no pre-2020 data). Full numbers in `results.json`; predictions in
`preds_<anchor>.csv`.

## Data

Spot 4h built from `data/raw/spot_1m_presample_20261007` on the standard
00/04/08/12/16/20 UTC grid (NaN minutes ignored, gaps stay NaN; 6845/6845/
6360/5284 bars BTC/ETH/BNB/XRP to 2020-09-30). Reference: existing perp 4h
(BTC `ma_ribbon_20260924`, others `xs_universe_20260924`). Features/labels
computed separately per price source (no seam artefact; gap bars keep NaN).
Pre-sample anchors train AND test on spot only (oc_presample precedent;
2020-03-01 test truncated to 2020-03-01..2020-09-23, 4964 rows, COVID crash
included). Reference anchors train on everything before (spot+perp stitched,
7-day embargo: label end < A - 7d) and test on perp rows of [A, A+365d).

## Per-year skill (Spearman IC pred vs realised label, 95% block-42 bootstrap CI)

| test year | train rows | train IC | n test | pooled IC [95% CI] | hit | per-coin IC (BTC/ETH/BNB/XRP) |
|---|---|---|---|---|---|---|
| 2019-03-01 (spot) | 10867 | 0.457 | 8740 | -0.003 [-0.097, 0.085] | 0.511 | 0.151/-0.090/0.020/-0.120 |
| 2019-09-24 (spot) | 15819 | 0.410 | 8756 | 0.062 [-0.038, 0.148] | 0.512 | 0.128/0.036/0.061/0.013 |
| 2020-03-01 (spot, trunc.) | 19635 | 0.361 | 4964 | 0.044 [-0.116, 0.179] | 0.488 | -0.010/-0.019/-0.000/0.137 |
| 2021-09-24 (perp) | 33195 | 0.305 | 8760 | 0.016 [-0.114, 0.142] | 0.490 | -0.064/0.075/0.111/-0.065 |
| 2022-09-24 (perp) | 41955 | 0.293 | 8760 | 0.017 [-0.091, 0.119] | 0.521 | -0.065/0.033/0.069/0.011 |
| 2023-09-24 (perp) | 50715 | 0.271 | 8760 | -0.033 [-0.124, 0.067] | 0.497 | 0.016/-0.041/-0.088/-0.069 |
| 2024-09-24 (perp) | 59499 | 0.257 | 8760 | -0.029 [-0.127, 0.066] | 0.496 | -0.097/-0.004/-0.075/0.033 |

In-sample (train) IC is 0.26-0.46 every anchor: the fit loop works
(positive control). Out-of-sample IC is ~0 in ALL seven years, pre-sample
and reference alike; all seven pooled CIs cross zero; 27 of 28 per-coin CIs
cross zero (the single exception, BTC 2019-03-01 at 0.151 [0.009, 0.271],
is expected noise under 28 comparisons). Hit rates sit at 0.49-0.52.

## Diagnostic book P&L (VECTORISED DIAGNOSTIC - not the engine, no SL/TP)

w = clip(pred/s_train, -1, 1) per coin, next-bar open-to-open, cost 0.0002 /
unit turnover, equal-weight mean (gross <= 1):

| test year | %/mo | total % | DD % | end eq | mean w | market drift %/mo |
|---|---|---|---|---|---|---|
| 2019-03-01 | -1.46 | -16.2 | 25.7 | 0.84 | -0.144 | 3.24 |
| 2019-09-24 | 2.56 | 35.4 | 34.7 | 1.35 | -0.068 | 1.84 |
| 2020-03-01 | 0.30 | 2.1 | 35.3 | 1.02 | -0.030 | 2.90 |
| 2021-09-24 | 2.05 | 27.5 | 27.0 | 1.27 | 0.154 | -4.92 |
| 2022-09-24 | 0.66 | 8.3 | 17.6 | 1.08 | 0.012 | 0.95 |
| 2023-09-24 | 1.55 | 20.3 | 20.7 | 1.20 | 0.152 | 5.99 |
| 2024-09-24 | 4.25 | 64.8 | 27.3 | 1.65 | 0.296 | 7.36 |

With IC ~ 0 these P&L rows are drift x small net exposure + noise, NOT
signal skill (e.g. 2024: mean_w 0.30 x drift 7.36 %/mo explains most of the
+4.25). DDs of 18-35% also show this raw diagnostic is untradeable as-is.
Do NOT read these rows as engine or gate results.

## Key question

**YES - the pre-sample IC is of the same sign and similar size as in the
reference years: both are zero. The TV-only 7-day member has no measurable
directional skill in any of the seven test years (2019-2025), while fitting
strongly in-sample (train IC 0.26-0.46) - textbook overfit with no
generalisation. The book's G2 return therefore cannot be attributed to this
signal family; it must come from elsewhere (other members/features, sizing,
portfolio construction, engine).**

## Post-hoc disclosure

`train_ic` was added to `tmp/fits.json` after the test outcomes were seen,
as a positive-control diagnostic only; all seven `preds_*.csv` are
bit-identical before/after (sha256 verified). Mean-weight / market-drift
columns above are post-hoc descriptive benchmarks; no choice feeds on them.

## Leakage / execution statement

Features: `tv_indicators` uses bars 0..t only (docstring; POC/Ichimoku/VWAP
warm-up is NaN, never forward-filled; gap bars excluded from feature
computation and reindexed as NaN). Labels: opens t+1..t+43 only, causal
vol42 from closes <= t. Fits: rows with label end < anchor - 7d only
(verified cut dates in stdout/panel stats). Diagnostic fills: next-bar opens
only (`r_next` within one price source, never across the spot/perp seam).
No test-year statistic entered any model or parameter choice. Tests:
`tests/test_oc_presamplebook.py` (label math, clip weight, turnover cost,
bootstrap shape, train/test embargo truncation, next-bar-only returns).

## Verdict (tieng Viet, ket luan chinh)

Thanh vien TV-only du bao 7-ngay khong co skill huong nao o ca 3 nam pre-sample lan 4 nam reference (IC ~ 0, CI deu cat 0, du train IC 0.26-0.46) - cung dau, cung do lon: bang khong.
Loi nhuan G2 cua book khong den tu ho signal nay - dung quy cong book cho TV-indicators 7-ngay, muon cai thien book phai tim o noi khac (member khac, sizing, engine).
Day la ket qua am co gia tri, khong can prospective log cho huong nay - dong lai; neu muon cuu TV features thi phai dang ky huong moi (horizon/khung khac).
