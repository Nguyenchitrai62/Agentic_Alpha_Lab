# oc_tiltgate — REPORT (2026-10-08; all stages complete)

Can a PARAMETER-FREE "follow last year" gate keep the vol-timing dip
tilt only in regimes where it works? Gate (frozen in PLAN.md): for
anchor A, tilt ON for [A, A+365d) iff effect(A) > 0, with effect =
sum((mult-1)*w*y10)/n over D0+B1 replica fills with bar-open T in
[A-372d, A-7d), mult from the fit that was live in that prior year.
No pretraining anywhere; dev4 FULLY CLEAN.

STATUS: DONE. Ledger extension DONE (5,301 fills, 2020-09-20..
2021-09-21, same core). Stage dev (12 sims) + stage last (12 sims,
once) complete. Reproduction gates PASS (REF == v421 G2 dev 0..3, Y4
and full-path DD 16.82 to the digit).

## Gate decisions (tmp/gate.json; effect in w*y units per fill)

| anchor | G_RV6 (fit) | effect / n | G_GARCH (fit) | effect / n |
|---|---|---|---|---|
| 2021 | OFF (no 2020 fit: 948 harness rows < 1000) | n/a / 5150 | OFF (same) | n/a / 5150 |
| 2022 | OFF (2021) | -0.000273 / 4169 | OFF (2021) | -0.000225 / 4169 |
| 2023 | OFF (2022) | -0.000184 / 4175 | OFF (2022) | -0.000152 / 4175 |
| 2024 | OFF (2023) | -0.000076 / 5389 | ON (2023) | +0.000025 / 5389 |
| 2025 | ON (2024) | +0.000069 / 3874 | OFF (2024) | -0.000004 / 3874 |

The gate says the tilt hurt in 2021-2023 windows, then flips ON/OFF on
dust-thin margins (+2.5e-05, -4.2e-06, +6.9e-05 per fill): a sign rule
on a ~zero-mean effect flips on noise. Kept as pre-registered (no
tuning); reported as a fragility, not fixed.

## Dev results (clean dev4; per-year 4-phase reset %/mo)

| row | y0 | y1 | y2 | y3 | mean | WORST | DDmax |
|---|---|---|---|---|---|---|---|
| REF | 2.588 | 3.282 | 6.045 | 10.677 | 5.601 | 2.588 | 16.91 |
| G_RV6 (all OFF) | 2.588 | 3.282 | 6.045 | 10.677 | 5.601 | 2.588 | 16.91 |
| G_GARCH (ON y3) | 2.588 | 3.282 | 6.045 | 10.724 | 5.612 | 2.588 | 16.91 |

OFF years with identical history == REF to the digit (asserted). ON
year y3 from REF-state gives 10.724 vs always-on V_GARCH 10.571
(report-only: different path state, not bit-identical).
Robust pick on dev4 only: G_GARCH (DD <= 20, no losing year, all mean
>= 5; WORST tie 2.588 three-way -> highest mean 5.612, margin +0.011
from a single ON year).

## Most-recent year (scored ONCE, labelled) + 5y

| row | Y4 %/mo | Y4 DD | 5y mean | full-path DD | Y4 all win |
|---|---|---|---|---|---|
| REF | 4.648 | 12.90 | 5.410 | 16.82 | 0.6267 |
| G_RV6 (ON y4) | 4.811 | 13.00 | 5.442 | 16.82 | 0.6268 |
| G_GARCH (OFF y4) | 4.648 | 12.90 | 5.418 | 16.82 | 0.6267 |

No losing year anywhere; full-path DD 16.82 everywhere (driven by the
2022 book leg the tilt cannot touch). The dev4 pick G_GARCH is OFF in
the scored year, so it contributes nothing there (4.648). G_RV6's ON
year reproduces V_RV6's 4.811 to the digit even from REF-state history.
NOTHING reaches the 5.0 gate (best: G_RV6 4.811 / 5y 5.442).

## Leakage statement

Feature timing (RV6/GARCH/sigma causal, truncation-tested, inherited
from oc_voltilt); gate windows end at A - 7d and use the (A-1yr) fit
whose training ends before (A-1yr) - 7d <= window start (verified in
tests/test_oc_tiltgate.py); label/fit windows (harness t_exit < anchor
- 7d, shift-0 only); fill timing (win_start=5 + 1m trade-through +
stop-first, engine). No statistic from any test year feeds any choice.
Gate costs inside the engine (maker 0.0002 / taker 0.00055 / longs pay
0.0001 per 8h).

## Vietnamese verdict

Gate "follow last year" né được các năm xấu (RV6 tắt 2021-2024, chỉ bật 2025), nhưng biên quyết định mỏng như bụi (+2,5e-05) nên
quy tắc dấu rất mong manh; dev4 pick G_GARCH hơn REF đúng +0,011 mean và tắt
ngay trong năm chấm điểm (4,648%).
Kết quả tốt nhất năm sạch vẫn là tilt bật full (G_RV6 = V_RV6 4,811%), mà vẫn
dưới cổng 5% — gate không đưa tilt nào qua cổng.
Kết luận: REJECT cả hai biến thể gated; đóng hướng này (đã hết 2-3 biến thể
cho phép), giữ gate như một baseline trung thực cho mọi tilt phức tạp sau.
