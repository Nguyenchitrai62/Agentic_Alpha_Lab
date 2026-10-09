# oc_lsratio REPORT — IDEAS5 §7 top-trader LS-ratio contrarian gate (2026-10-08; pytest 4/4)

Rule (frozen PLAN.md): per coin, Binance top-trader LONG/SHORT ACCOUNT ratio =
`count_toptrader_long_short_ratio` from `data/raw/um_metrics_20260926`
(`sum_` = positions, not used — disclosed). LS(T) = last print with create_time
<= T-5min on the 4h standard grid (causal asof; NaN never gated, never imputed).
p90/p10 per anchor over LS in [A-372d, A-7d) (>=1000 finite else gate-off that
coin-year). gate_long = LS > p90; gate_short = LS < p10 (both strict). L1: gated
book longs x0.5 (after the exact v421 bear filter, before ffill). L2: L1 + gated
book shorts x0.5 (symmetric both sides — disclosed reading of "L2 symmetric").
Dip untouched (tilt 1). No exposure-matched control (IDEAS5 §7 does not ask —
disclosed, same as oc_vpinveto §2 / oc_oishort §6). CLOSED rows read:
`oc_i2_oiguard` (OI-drop unwind skip) + IDEAS4-H6 (OI-level long throttle) are
the opposite tails/legs; this is the uncovered ratio-contrarian cell, kept.

STATUS: DONE. G2 reproduced to the digit (dev + Y4 + 5.41/16.82). Stage dev
(12 sims: REF/L1/L2 x 4 shifts) + stage last (4 sims: REF ONCE — pick is REF)
complete. Determinism PASS (stage-last dev segments equal stage-dev).

## Gates (causal; rows < 2021-09-24 never gated)

Long gates (LS > p90) per anchor-year, standard grid:

| coin | 2021 | 2022 | 2023 | 2024 | 2025(clean) |
|---|---|---|---|---|---|
| BTC | 211 | 0 | 387 | 99 | 798 |
| ETH | 0 | 0 | 1603 | 742 | 2 |
| SOL | 0 | 0 | 786 | 695 | 71 |
| BNB | 0 | 0 | 97 | 129 | 569 |
| XRP | 0 | 0 | 1160 | 0 | 134 |

Short gates (LS < p10, L2 only):

| coin | 2021 | 2022 | 2023 | 2024 | 2025(clean) |
|---|---|---|---|---|---|
| BTC | 38 | 0 | 142 | 576 | 88 |
| ETH | 0 | 0 | 0 | 108 | 614 |
| SOL | 0 | 0 | 164 | 45 | 45 |
| BNB | 0 | 0 | 59 | 1135 | 58 |
| XRP | 0 | 0 | 34 | 259 | 12 |

Norm sizes (finite 4h samples in [A-372d, A-7d)): 2021 anchor BTC 2190, non-BTC
0 -> non-BTC never gated in y0 (disclosed skip); 2022 anchor BTC 804 / ETH 353 /
SOL 353 / BNB 353 / XRP 359 (< 1000) -> ALL coins gate-off in y1 (disclosed skip;
exchange-wide count-ratio NaN gap 2022-01..2022-12, never imputed); 2023-2025
anchors 1657-2189 (full). Gated LONG book rows (standard grid, dev): 3057;
gated SHORT rows: 538. Decision-index gated share: L1 y0 0.021, y1 0.000,
y2 0.410, y3 0.249; L2 y0 0.026, y1 0.000, y2 0.454, y3 0.404 — y2/y3 gate at
25-45% of decisions (frozen pre-anchor quantiles tripped by ratio regime
shifts, e.g. ETH 2023: 1603 longs; disclosed, not selected on).

## Dev results (2021–2024; %/mo geometric reset + DD; wins pooled 4-phase)

| row | y0 R/DD | y1 R/DD | y2 R/DD | y3 R/DD | mean | WORST | DDmax | fullDD |
|---|---|---|---|---|---|---|---|---|
| REF | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 5.601 | 2.588 | 16.91 | 16.82 |
| L1 | 2.553/10.85 | 3.282/16.91 | 6.916/14.73 | 10.773/8.12 | 5.831 | 2.553 | 16.91 | 16.82 |
| L2 | 2.529/10.85 | 3.282/16.91 | 7.074/14.71 | 10.827/8.12 | 5.877 | 2.529 | 16.91 | 16.82 |

Book win (dev): REF 0.503/0.516/0.519/0.508; L1 0.491/0.515/0.511/0.506;
L2 0.489/0.515/0.515/0.508. All-win: REF .613/.658/.697/.671;
L1 .611/.658/.694/.670; L2 .610/.658/.695/.669.
L1 vs REF: mean +0.230, WORST -0.035, DDmax 0.00 / y2 DD -1.08. L2 vs REF:
mean +0.276, WORST -0.059, DDmax 0.00 / y2 DD -1.10. y1 identical (gate-off year).
No losing year anywhere; DD <= 20 everywhere.

Robust pick on dev4 ONLY (DD <= 20, no losing, prefer mean >= 5, highest WORST):
REF (2.588 > L1 2.553 > L2 2.529). Both L-variants buy mean (+0.23/+0.28) by
spending the worst year (-0.04/-0.06 with book-win erosion in y0) — the exact
trade the robust criterion (leader 2026-09-27) rejects.

## Most-recent-year verdict (clean; scored ONCE for the dev4 pick REF only)

| row | %/mo | DD | full-path DD | 5y geo | book win | all win |
|---|---|---|---|---|---|---|
| REF | 4.648 | 12.90 | 16.82 | 5.410 | 0.5365 (1096) | 0.6267 |
| L1 | unscored | — | — (dev full 16.82) | — | — | — |
| L2 | unscored | — | — (dev full 16.82) | — | — | — |

L1/L2 clean years unscored per protocol (only pick + REF). REF Y4 reproduces v421
G2 to the digit; determinism PASS.

## Leakage statement

Feature timing: LS prints with create_time <= T-5min only (contemporaneous/future
prints excluded; NaN -> gate-off, never imputed); truncation-tested in
tests/test_oc_lsratio.py. Label windows: none (unsupervised quantiles only).
Fit windows: p90/p10 from [A-372d, A-7d) per anchor, frozen per year, 7d embargo;
real-data norm test asserts stored p90/p10 equal the embargoed-window quantiles;
no statistic from any test year feeds any choice. Fill timing: win_start=5 +
1m trade-through + stop-first inside the engine. Gate costs inside the engine
(maker 0.0002 / taker 0.00055 / longs 0.0001 per 8h).

## Vietnamese verdict

REJECT cả L1 và L2 — dev4 mean có hơn REF (+0,23/+0,28) nhưng WORST-year đều thua REF (−0,04/−0,06, book-win y0 mòn dần), robust pick theo đúng tiêu chí là REF; DDmax/fullDD không cải thiện (16,91/16,82 y hệt).
Gate y2/y3 đánh 25–45% số quyết định (quantile đông cứng gặp regime-shift, ETH 2023 né 1603 long) mà không mua được DD; y1 gate-off hoàn toàn vì dữ liệu 2022 mất hàng loạt.
Hướng này đóng lại, không adopt; L-variants giữ làm bằng chứng âm tính cho top-trader-ratio gate.
