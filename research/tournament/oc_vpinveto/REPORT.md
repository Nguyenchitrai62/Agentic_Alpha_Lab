# oc_vpinveto REPORT — IDEAS5 §2 VPIN book-long veto (2026-10-08; pytest 5/5)

Rule (frozen PLAN.md): per coin, VPIN-50 over trailing 24h of 1m bars
(50 chronological equal-volume buckets on taker-flagged buy/sell notional from
`data/raw/aggflow_20260929_orders_1m`; 1m bars with open in [T-24h, T-1m];
exchange flags used as the ground truth BVC approximates — disclosed).
z = (VPIN − mu[A])/sd[A] with mu/sd over [A−372d, A−7d) per anchor (pre-anchor +
7d embargo, frozen per year); gate iff z > 2. V1: gated book longs x0.5
(after the exact v421 bear filter, before ffill). V2: V1 + dip multiplier 0 on
gated (T,sym) (skip new dip bids). CLOSED row read: `oc_i2_tapecancel`
(dSum −0.40) — post-placement tape cancel, different leg/timing, kept.

STATUS: DONE. G2 reproduced to the digit (dev + Y4 + 5.41/16.82). Stage dev
(12 sims) + stage last (8 sims: REF+V1 ONCE) complete. Determinism PASS.

## Gates (causal; rows < 2021-09-24 never gated)

Per-coin gated 4h closes per anchor-year (standard grid):

| coin | 2021 | 2022 | 2023 | 2024 | 2025(clean) |
|---|---|---|---|---|---|
| BTC | 18 | 458 | 81 | 260 | 99 |
| ETH | 14 | 197 | 85 | 134 | 156 |
| SOL | 0 | 83 | 44 | 732 | 270 |
| BNB | 0 | 194 | 105 | 326 | 174 |
| XRP | 0 | 32 | 486 | 88 | 234 |

Total ≈ 0.3% (2021) to ≈ 14% (2024) of (T,sym) bars — 10–50x the "~10-20/yr"
guess in IDEAS5 (disclosed; regime shifts in VPIN level trip the frozen
pre-anchor norms, e.g. SOL 2024: 732). Gated LONG book rows (standard grid,
full history): 2007. Decision-index gated share (dip calls): y0 0.0008,
y1 0.040, y2 ≈ 0.022, y3 0.080.

## Dev results (2021–2024; %/mo geometric reset + DD; wins pooled 4-phase)

| row | y0 R/DD | y1 R/DD | y2 R/DD | y3 R/DD | mean | WORST | DDmax | fullDD |
|---|---|---|---|---|---|---|---|---|
| REF | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 5.601 | 2.588 | 16.91 | 16.82 |
| V1 | 2.598/10.86 | 3.333/17.20 | 5.999/16.08 | 10.086/8.28 | 5.464 | 2.598 | 17.20 | 17.13 |
| V2 | 2.595/10.86 | 3.681/15.63 | 6.508/16.11 | 9.703/8.04 | 5.586 | 2.595 | 16.11 | 15.60 |

Book win (dev): REF 0.503/0.516/0.519/0.508; V1 0.505/0.486/0.517/0.518;
V2 0.505/0.490/0.532/0.521. All-win: REF .613/.658/.697/.671;
V1 .613/.650/.700/.672; V2 .613/.651/.699/.672.
V1 vs REF: mean −0.137, WORST +0.010, DDmax +0.29 (worse). V2 vs REF:
mean −0.015, WORST +0.007, DDmax −0.80 / fullDD −1.22 (DD buy, no return).

Robust pick on dev4 ONLY (DD ≤ 20, no losing, prefer mean ≥ 5, highest WORST):
V1 (2.598 > V2 2.595 > REF 2.588 — a razor-thin +0.01 tie in practice).
V2 is the DD pick but loses mean; neither beats REF on mean.

## V2 dip-leg replica gate (frozen D0+B1 ledger, read-only reuse)

Masked (skipped) ledger rows on gated bars: 744/22312 (3.33%).
dSum per year (masked − base, 4-phase means): y0 −0.0011, y1 −0.0018,
y2 +0.0335, y3 −0.1810, y4(clean, for reference) +0.0005.
dSum5y = −0.150 < +0.273 → NOT PROMISING. The dip skip dodges little and
loses in 2024; its engine DD improvement (V2 fullDD 15.60) comes with no
replica edge. Base reproduction: 7.718304 ± 0.002 PASS.

## Most-recent-year verdict (clean; scored ONCE for the dev4 pick V1 + REF)

| row | %/mo | DD | full-path DD | 5y geo | book win | all win |
|---|---|---|---|---|---|---|
| REF | 4.648 | 12.90 | 16.82 | 5.410 | 0.5365 (1096) | 0.6267 |
| V1 | 4.749 (+0.101) | 12.93 | 17.13 | 5.320 | 0.5345 (1132) | 0.6256 |
| V2 | unscored | — | — (dev full 15.60) | — | — | — |

V1 beats REF by +0.10 in the clean year but trails on 5y (−0.09) and full-path
DD (+0.31); both under the 5.0 gate. No losing year anywhere; DD ≤ 20 everywhere.
V2's clean year is unscored per protocol (only pick + REF).

## Leakage statement

Feature timing: 1m bars with open in [T−24h, T−1m] only (bar must end ≤ T);
never the gate bar's own future flow; truncation-tested in
tests/test_oc_vpinveto.py. Label windows: none (unsupervised moments only).
Fit windows: mu/sd from [A−372d, A−7d) per anchor, frozen per year, 7d embargo;
real-data norm test asserts stored mu/sd equal the embargoed window moments;
no statistic from any test year feeds any choice. Fill timing: win_start=5 +
1m trade-through + stop-first inside the engine. Gate costs inside the engine
(maker 0.0002 / taker 0.00055 / longs 0.0001 per 8h).

## Vietnamese verdict

REJECT cả V1 và V2 — dev4 không hơn REF về mean (V1 −0,14, V2 −0,02), pick V1 chỉ hơn WORST +0,01 (coi như hòa) mà DD tệ hơn (+0,3); năm sạch V1 +0,10 nhưng 5y −0,09 và DD tệ hơn.
Chân dip của V2 rớt cổng replica (dSum5y −0,15 so với +0,273) nên không có edge_BACKEND riêng; V2 chỉ mua DD (−1,2) bằng mean.
Hướng này đóng lại, không adopt; giữ V2 làm bằng chứng prospective nếu cần (DD thấp nhất 15,6).
