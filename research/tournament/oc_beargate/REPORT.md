# oc_beargate — REPORT (2026-10-08; all stages complete, pytest 7/7)

Apply the dip-size tilt only when G2's OWN frozen bear filter says "not bear"
(C2_B, GARCH_B; no new parameter). Bear = exact v421 definition
(`research/parallel/rounds/parallel-20260906-r2/v421/v421_gross_cap.py:70`:
`bear = (btc < btc.rolling(1200, min_periods=600).mean())` with
`btc = _opens_std["BTCUSDT"].reindex(books154.index)` line 69; same lines in
oc_chronos/run_engine.py:126-127), evaluated at each holding-bar open T as the
latest standard-grid index r <= T (ffill, causal — the same ffill the books use).

STATUS: DONE. Stage dev (12 sims) + stage last (12 sims, ONCE) complete.
Reproduction gates PASS (REF == v421 G2 dev years 0..3 AND Y4, to the digit).
Bear share + placebo DONE.

## Bear share per year (causal ffill <= T)

| year | bars bear% (n=8760) | fills bear% (replica ledger) |
|---|---|---|
| 2021-09-24 | 72.65 (6364) | 78.47 (3273/4171) |
| 2022-09-24 | 40.73 (3568) | 35.80 (1453/4059) |
| 2023-09-24 | 21.55 (1888) | 20.98 (1123/5352) |
| 2024-09-24 | 13.93 (1220) | 8.06 (319/3958) |
| 2025-09-24 clean | 80.54 (7036) | 72.53 (3461/4772) |

The gate is mostly OFF in 2021 and in the clean year (73-81% bear), mostly ON in
2023-2024 (8-21% bear). So the clean-year verdict tests the tilt on ~27% of fills.

## Dev results (years 0..3; C2 / V_GARCH COPIED, not re-run)

| row | y0 | y1 | y2 | y3 | mean | WORST | DDmax |
|---|---|---|---|---|---|---|---|
| REF | 2.588 | 3.282 | 6.045 | 10.677 | 5.601 | 2.588 | 16.91 |
| C2 copied | 2.711 | 3.460 | 6.250 | 10.721 | 5.739 | 2.711 | 15.48 |
| V_GARCH copied | 2.398 | 3.265 | 6.447 | 10.571 | 5.622 | 2.398 | 17.17 |
| C2_B | 2.597 | 3.445 | 6.399 | 10.744 | 5.749 | 2.597 | 15.51 |
| GARCH_B | 2.589 | 3.302 | 6.337 | 10.713 | 5.687 | 2.589 | 17.18 |

Robust pick on dev4 ONLY among REF / C2_B / GARCH_B: C2_B (all DD <= 20, no
losing year, all mean >= 5; highest WORST: C2_B 2.597 > GARCH_B 2.589 > REF
2.588). DISCLOSED: the margin is 0.008-0.009 pp/mo — a razor-thin tie in
practice. Gating vs ungated on dev: C2 5.739/W2.711 -> C2_B 5.749/W2.597
(mean +0.01, WORST -0.11); V_GARCH 5.622/W2.398 -> GARCH_B 5.687/W2.589
(mean +0.07, WORST +0.19).

## Most-recent-year verdict (clean; scored ONCE for REF/C2_B/GARCH_B, labelled)

| row | %/mo | DD | full-path DD | all win |
|---|---|---|---|---|
| REF | 4.648 | 12.90 | 16.82 | 0.6267 |
| C2 copied | 4.754 (+0.106) | 12.86 | 15.42 | 0.6276 |
| V_GARCH copied | 4.932 (+0.284) | 12.32 | 17.12 | 0.6268 |
| C2_B | 4.699 (+0.051) | 12.86 | 15.45 | 0.6269 |
| GARCH_B | 4.815 (+0.167) | 12.32 | 17.15 | 0.6268 |

5y geo: REF 5.410 / C2_B 5.538 / GARCH_B 5.512 (copied C2 5.542, V_GARCH 5.484);
no losing year anywhere; full-path DD <= 20 everywhere. Gating COST clean-year
return vs ungated: C2 -0.055, GARCH -0.117. NONE reaches the 5.0 gate. The dev4
robust pick (C2_B) beats REF by +0.051 but trails both ungated tilts.

## Timing placebo (replica ledger, 1000 perms; gated mults)

| row | timing pct y0..y4 | block pct y0..y4 |
|---|---|---|
| C2_B | 55.64, 83.72, 100.0, 100.0, 64.84 | 47.95, 82.52, 100.0, 100.0, 74.83 |
| GARCH_B | 59.04, 36.56, 100.0, 100.0, 99.70 | 51.05, 53.45, 99.90, 100.0, 99.90 |
| (copied) C2 | 90.11, 88.31, 100.0, 100.0, 99.20 | 85.61, 89.01, 100.0, 100.0, 98.90 |
| (copied) V_GARCH | 12.39, 7.29, 99.90, 100.0, 100.0 | 8.39, 19.18, 100.0, 100.0, 100.0 |

Gating DESTROYS C2's clean-year timing (99.2 -> 64.8, not significant) but
GARCH_B KEEPS it (99.7/99.9, significant). Both gated variants keep the
2023-2024 signature (100.0) and nothing in 2021-2022 — the bear years the gate
was designed for show no timing either way.

## Leakage statement

Feature timing (frozen ch_q10 / risk_GARCH inherit their truncation tests);
bear timing (rolling <= r <= T + ffill <= T; truncation-tested in
tests/test_oc_beargate.py); label windows (harness t_exit < A - 7d inherited);
fit windows (frozen fits, shift-0 + 7d embargo inherited, anchor-y fit for year y;
no statistic from any test year feeds any choice); fill timing (win_start=5 +
1m trade-through + stop-first, engine). No statistic from any test year feeds any
choice. Gate costs inside the engine (maker 0.0002 / taker 0.00055 / longs pay
0.0001 per 8h).

## Vietnamese verdict

Gating theo bear filter có sẵn không đưa tilt nào qua cổng 5%: năm sạch C2_B chỉ
+0,05 (4,70%, timing mất ý nghĩa 64,8%), GARCH_B +0,17 (4,82%, giữ timing 99,7%)
nhưng đều thua bản không gate và dưới cổng.
Dev4 pick C2_B hơn REF/GARCH_B chỉ 0,008-0,009 (coi như hòa), nên không adopt.
Kết luận: REJECT cả hai tilt có gate — giữ GARCH_B làm bằng chứng prospective
(timing còn ý nghĩa ở năm sạch), C2_B loại hẳn.
