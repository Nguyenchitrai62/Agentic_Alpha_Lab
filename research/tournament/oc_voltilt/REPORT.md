# oc_voltilt — REPORT (2026-10-08; all stages complete)

Is the foundation-model dip tilt just VOLATILITY timing? Two trivial causal
vol forecasts (RV6 realised vol, GARCH(1,1)) with the IDENTICAL tilt rule
(x1.25 / x0.75 outer quintiles). No pretraining anywhere in this study, so
dev4 is FULLY CLEAN (no contamination caveat at all).

STATUS: DONE. Part A DONE (261,125 rows, 20/20 groups, rv6/g cov 1.0).
Stage dev (12 sims) + stage last (12 sims, once) complete. Reproduction gates
PASS (REF == v421 G2 dev years 0..3 AND Y4, to the digit). Placebo + overlap
DONE.

## Part A — features (DONE, FROZEN)

- `build_vol_features.py` (CPU-only, ~1 min): sigma = EXACT Chronos replica
  (rolling-360 std of diff(log open)); RV6 = std of last 6 close-to-close 4h
  log returns ending at the bar closing at T; risk_RV6 = RV6/sigma.
- GARCH(1,1) zero-mean: 25 per-(anchor, sym) MLE fits (scipy L-BFGS-B,
  stationary-by-construction) on shift-0 bars closing before A - 7d;
  alpha 0.04..0.15, beta 0.82..0.95; causal filter with anchor-of-year params,
  risk_GARCH = forecast sigma/sigma (E >= 360 burn-in).
- Causality: RV6 uses 6 closes <= T; GARCH filter uses r[E-1] and earlier
  only; sigma uses opens <= T (truncation-tested in tests/test_oc_voltilt.py).

## Part-B fits (harness rows only, shift-0, 7d embargo)

| anchor | V_RV6 dir/rho | V_GARCH dir/rho |
|---|---|---|
| 2021 | +1 / 0.0805 | +1 / 0.0929 |
| 2022 | +1 / 0.1459 | +1 / 0.1414 |
| 2023 | +1 / 0.1398 | +1 / 0.0958 |
| 2024 | +1 / 0.1250 | +1 / 0.0959 |
| 2025 | +1 / 0.1135 | +1 / 0.0911 |

All ten fits +1 (high vol favourable — SAME sign as K2/C2/T3); train rho is
as strong or stronger than the FMs (Kronos 0.019..0.084, Chronos
0.036..0.129, Toto 0.028..0.094). Coverage 9,845/10,100 majors rows.

## Dev results (FULLY CLEAN — no pretraining)

| row | y0 | y1 | y2 | y3 | mean | WORST | DDmax |
|---|---|---|---|---|---|---|---|
| REF | 2.588 | 3.282 | 6.045 | 10.677 | 5.601 | 2.588 | 16.91 |
| V_RV6 | 2.271 | 3.399 | 6.235 | 10.848 | 5.637 | 2.271 | 15.64 |
| V_GARCH | 2.398 | 3.265 | 6.447 | 10.571 | 5.622 | 2.398 | 17.17 |

Robust pick on dev4 only: REF (all DD <= 20, no losing year, all mean >= 5;
highest WORST: REF 2.588 > V_GARCH 2.398 > V_RV6 2.271). The vol tilts lift
the mean (+0.02..+0.04) but DENT the worst year (-0.19..-0.32) — same
dev-mean-vs-robustness lesson as v189-v197.

## Most-recent-year verdict (clean; scored ONCE for all three rows, labelled)

| row | %/mo | DD | full-path DD | all win |
|---|---|---|---|---|
| REF | 4.648 | 12.90 | 16.82 | 0.6267 |
| V_RV6 | 4.811 (+0.163) | 13.00 | 15.55 | 0.6268 |
| V_GARCH | 4.932 (+0.284) | 12.32 | 17.12 | 0.6268 |

5y geo mean: REF 5.410 / V_RV6 5.471 / V_GARCH 5.484, no losing year anywhere,
full-path DD <= 20 everywhere. V_GARCH beats every FM tilt on the clean year
(K2 4.801, T3 4.811, C2 4.754); V_RV6 ties T3 (+0.163). NONE reaches the 5.0
gate. The dev4 robust pick (REF) is confirmed: the vol tilts' dev-mean edge
did not come with robustness.

## Timing placebo (replica ledger reused, 1000 perms)

| row | timing pct y0..y4 | block pct y0..y4 |
|---|---|---|
| V_RV6 | 2.40, 14.49, 97.10, 100.0, 100.0 | 1.40, 16.78, 96.00, 100.0, 100.0 |
| V_GARCH | 12.39, 7.29, 99.90, 100.0, 100.0 | 8.39, 19.18, 100.0, 100.0, 100.0 |

Same signature as the FMs: significant timing on 2023-2026 INCLUDING the
clean year (100.0), nothing in 2021-2022.

## Overlap: vol risks vs FM risks (decision bars, all shifts pooled)

Pooled Spearman: RV6 vs C2 0.40 / K2 0.32 / T3 0.59; GARCH vs C2 0.44 /
K2 0.31 / T3 0.51. V_RV6 multiplier == C2 multiplier on 52-62% of rows.
Simple vol explains a LARGE share of the FM tilt (especially Toto) but not
all of it — the FMs carry extra timing content beyond RV6/GARCH.

## Leakage statement

Feature timing (RV6: 6 closes <= T; GARCH filter: r[E-1] and earlier, frozen
per-anchor params from bars closing before A - 7d; sigma: opens <= T;
truncation-tested); label windows (harness t_exit < A - 7d inherited); fit
windows (shift-0 only + 7d embargo, anchor-y fit for year y; GARCH params use
prices only, never labels/outcomes); fill timing (win_start=5 + 1m
trade-through + stop-first, engine). No statistic from any test year feeds
any choice. Gate costs inside the engine (maker 0.0002 / taker 0.00055 /
longs pay 0.0001 per 8h).

## Vietnamese verdict

Vol đơn giản tái tạo đúng chữ ký FM (cùng chiều +1, timing có ý nghĩa từ
2023, kể cả năm sạch 100%) và V_GARCH còn vượt mọi FM ở năm sạch (+0,28, đạt
4,93%) — nhưng TẤT CẢ vẫn dưới cổng 5%, và trên dev4 sạch thì tilt nào cũng
làm tệ đi worst-year nên robust pick vẫn là REF.
Kết luận: FM tilt chủ yếu là volatility timing (nhất là Toto, rho 0,59) —
không cần host model đắt tiền để lấy phần này, nhưng phần này một mình
không qua cổng nên REJECT cả hai tilt; giữ kết quả làm baseline đơn giản cho
mọi tilt phức tạp sau này.
