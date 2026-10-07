# oc_idea2_dipstop REPORT — fixed per-coin dip stops in the 4-phase engine (IDEAS 2026-10-07 §2)

## 0. PRE-REGISTRATION (written BEFORE any run; only these 2 variants, no others)

- Base: G2 = R2B1D17BFG2 (v421 cache): inv rule, k=1.0, kd=1.7, bear-book filter,
  gross cap G=2.0, v321 engine (close5 stops, 8sg backstop, m_sleeve_sl=4.0,
  budget 0.26, rungs 2.5/3/3.5/4/5sg, TP = G2 agent lookup untouched), gate costs
  (maker 0.02%, taker 0.055%, longs pay 0.01%/8h), win_start=5.
- P1: G2 + XRP 5.5sg / rest 4.0sg (engine hook sleeve_sl_coin; risk budget counts
  the per-coin distance; backstop 8sg unchanged; TP unchanged).
- P2: G2 + XRP 5.5sg / rest 4.5sg (same hook; m_sleeve_sl=4.5 documents the rest leg).
- S4 row: the dev-selected winner re-run with stop_slip=0.5 (robustness only).
- Selection ONLY on dev years 2021-2024 (anchors 2021-09-24..2024-09-24): robust
  criterion — among variants with DD<=20 and no losing dev year, prefer dev4 mean
  >=5, then the highest dev4 WORST year; ties -> higher mean. Most recent year
  (2025-09-24..2026-09-23) scored once, for the chosen variant only, POST-HOC.
- Baseline gate: reproduce G2 (5.410/W 2.588/DD 16.91/full 16.82) and G2+carry
  (5.634/W 2.778/DD 16.75/full 16.66, oc_carrycompound) from cache exactly first,
  else stop and report.
- Metric: 4-phase reset_metric.year_reset + full-path DD exactly like v421/v422.
- POST-HOC label: the per-coin choice (XRP 5.5) comes from the oc_idea2 screen that
  already saw all five years; this engine test is POST-HOC INFORMED, folds must
  transfer or the direction closes.

## 1. Baseline reproduction (from cache, no rerun)

`run_dipstop.py --check` asserts and passes:
- G2 (v421 R2B1D17BFG2 recomputed via reset_metric + v388.mix): R=5.410,
  W=2.588, DD=16.91, full-path DD=16.82 — matches v421_result.json to the digit.
- G2+carry f=0.25 (oc_carrycompound results.json): R=5.634, W=2.778, DD=16.75,
  full=16.66 — matches exactly.
Gate costs in the engine: maker 0.0002 / taker 0.00055 / longs pay 0.0001 per 8h
settlement (engine_user defaults, v321 close5/backstop-8 G2 harness).

## 2. Engine results (4-phase, reset_metric + full-path DD like v421/v422)

`run_dipstop.py --run` (serial, resumable, tmp/ cache): P1/P2 on all 4 shifts,
v421 worker verbatim (v321 + R2 agents, bear filter, G=2.0 cap, win_start=5);
REF = v421 cache bit-exact. `run_dipstop.py --slip`: S4 stop_slip=0.5 for the
dev winner only. `run_dipstop.py --report`: select on dev4, 2025 once for winner.

Dev years 2021-2024 only (R %/mo / DD % per anchor year; 5y columns POST-HOC):

| row | 2021 | 2022 | 2023 | 2024 | dev4 R/W/DD/losing | 2025 POST-HOC | full DD |
|---|---|---|---|---|---|---|---|
| G2 (REF) | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 5.601/2.588/16.91/0 | 4.648/12.90 | 16.82 |
| G2_P1 | 2.607/10.47 | 3.281/16.91 | 6.049/15.88 | 10.724/8.29 | 5.618/2.607/16.91/0 | — (not scored) | — |
| G2_P2 | 2.613/11.11 | 3.378/16.81 | 5.873/15.86 | 10.750/8.29 | 5.606/2.613/16.81/0 | 4.731/13.08 | 16.80 |

Winner on dev4 (robust criterion: DD<=20, no losing year, R>=5 both, highest
WORST year 2.613 vs 2.607): G2_P2. Edge over G2 is negligible (+0.005pp/mo
dev4; P1 +0.017pp), DD -0.10pp. Folds k=2/3/4 all pick P2 but transfer 0/3
(2023 R loss; 2024/2025 R wins with worse DD). 2025 POST-HOC: +0.083pp R,
+0.18pp DD vs G2. S4 slip dev4 (winner): 5.094/2.369/17.16/0 — the tiny edge
reverses under slip stress (-0.51pp vs base P2; still DD<=20, no losing year).

## 3. Verdict

REJECT: fixed per-coin stops do not survive the engine — dev gain is ~zero
(+0.005pp/mo), folds transfer 0/3, slip stress erases it. Close this direction.

Nhan dinh 3 dong: khong dat — P2 thang P1 sat nut nho worst-year dev4 nhung
chi +0,005 diem %/thang so voi G2, folds 0/3 va slip stress xoa sach loi the.
Tu choi phuong an stop co dinh theo coin; dong huong, khong can paper them.
