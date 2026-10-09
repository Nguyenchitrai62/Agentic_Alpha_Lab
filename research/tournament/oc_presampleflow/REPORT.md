# oc_presampleflow REPORT (2026-10-07; PLAN pre-registered before any outcome)

## Setup (descriptive generality test; NOT the deployed book)

Pooled HistGradientBoostingRegressor with v92 hyperparameters (max_depth=4,
lr=0.03, iter=400, min_leaf=300, l2=1.0, seed=0) and the v92 H=42 (7-day)
vol-normalised label (fwd = log(o[t+43]/o[t+1]), y = clip(fwd/(vol42*sqrt42),
-4, 4)) -- the same yardstick as oc_presamplebook's TV test -- fitted
separately per family, one pooled fit per anchor over BTC/ETH/BNB/XRP (SOL
excluded: no pre-2020 spot flow). FLOW = the 6 order-level whale-flow features
of deployed A/Aq (`v236/flow_features.py` imported UNCHANGED, `D` repointed at
the SPOT orders table, the v240 pattern). PREMIUM = the 5 Coinbase-premium
features of deployed D/Dq (`v111/v111_coinbase_premium.py` `premium()`/`add_cb`
imported UNCHANGED; market-wide, joined by t to every coin, so BNB/XRP use
BTC's premium exactly as the deployed code does). BLEND = 0.8*pred_FLOW +
0.2*pred_PREM per row (mirrors deployed `d2 = 0.8*o1 + 0.2*D` from
`scripts/forward_v205.py::research_books_d2`, confirmed before any outcome;
implicit deployed weights A/Aq/B/Bq 0.2, D/Dq 0.1). Full numbers in
`results.json`; predictions in `preds_<anchor>.csv`.

## Data (single SPOT venue throughout; venue difference disclosed)

Stitched Binance SPOT 4h per coin: presample 1m-built
(`data/raw/spot_1m_presample_20261007`, standard grid, gaps stay NaN) for
t < 2020-10-01 + `data/raw/spot_majors_20260925` SPOT 4h after (no overlap, no
seam choice; 20030/20030/19473/18397 bars BTC/ETH/BNB/XRP). Flow from the
SPOT order-level store `data/raw/aggflow_spot_20260929_orders/`
(BTC/ETH/BNB from 2017-08/11, XRP from 2018-05-04). VENUE DIFFERENCE: the
research years used PERP flow; here pre-sample AND reference both use SPOT
flow so the comparison is like-for-like on the same construction. Premium
from `data/raw/coinbase_20260925` 1h vs Binance SPOT 4h (v111 code's own
sources). Pre-sample anchors train AND test on this spot series; reference
anchors (2021-09-24..2024-09-24) train on everything before and test on spot
rows of [A, A+365d) with the same 7-day embargo (label end < A - 7d). The
most-recent year is never touched.

## Per-year skill (Spearman IC pred vs realised label, 95% block-42 bootstrap CI)

FLOW (6 order-level flow features; train IC 0.47/0.43/0.39/0.32/0.32/0.29/0.26):

| test year | n test | pooled IC [95% CI] | hit | per-coin IC (BTC/ETH/BNB/XRP) |
|---|---|---|---|---|
| 2019-03-01 (spot) | 8032 | 0.054 [-0.034, 0.135] | 0.532 | 0.088/-0.018/0.230/0.119 |
| 2019-09-24 (spot) | 8580 | -0.024 [-0.109, 0.060] | 0.512 | -0.162/0.030/0.052/0.059 |
| 2020-03-01 (spot) | 8760 | -0.015 [-0.106, 0.074] | 0.459 | -0.005/0.013/-0.047/0.060 |
| 2021-09-24 (spot) | 8760 | 0.024 [-0.055, 0.098] | 0.472 | 0.105/0.037/0.026/-0.058 |
| 2022-09-24 (spot) | 8760 | 0.010 [-0.058, 0.072] | 0.498 | 0.015/-0.067/0.035/0.075 |
| 2023-09-24 (spot) | 8760 | 0.008 [-0.048, 0.062] | 0.500 | -0.046/0.026/-0.016/0.033 |
| 2024-09-24 (spot) | 8760 | 0.004 [-0.049, 0.052] | 0.520 | -0.014/0.039/-0.038/0.015 |

PREMIUM (5 Coinbase-premium features; train IC 0.56/0.50/0.47/0.39/0.36/0.32/0.31):

| test year | n test | pooled IC [95% CI] | hit | per-coin IC (BTC/ETH/BNB/XRP) |
|---|---|---|---|---|
| 2019-03-01 (spot) | 8032 | -0.027 [-0.206, 0.151] | 0.475 | -0.062/-0.027/-0.037/0.020 |
| 2019-09-24 (spot) | 8580 | 0.062 [-0.078, 0.195] | 0.489 | 0.058/0.033/0.054/0.107 |
| 2020-03-01 (spot) | 8760 | 0.064 [-0.036, 0.166] | 0.467 | 0.080/0.035/0.112/0.034 |
| 2021-09-24 (spot) | 8760 | -0.164 [-0.293, -0.020] | 0.448 | -0.188/-0.144/-0.187/-0.135 |
| 2022-09-24 (spot) | 8760 | -0.023 [-0.143, 0.099] | 0.481 | -0.006/-0.042/-0.014/-0.022 |
| 2023-09-24 (spot) | 8760 | 0.057 [-0.050, 0.167] | 0.531 | 0.016/0.076/0.010/0.126 |
| 2024-09-24 (spot) | 8760 | -0.065 [-0.168, 0.032] | 0.481 | -0.099/-0.063/-0.066/-0.033 |

BLEND (0.8 FLOW + 0.2 PREM; train IC 0.56/0.52/0.48/0.40/0.39/0.35/0.33):

| test year | pooled IC [95% CI] | hit | diag book %/mo | diag DD % |
|---|---|---|---|---|
| 2019-03-01 | 0.040 [-0.051, 0.129] | 0.519 | 1.28 | 12.1 |
| 2019-09-24 | -0.009 [-0.085, 0.071] | 0.500 | -1.14 | 35.8 |
| 2020-03-01 | -0.007 [-0.098, 0.087] | 0.462 | -6.95 | 64.6 |
| 2021-09-24 | -0.014 [-0.097, 0.065] | 0.457 | -4.86 | 59.8 |
| 2022-09-24 | 0.017 [-0.058, 0.087] | 0.490 | -0.91 | 27.0 |
| 2023-09-24 | 0.026 [-0.052, 0.101] | 0.510 | -0.58 | 20.1 |
| 2024-09-24 | -0.014 [-0.081, 0.048] | 0.510 | 0.85 | 30.6 |

In-sample (train) IC is 0.26-0.56 every anchor x variant: the fit loop works
(positive control). Out-of-sample pooled IC is ~0 in 20 of 21 variant-years;
20 of 21 pooled CIs cross zero (the exception, PREMIUM 2021 at
-0.164 [-0.293, -0.020], is expected noise under 21 comparisons and does not
persist: 2022 -0.02, 2023 +0.06, 2024 -0.06). Per-coin nominal exclusions
(BNB flow 2019-03, BTC flow 2021, XRP prem 2023, BTC flow 2019-09 negative)
have scattered signs with no year-to-year persistence -- textbook multiple
comparisons over 84 cells. Hit rates sit at 0.45-0.53.

## Diagnostic book P&L (VECTORISED DIAGNOSTIC - not the engine, no SL/TP)

w = clip(pred/s_train, -1, 1) per coin, next-bar open-to-open, cost 0.0002 /
unit turnover, equal-weight mean (gross <= 1). FLOW %/mo:
1.14/-1.09/-7.27/-4.02/-1.75/-1.90/0.46 (DD 17-65%). PREMIUM %/mo:
-1.04/-3.81/-3.49/-5.45/2.08/5.06/-0.61 (DD 18-71%). With IC ~ 0 these rows
are drift x exposure + noise, NOT signal skill, and their 20-70% DDs show
this raw diagnostic is untradeable as-is. Do NOT read these rows as engine
or gate results.

## Key question

**NO -- neither deployed member family shows positive OOS IC in the
pre-sample years, but neither does it in the research years either: both
families are ~0 in ALL seven test years (2019-2025), exactly like the TV-only
member of oc_presamplebook. The families fit strongly in-sample (train IC
0.26-0.56) and generalise to zero out-of-sample on the 7-day pooled-HGB
yardstick. G2's book timing therefore cannot be attributed to standalone
7-day directional skill of ANY single feature family (TV, whale flow, or
Coinbase premium); it must come from elsewhere -- shorter horizons (v103
1d/3d), the long/short ensemble structure, cross-sectional features, sizing,
portfolio construction, or the engine. (Caveat: deployed A/D members are full
multi-horizon v144 ensembles, not this 7d proxy; what is zero here is each
family's 7d pooled-HGB skill, the common yardstick across all three family
studies.)**

## Post-hoc disclosures (no frozen choice changed)

- PLAN said the 2020-03-01 test year is "truncated at 2020-09-23 by label
  realisation"; the pre-registered stitch rule (spot_majors SPOT 4h for
  t >= 2020-10-01, same venue) keeps labels realisable, so the year runs the
  full 8760 rows (COVID crash included). The truncation clause was
  inoperative; coverage is reported, nothing was filled or chosen on it.
