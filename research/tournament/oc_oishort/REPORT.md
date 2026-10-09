# oc_oishort REPORT — IDEAS5 §6 OI-rise / price-fall short-cover gate (2026-10-08; pytest 6/6)

Rule (frozen PLAN.md): per 4h close T and coin, dOI = ln(OI<=T-5min / OI<=T-24h-5min)
(`data/raw/um_metrics_20260926`, as-of vintages, 5-min lag); R24 = ln(C4(T)/C4(T-24h))
and sg = std of 360 single-step log returns strictly before T (`hourly_ext.parquet`
closes with END <= T); z = (dOI-mu[A])/sd[A] with mu/sd over [A-372d, A-7d) per anchor
(7d embargo). gate_O1 = z > 2.0 AND R24 < -2sg; gate_O2 = z > 1.5 AND same price leg.
O1/O2: gated book SHORTS x0.5 (after exact v421 bear filter, before ffill); longs and
dip untouched. CLOSED rows read: `oc_i2_oiguard` (OI-DROP DIP skip, dSum -0.25/-0.12 —
opposite tail/leg) and IDEAS4-H6 (OI-LEVEL long throttle, never tested) — this is the
uncovered short-divergence cell, kept. No exposure-matched control (IDEAS5 §6 does not
ask; disclosed, same as `oc_vpinveto`).

STATUS: DONE. G2 reproduced to the digit (dev + Y4 + 5.41/16.82). Stage dev (12 sims) +
stage last (4 sims: REF ONCE, pick is REF) complete. Determinism PASS.

## Gates (causal; rows < 2021-09-24 never gated; OI span: BTC 2020-09-01, others 2021-12-01)

Per-coin gated 4h closes per anchor-year (standard grid; 2021 non-BTC norms have 0
samples -> never gate, disclosed; 2022 non-BTC norms partial ~1727 samples, disclosed):

| coin | 2021 | 2022 | 2023 | 2024 | 2025(clean) | dev4 O1/O2 |
|---|---|---|---|---|---|---|
| BTC | 0/1 | 6/18 | 4/14 | 4/7 | 20/45 | 14/39 |
| ETH | 0/0 | 10/19 | 0/5 | 5/11 | 5/14 | 15/35 |
| SOL | 0/0 | 29/33 | 0/0 | 9/14 | 10/28 | 38/47 |
| BNB | 0/0 | 51/63 | 7/11 | 2/5 | 2/10 | 60/79 |
| XRP | 0/0 | 2/5 | 5/5 | 1/6 | 19/32 | 8/16 |

Total dev4 (T,sym) bars: O1 135, O2 216 (~0.3-0.5% of grid — thin by construction, near
the ~10-20/yr guess). Gated SHORT book rows (standard grid): O1 132, O2 232 per shift.
Decision-index gated share (dip calls): O1 y0 0.0, y1 0.0706, y2 0.0057, y3 0.0084;
O2 y0 0.0, y1 0.0849, y2 0.0179, y3 0.0096. `metrics_ext_20260924` (redundant BTC-only
subset) unused, disclosed.

## Dev results (2021–2024; %/mo geometric reset + DD; wins pooled 4-phase)

| row | y0 R/DD | y1 R/DD | y2 R/DD | y3 R/DD | mean | WORST | DDmax | fullDD |
|---|---|---|---|---|---|---|---|---|
| REF | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 5.601 | 2.588 | 16.91 | 16.82 |
| O1 | 2.588/10.86 | 3.296/16.83 | 5.876/15.79 | 10.718/8.27 | 5.572 | 2.588 | 16.83 | 16.79 |
| O2 | 2.588/10.86 | 3.302/16.86 | 5.836/15.79 | 10.753/8.27 | 5.572 | 2.588 | 16.86 | 16.83 |

Book win (dev): REF 0.503/0.516/0.519/0.508; O1 0.503/0.512/0.519/0.508;
O2 0.503/0.509/0.518/0.510. All-win: REF .613/.658/.697/.671;
O1 .613/.657/.697/.671; O2 .613/.657/.697/.671.
O1 vs REF: mean -0.029, WORST +0.000 (tie), DDmax -0.08 (tiny DD buy, no return).
O2 vs REF: mean -0.029, WORST +0.000 (tie), DDmax -0.05. No losing year anywhere.

Robust pick on dev4 ONLY (DD <= 20, no losing, prefer mean >= 5, highest WORST):
all three tie on WORST (2.588); ties -> higher mean -> REF (5.601 > 5.572 = 5.572).
Pick = REF (the gate does not beat the baseline on any selection leg).

## Most-recent-year verdict (clean; scored ONCE for pick REF only — O1/O2 masked)

| row | %/mo | DD | full-path DD | 5y geo | book win | all win |
|---|---|---|---|---|---|---|
| REF | 4.648 | 12.90 | 16.82 | 5.410 | 0.5365 (1096) | 0.6267 |
| O1 | unscored | — | — (dev full 16.79) | — | — | — |
| O2 | unscored | — | — (dev full 16.83) | — | — | — |

REF reproduces v421 G2 Y4 (4.648/12.90) and 5y (5.410/W 2.588/full 16.82) to the digit.
O1/O2 clean years unscored per protocol (only pick + REF; pick is REF).

## Leakage statement

Feature timing: OI rows with create_time <= T-5min only; hourly closes with END <= T
only; R24/sg/dOI/z from data <= T; never the gate bar's own future flow;
truncation-tested in tests/test_oc_oishort.py. Label windows: none (unsupervised
moments only). Fit windows: mu/sd from [A-372d, A-7d) per anchor/coin, frozen per year,
7d embargo; real-data norm test asserts stored BTC anchor-0 mu/sd equal the embargoed
window moments; no statistic from any test year feeds any choice. Fill timing:
win_start=5 + 1m trade-through + stop-first inside the engine. Gate costs inside the
engine (maker 0.0002 / taker 0.00055 / longs 0.0001 per 8h, shorts 0).

## Vietnamese verdict

REJECT cả O1 và O2 — dev4 không hơn REF về mean (cả hai −0,03, WORST hòa 2,588), chỉ mua
DD tí hon (−0,08/−0,05) mà không có edge return; pick theo luật robust là chính REF.
Năm sạch chỉ chấm REF (4,648, đúng số G2), O1/O2 bị mask theo protocol vì không thắng baseline.
Hướng §6 đóng tại đây, không adopt; squeeze-tail short-cover không có timing alpha trên majors.
