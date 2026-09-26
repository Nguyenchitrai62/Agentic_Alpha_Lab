# v154 error analysis (descriptive diagnostics)

> DESCRIPTIVE ONLY: this analysis replays the already-seen OOS span 2021-09-24..2026-09-23 (including the former hidden year). It fits nothing and tunes nothing. Any idea it suggests needs a pre-registered test (and prospective confirmation) before any use.

## Reconstruction check
Rebuilt v154 (A+B+D)/3 through the v144 t25 governed engine: **monthly 3.515%** (ref 3.515, d=0.0000), **full-path DD 19.15%** (ref 19.15, d=0.0000). Tolerance 0.01: PASSED.
Live span 2021-09-24..2026-09-23. Additive net sum 2.2326 vs compounded 6.9499 (capital fraction; the gap is compounding).

## Totals (capital fractions, additive sums over live 4h bars)
| gross | cost | funding | carry_gross | carry_cost | carry_net | net |
|---|---|---|---|---|---|---|
| 2.5509 | 0.2338 | 0.1809 | 0.1281 | 0.0317 | 0.0964 | 2.2326 |

## 1. By asset (asset nets exclude portfolio carry; add carry_net for the total)
| asset | gross | cost | funding | net_ex_carry |
|---|---|---|---|---|
| BNBUSDT | 0.5137 | 0.0587 | 0.0475 | 0.4074 |
| BTCUSDT | 0.6641 | 0.0529 | 0.0718 | 0.5394 |
| ETHUSDT | 0.4683 | 0.0380 | 0.0283 | 0.4020 |
| SOLUSDT | 0.3981 | 0.0408 | 0.0171 | 0.3402 |
| XRPUSDT | 0.5067 | 0.0434 | 0.0162 | 0.4471 |

## 2. By member (standalone costs; netting residuals reconcile to the total)
| member | gross | cost_standalone | funding_standalone | carry_share | net_standalone |
|---|---|---|---|---|---|
| A | 0.8406 | 0.0865 | 0.0610 | 0.0321 | 0.7253 |
| B | 0.8794 | 0.0908 | 0.0633 | 0.0321 | 0.7575 |
| D | 0.8309 | 0.0826 | 0.0589 | 0.0321 | 0.7215 |
cost netting residual -0.0261; funding netting residual -0.0022.

## 3. By book inside members (gross only; execution is shared at member level)
| member | book | gross |
|---|---|---|
| A | b_lo | 0.2392 |
| A | b94 | 0.2079 |
| A | b103 | 0.3934 |
| B | b_lo | 0.2410 |
| B | b94 | 0.2275 |
| B | b103 | 0.4109 |
| D | b_lo | 0.2412 |
| D | b94 | 0.1916 |
| D | b103 | 0.3981 |

## 4. Long vs short legs (buys attach cost to long; funding+carry attach to long)
| leg | gross | cost | funding | carry_net | net |
|---|---|---|---|---|---|
| long | 2.2341 | 0.1251 | 0.1809 | 0.0964 | 2.0245 |
| short | 0.3168 | 0.1087 | 0.0000 | 0.0000 | 0.2081 |

## 5. By BTC daily ribbon state at t
| group | bars | gross | cost | funding | carry_net | net |
|---|---|---|---|---|---|---|
| bear(-1) | 2994 | 0.2239 | 0.0475 | 0.0096 | -0.0081 | 0.1586 |
| bull(+1) | 3463 | 1.1881 | 0.0690 | 0.0805 | 0.0918 | 1.1305 |
| flat(0) | 4487 | 1.1389 | 0.1173 | 0.0909 | 0.0128 | 0.9435 |

## 6. By BTC realised-vol tercile at t (cut points 0.0023, 0.0077, 0.0110, 0.0286)
| group | bars | gross | cost | funding | carry_net | net |
|---|---|---|---|---|---|---|
| high | 3648 | 0.9822 | 0.0626 | 0.0396 | 0.0392 | 0.9192 |
| low | 3648 | 0.9859 | 0.1011 | 0.0915 | 0.0196 | 0.8129 |
| mid | 3648 | 0.5828 | 0.0700 | 0.0498 | 0.0376 | 0.5006 |

## 7. By anchor year
| anchor | bars | gross | cost | funding | carry_net | net |
|---|---|---|---|---|---|---|
| 2021-09-24 | 2190 | 0.2355 | 0.0282 | 0.0197 | 0.0086 | 0.1961 |
| 2022-09-24 | 2190 | 0.4420 | 0.0371 | 0.0383 | 0.0053 | 0.3719 |
| 2023-09-24 | 2190 | 0.7233 | 0.0413 | 0.0315 | 0.0669 | 0.7173 |
| 2024-09-24 | 2190 | 0.5621 | 0.0691 | 0.0473 | 0.0181 | 0.4638 |
| 2025-09-24 | 2184 | 0.5879 | 0.0579 | 0.0441 | -0.0023 | 0.4835 |

## 8. Five largest non-overlapping drawdown episodes (peak -> trough)
| peak | trough | depth_pct | window_net | window_gross | window_cost | window_funding | window_carry_net |
|---|---|---|---|---|---|---|---|
| 2022-01-12 | 2022-04-21 | 19.15 | -0.21 | -0.19 | 0.01 | 0.01 | -0.01 |
| 2022-07-20 | 2022-11-26 | 17.96 | -0.19 | -0.17 | 0.01 | 0.01 | -0.00 |
| 2023-07-13 | 2023-10-15 | 16.40 | -0.18 | -0.16 | 0.01 | 0.01 | 0.00 |
| 2025-09-21 | 2025-09-25 | 15.20 | -0.16 | -0.16 | 0.00 | 0.00 | 0.00 |
| 2024-07-04 | 2024-07-31 | 14.71 | -0.16 | -0.16 | 0.00 | 0.00 | 0.00 |