- `train_ic_blend` in `tmp/fits.json` is the Spearman IC of the fixed
  0.8/0.2 combination of the two fitted models' train predictions (no refit,
  no choice). `s_blend = 0.8*s_flow + 0.2*s_prem` per PLAN.
- Mean-weight / market-drift style benchmarks are omitted (IC ~ 0 makes them
  pure drift arithmetic; see oc_presamplebook for why they mislead).

## Leakage / execution statement

Features: flow module uses trades inside bars <= t plus causal rolling <= t
(warm-up NaN, never forward-filled); premium uses the Coinbase 1h candle
opening at T+3h (known at the 4h close) plus causal rolling (asof-backward
within 2h, gaps stay NaN); both imported UNCHANGED (only `D` repointed, the
v240 pattern; no edit to any original). Labels: opens t+1..t+43 only, causal
vol42 from closes <= t. Fits: rows with label end < anchor - 7d only
(verified cut dates in stdout). Diagnostic fills: next-bar opens only
(`r_next` within the single stitched spot series, never across venues). No
test-year statistic entered any model or parameter choice (weights 0.8/0.2
fixed from `forward_v205.py` before any outcome). Tests:
`tests/test_oc_presampleflow.py` (label math incl. clip, flow ratio/z, premium
asof/rolling incl. tolerance boundary, embargo truncation, next-bar-only
returns, turnover cost, bootstrap shape, blend arithmetic) -- 6 passed.

## Verdict (tieng Viet, ket luan chinh)

Ca hai ho signal cua book (whale-flow order-level va Coinbase premium) deu co IC ~ 0 o ca 3 nam pre-sample lan 4 nam reference tren cung yardstick HGB 7-ngay (20/21 CI cat 0, train IC 0.26-0.56) - giong het TV-only: timing cua G2 khong den tu skill huong 7-ngay doc-lap cua bat ky family don le nao.
Muon cai thien book dung tim alpha 7-ngay tu cac family nay - huong nay dong lai; phai tim o noi khac (horizon ngan 1d/3d, cau truc LS, weighing, engine), dang ky huong moi neu muon theo.
Day la ket qua am co gia tri mo rong oc_presamplebook, khong can prospective log - khong thay doi deployment.
