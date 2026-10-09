# oc_fundhold REPORT — IDEAS6 §5 funding-aware hold extension (2026-10-08; pytest 6/6)

Rule (frozen PLAN.md): at a BASE dip timeout (D0 rung with no TP/stop/backstop by
the next 4h open), if LONG and last SETTLED funding (calc_time strictly before the
timeout open T+240) > trailing-90d quantile -> exit on time (base); else extend the
resting TP/stop +8h (minutes 240..719, same frozen sl/bl/tp, taker fallback, max
one, timeout at o4 = open T+720 taker). V1 quantile = p70, V2 = p50, per
anchor-coin over settlements in [A-97d, A-7d) (7d embargo, >= 50 else never extend,
never imputed). "F1 long" read as "If long" (replica fills are dip longs only;
book SHORT always-extend is out of replica scope — disclosed, no book effect
claimed). Signals frozen. CLOSED rows read: `oc_holdext` (unconditional +4h: sum
1/5 + DD 1/5) and `oc_condhold` (profit-only +4h: 3/5 + 1/5) — both hold WHEN
unconditionally/on-profit; `oc_fundclock` (flatten on p90 PREDICTED: W2 dev4 +0.56
but clean year -0.16, gate FAIL) — flatten into the clock. This EXTENDS when cheap
on SETTLED sign. Kept per IDEAS6.

STATUS: DONE. G2 reproduced to the digit (dev + Y4 + 5.41/16.82, asserted in
`check_g2.py`). Replica gate (5,496 paired fills, base Y0-Y3 sums match holdext BASE
to 4 decimals: 2.3881/0.1829/3.8098/2.5793; Y4 0.7256 vs 0.7115 from the stricter
+720 paired-keep at the data end — disclosed) complete. NO engine run: neither
variant passes the binding replica + placebo gate (clean gate failure, valid per
IDEAS6). G2 engine numbers below are COPIED labelled context (check_g2 asserted).

## Thresholds (causal; all pools n=270, no skip; settled `last_funding_rate`)

q70/q50 per anchor (BTC/ETH/SOL/BNB/XRP): 2021 (+10/+10/+10.6/0/+10 bps both legs,
bull-regime funding) then 2022-2025 mostly lower (BTC q70 7.9-10 bps, q50 3.6-6.9;
BNB q70 0-0.4 bps, q50 -1.5-0 bps) — frozen trailing quantiles drift with regime
(same non-stationarity as `oc_fundclock`/`oc_bookfunding`). Extension share of base
timeouts (2,251 total): V1 95%/61%/58%/58%/96% per year; V2 95%/25%/22%/42%/82%.
Funding feed ends 2026-08-31 -> timeouts after that exit on time (gate off).

## Replica results (single-phase w*y sums; DD of the daily-sum path; rung wins)

| arm | y0 sum/DD/win | y1 sum/DD/win | y2 sum/DD/win | y3 sum/DD/win | y4 sum/DD/win (gate input, research data) |
|---|---|---|---|---|---|
| BASE | 2.3881/0.44/0.688 | 0.1829/1.14/0.695 | 3.8098/0.27/0.773 | 2.5793/0.22/0.699 | 0.7256/0.66/0.657 |
| V1 (p70) | 2.1212/0.74/0.756 | -0.3614/1.64/0.727 | 3.4968/0.34/0.801 | 2.8424/0.37/0.778 | 0.8984/1.03/0.791 |
| V2 (p50) | 2.1212/0.74/0.756 | 0.2021/1.17/0.716 | 3.7010/0.27/0.785 | 2.5161/0.39/0.750 | 0.7641/1.06/0.772 |

