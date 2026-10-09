# audit_mvrv REPORT — blind replication of the MVRV-z cycle gate M1 on G2

PLAN.md was written BEFORE any outcome (2026-10-07); no threshold/window/multiplier was
changed after outcomes. `replication.json` was saved BEFORE opening anything of
oc_lit_position / oc_mvrvrobust (blind protocol step 3). Gate costs: maker 0.0002, taker
0.00055 (stops/market exits taker), longs pay 0.0001 per 8h settlement (00/08/16 UTC),
shorts nothing; limit fills only on 1m trade-through, no fill in the first 5 min after a 4h
close (`win_start=5`); stop-first in the same 1m bar. Engine = v426 copy (multiplier on
STANDARD book rows with bear-filtered weight > 0, after the bear filter, before the
shifted-clock forward fill; pre-2021-09-24 rows never gated) on G2
(R2B1D17BFG2: rule inv, k 1.0, kd 1.7, bear True, G 2.0). 4-phase engine via heavy_slot
(tag audit_mvrv, Pool(2)).

## Baseline reproduction

PASS. Cached G2 via `reset_metric.year_reset` + `v388.mix`: 5.41 %/mo, W 2.588, max yearly
DD 16.91, full-path DD 16.82, yearly [2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27,
4.648/12.9] — to the digit. The re-ran G2 row matches the cache to the digit on all five
years, the 5y/dev4 aggregates and the full-path DD, so overlays are comparable.

## Blind replica results (4-phase reset R %/mo / yearly DD; full-path DD)

| year | G2 R/DD | M1 R/DD | CTRL_M1 R/DD |
|---|---|---|---|
| 2021-22 | 2.588 / 10.86 | 2.588 / 10.86 | 2.588 / 10.86 |
| 2022-23 | 3.282 / 16.91 | 3.367 / 16.26 | 3.264 / 17.00 |
| 2023-24 | 6.045 / 15.81 | 7.824 / 13.73 | 6.836 / 16.01 |
| 2024-25 | 10.677 / 8.27 | 11.218 / 9.99 | 10.436 / 8.46 |
| 2025-26 (labelled, byproduct) | 4.648 / 12.90 | 4.648 / 12.90 | 4.662 / 12.36 |
| dev4 mean / worst / DD | 5.601 / 2.588 / 16.91 | 6.192 / 2.588 / 16.26 | 5.735 / 2.588 / 17.00 |
| 5y mean / DD / full-path DD | 5.41 / 16.91 / 16.82 | 5.881 / 16.26 / 16.22 | 5.519 / 17.00 / 16.95 |

Gated share of book long cells (standard index) / realised mean multiplier: 2021 0.0% / 1.0
(5098 long cells, 0 gated); 2022 3.25% / 0.9837 (5319, 173); 2023 45.37% / 0.7732 (6511,
2954); 2024 6.41% / 0.9679 (6549, 420); 2025 0.0% / 1.0 (4175, 0). Control means per year:
1.0 / 0.9837 / 0.7732 / 0.9679 / 1.0. M1 beats its exposure-matched control on dev4 mean
(6.192 > 5.735) and 5y (5.881 > 5.519) with lower DD, but ties G2 on the worst dev year
(2.588 — the gate never fires in 2021), so it is NOT a strict TEMPLATE candidate (3/4).
Trade win rate is not separated by this engine (TOTAL-equity paths only; the engine does not
attribute book vs dip trades) — same limitation as both audited REPORTs, which also report
R/DD only for these rows.

## What failed / what held

- Nothing failed in the replica: every M1 and CTRL_M1 number matches oc_lit_position's
  REPORT to the digit (see COMPARISON.md, all diffs 0.00 vs R 0.10 pp / DD 0.5 pp gates).
- M1's gain concentrates in 2023 (+1.78 pp) with a DD cut there (15.81 -> 13.73) at the cost
  of higher 2024 DD (8.27 -> 9.99); 2025 gate is silent (M1 == G2 by construction).

## Leakage / causality checks (how verified)

- Feature timing: MVRV daily as-of D+1 02:00 <= T (searchsorted right-1); rolling window ends
  at D inclusive (trailing <= 365d, min 180, causal in D). `test_zm_window_end_causal` and
  `test_truncation_future_csv_rows_unchanged` recompute z after causal truncation (identical);
  `test_availability_d_plus_1_02h` checks the ±boundary (01:59 -> prior day, 02:00 -> new day).
- Label windows: none fitted (engine uses realised 1m path).
- Fit windows: no fits; thresholds (2.0) frozen in PLAN; CTRL means realised-exposure only.
- Fill timing: engine `win_start=5` + 1m trade-through + stop-first (v426 harness, G2 bit-exact).
  `test_crosscheck_lit_position_signal_identical` (post-replication only) asserts the
  independent z(T) equals oc_lit_position's H8 signal exactly (max diff 0.0, 750 gated bars).
  `tests/test_audit_mvrv.py` passes (6 tests).
- Vintage caveat (see COMPARISON.md): `btc.csv` is a single frozen vintage pulled 2026-09-24
  (manifest sha256 e64aca4f...); realised-cap revisions could shift historical MVRV after the
  fact. No timestamp leakage was found; the residual risk is vintage-only, shared by all three
  implementations, and needs archived vintages or a live paper log to quantify.

## Vietnamese verdict (3 lines)

- Tái tạo mù M1 khớp từng chữ số với cả hai báo cáo (dev4 6,192/DD 16,26, 5y 5,881/full 16,22; control 5,735/5,519; chênh lệch 0,00 so với ngưỡng R 0,10/DD 0,5) — code tín hiệu không rò rỉ thời gian (cửa D+1 02:00, cửa sổ trailing, searchsorted đúng).
- M1 vượt control về trung bình và DD nhưng hòa năm xấu nhất (gate không nổ 2021) nên không đạt strict; hiệu quả dồn vào 2023 (+1,78pp, DD 15,81→13,73) và gate im lặng năm gần nhất.
- Rủi ro còn lại duy nhất là vintage đơn (realised-cap có thể bị sửa hồi tố, không lượng hóa được bằng dữ liệu hiện có) — cần paper-log prospective với vintage trực tiếp, không tinh chỉnh thêm.