### Episode 1: 2022-01-12 -> 2022-04-21 (depth 19.15%)
gross by asset: BNBUSDT -0.0390, BTCUSDT -0.0348, ETHUSDT -0.0696, SOLUSDT -0.0098, XRPUSDT -0.0369
gross by member: A -0.0700, B -0.0595, D -0.0606
gross by book: A/b_lo -0.0186, A/b94 -0.0182, A/b103 -0.0332, B/b_lo -0.0166, B/b94 -0.0179, B/b103 -0.0250, D/b_lo -0.0172, D/b94 -0.0174, D/b103 -0.0260
gross long -0.1873 / short -0.0028.

### Episode 2: 2022-07-20 -> 2022-11-26 (depth 17.96%)
gross by asset: BNBUSDT 0.0111, BTCUSDT -0.1112, ETHUSDT 0.0010, SOLUSDT -0.0599, XRPUSDT -0.0080
gross by member: A -0.0541, B -0.0382, D -0.0749
gross by book: A/b_lo -0.0160, A/b94 -0.0128, A/b103 -0.0252, B/b_lo -0.0140, B/b94 -0.0089, B/b103 -0.0152, D/b_lo -0.0145, D/b94 -0.0145, D/b103 -0.0459
gross long -0.1532 / short -0.0139.

### Episode 3: 2023-07-13 -> 2023-10-15 (depth 16.40%)
gross by asset: BNBUSDT -0.0103, BTCUSDT -0.0434, ETHUSDT -0.0401, SOLUSDT -0.0323, XRPUSDT -0.0293
gross by member: A -0.0618, B -0.0525, D -0.0411
gross by book: A/b_lo -0.0103, A/b94 -0.0173, A/b103 -0.0342, B/b_lo -0.0111, B/b94 -0.0157, B/b103 -0.0257, D/b_lo -0.0107, D/b94 -0.0195, D/b103 -0.0110
gross long -0.1206 / short -0.0349.

### Episode 4: 2025-09-21 -> 2025-09-25 (depth 15.20%)
gross by asset: BNBUSDT -0.0540, BTCUSDT -0.0576, ETHUSDT -0.0199, SOLUSDT -0.0264, XRPUSDT -0.0012
gross by member: A -0.0535, B -0.0497, D -0.0559
gross by book: A/b_lo -0.0141, A/b94 -0.0131, A/b103 -0.0263, B/b_lo -0.0118, B/b94 -0.0108, B/b103 -0.0271, D/b_lo -0.0157, D/b94 -0.0131, D/b103 -0.0271
gross long -0.1613 / short 0.0022.

### Episode 5: 2024-07-04 -> 2024-07-31 (depth 14.71%)
gross by asset: BNBUSDT -0.0201, BTCUSDT -0.0121, ETHUSDT -0.0331, SOLUSDT -0.0436, XRPUSDT -0.0468
gross by member: A -0.0565, B -0.0554, D -0.0437
gross by book: A/b_lo -0.0015, A/b94 -0.0183, A/b103 -0.0367, B/b_lo 0.0024, B/b94 -0.0178, B/b103 -0.0400, D/b_lo 0.0027, D/b94 -0.0152, D/b103 -0.0312
gross long 0.0038 / short -0.1595.

## 9. Daily hit rate and payoff ratio per anchor year
| anchor | days | hit_rate | payoff_ratio | mean_daily_bps |
|---|---|---|---|---|
| 2021-09-24 | 365 | 0.5342 | 1.0188 | 5.3723 |
| 2022-09-24 | 365 | 0.4740 | 1.4479 | 10.1889 |
| 2023-09-24 | 365 | 0.5260 | 1.4077 | 19.6533 |
| 2024-09-24 | 365 | 0.5205 | 1.2536 | 12.7060 |
| 2025-09-24 | 364 | 0.5192 | 1.2447 | 13.2831 |
overall: {'days': 1824, 'hit_rate': 0.5148026315789473, 'payoff_ratio': 1.2764493453092502}

## Observations (plain, descriptive; not validated findings)
1. Member gross ranking: B 0.879, A 0.841, D 0.831 (total gross 2.551); costs+funding take 0.318 off the gross path.
2. Asset gross ranking: BTCUSDT 0.664, BNBUSDT 0.514, XRPUSDT 0.507, ETHUSDT 0.468, SOLUSDT 0.398.
3. Long-leg gross 2.234 vs short-leg gross 0.317; long net 2.025 vs short net 0.208 (funding and carry attach to the long leg).
4. Anchor-year net ranking: 2023 0.717, 2025 0.484, 2024 0.464, 2022 0.372, 2021 0.196.
5. Ribbon-regime net ranking: bull(+1) 1.130, flat(0) 0.944, bear(-1) 0.159 (bars: bull(+1)=3463, flat(0)=4487, bear(-1)=2994).
6. Vol-tercile net ranking: high 0.919, low 0.813, mid 0.501.
7. Deepest drawdown episode 2022-01-12 -> 2022-04-21 (19.15%); largest gross-loss asset ETHUSDT (-0.070), member A (-0.070).
8. Daily hit rate by anchor year: 2021 0.534, 2022 0.474, 2023 0.526, 2024 0.521, 2025 0.519 (overall 0.515).
9. Member standalone costs exceed realised costs by 0.026 (netting benefit of averaging members before trading).
10. Book gross across members: b103 1.202, b_lo 0.721, b94 0.627.

Any idea above needs a pre-registered test (and prospective confirmation) before any use.