dSum vs BASE per year (V1): -0.267/-0.544/-0.313/+0.263/+0.173, dSum5y = -0.688
(gate +0.273). (V2): -0.267/+0.019/-0.109/-0.063/+0.038, dSum5y = -0.381.
PASS_sum (strictly higher, V1/V2): 2/5, 2/5. PASS_dd (not worse): 0/5, 1/5
(V2 2023 0.2673 vs 0.2718 the only DD win). LOO sign-higher: 0/5, 0/5.
PROMISING (4/5 + 4/5 + dSum5y>=+0.273): V1 NO, V2 NO.
Timeout share BASE 41.0% pooled (0.45/0.40/0.33/0.43/0.47); residual V1
0.19/0.24/0.21/0.28/0.18, V2 0.19/0.32/0.29/0.33/0.22 — extension converts timeouts
to TPs (win +6-13 pp) but at worse prices + extra funding.

Fee / funding split (aggregate w*cost; frozen legs: fill maker 0.0002, TP 2*maker,
stop/backstop/time maker+taker; longs 0.0001/settlement): fees BASE
0.345/0.395/0.467/0.360/0.387 per year; V1 0.297/0.364/0.438/0.331/0.336; V2
0.297/0.379/0.457/0.341/0.346 (fewer timeout-taker exits). Funding BASE
0.0125/0.0117/0.0165/0.0155/0.0197; V1 0.0242/0.0193/0.0252/0.0228/0.0346; V2
0.0242/0.0140/0.0201/0.0210/0.0323 — conditional extension PAYS 1.2-2x the base
funding (holds through 1-2 extra settlements) while saving nothing on the
expensive timeouts it skips (they were already the minority leg).

Dev4 robust pick (DD <= 20, no losing dev year, prefer mean >= 5, highest WORST):
NOT APPLICABLE — no variant passes the binding replica gate, so no 4-phase engine
run and no %/mo pick (pick = "none-eligible"; Y4 shown only as gate input,
labelled research data). G2 reference (COPIED, check_g2 asserted): dev
[(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)], Y4 (4.648/12.90), 5y
5.410, full-path DD 16.82. Replica 5y sums: BASE 9.6857, V1 8.9975, V2 9.3047.

## Leakage statement

Feature timing: settled funding with calc_time strictly before the timeout open
only (same-minute settlements excluded; truncation-tested in
tests/test_oc_fundhold.py); sigma/bar opens from closes <= bar open; fills on
strict 1m trade-through from minute 16 (> 5-min ban). Label windows: none
(unsupervised quantiles only). Fit windows: q70/q50 from [A-97d,A-7d) per
anchor-coin, frozen per year, 7d embargo; no statistic from any test year feeds any
choice. Fill timing: live 16..238 + stop-first in shared 1m bar (tested); extended
legs reuse resting TP/stop (no new orders). Gate costs inside replica outcomes
(maker 0.0002 / taker 0.00055 / longs 0.0001 per 8h). Taker-fallback timeout
assumption is conservative vs maker-first (Idea 1).

## Caveats / post-hoc log

1. No post-hoc change to definitions, thresholds, variants, or the decision rule.
   PLAN.md frozen before any outcome; original rows kept (no extra rows).
2. Single-phase replica (holdext-exact) disclosed vs 4-phase-mean placebo units:
   the +0.273 gate is applied in the same w*y units (conservative absolute bar;
   both variants fail by 0.65-0.96, not a boundary call).
3. Engine files (`run_engine.py` etc.) were NOT created: PLAN.md allows creating
   them only for gate-passing variants; none passed, so nothing was run.
4. All five years were available when scored; findings need prospective validation.

## Vietnamese verdict

REJECT adopt — cả V1 (p70) lẫn V2 (p50) đều rớt cổng replica sạch (sum 2/5, DD 0-1/5,
dSum5y −0,69/−0,38 so với +0,273, LOO 0/5): giữ timeout rẻ thêm 8h đổi timeout lấy TP
muộn nhưng giá tệ hơn + funding gấp ~2 lần, DD nặng hơn mọi năm.
Không có engine run theo đúng luật dip-side; giữ hướng này ĐÓNG, không triển vọng gì thêm.
