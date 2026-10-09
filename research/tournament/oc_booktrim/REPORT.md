# oc_booktrim — REPORT (2026-10-08)

Question: is G2's book over-sized — does a uniform book trim (x0.8 / x0.6, dip
sleeve untouched) free gross-cap room for more dip fills and raise the return?
PLAN.md was written BEFORE any outcome; no definition changed after outcomes
(one tooling bug-fix in analyze_booktrim.py: the last-stage assert assumed two
variants, but pick==REF collapses it to REF-only — disclosed below; no metric
or selection definition changed). Engine via heavy_slot (sequential shifts,
heartbeat every 600 s).

STATUS: DONE. Dev stage: 3 variants x 2 frics x 4 phases = 24 phase sims. Robust
pick on dev4 Binance base = REF. Last stage: REF-only x 2 frics x 4 phases = 8
phase sims, scored ONCE (BT08/BT06 Y4 never computed). All reproduction gates
PASS to the digit.

## 0. Reproduction gates (PASS, to the digit — else STOP)

- REF_base dev years 0..3 == v421_result.json G2 [(2.588/10.86), (3.282/16.91),
  (6.045/15.81), (10.677/8.27)].
- REF_base full window: 5y 5.410 + full-path DD 16.82 == v421 G2.
- REF_S5 all 5 years + 5y + full-path DD == oc_c2bybit tmp/c2bybit_table.json
  REF_S5.
- Dev/last stage consistency for REF dev years 0..3 (both frics).

## 1. Dev4 Binance base (anchors 2021..2024 — CONTAMINATION CAVEAT: dev years formed the hypothesis via other studies' realised-scale controls; numbers are an UPPER BOUND)

4-phase reset %/mo (yearly DD in brackets) [2021, 2022, 2023, 2024] | dev4 mean / W / maxDD:

| row | years R/DD | dev4 mean / W / DD, losing |
|---|---|---|
| REF | 2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27 | 5.601 / 2.588 / 16.91, 0 |
| BT08 (book x0.8) | 2.548/10.61, 2.795/16.32, 6.162/15.34, 9.624/7.78 | 5.243 / 2.548 / 16.32, 0 |
| BT06 (book x0.6) | 2.407/10.77, 2.552/15.80, 5.654/14.83, 8.733/7.36 | 4.805 / 2.407 / 15.80, 0 |

The trim loses monotonically: BT08 -0.358 pp/mo, BT06 -0.796 pp/mo vs REF. DD
improves only modestly (-0.59 / -1.11 pp). No losing dev year in any row.
Eligible (DD <= 20, no losing year): all three; mean >= 5 %/mo: REF only.
Robust pick on dev4 base ONLY = REF.

## 2. Dev4 Bybit S5 (same dev window, SHORT 2021 window from 2021-11-15, labelled)

| row | dev4 mean / W / DD, losing |
|---|---|
| REF | 4.994 / 2.129 / 18.11, 0 |
| BT08 | 4.556 / 2.094 / 17.67, 0 |
| BT06 | 4.192 / 2.090 / 17.16, 0 |

Same monotonic loss (BT08 -0.438, BT06 -0.802). The trim is not a Bybit-specific
artefact; it loses on both price sources.

## 3. Post-release year Y4 2025-09-24..2026-09-23 (clean, scored ONCE, REF only)

| fric | REF R/DD |
|---|---|
| base (Binance) | 4.648/12.90 |
| S5 (Bybit) | 4.443/12.37 |

5y + full-path DD (v388.mix from 2021-09-24): base 5.410 / full 16.82; S5 4.883
/ full 18.09 (== v421 / oc_c2bybit REF_S5 to the digit).

## 4. Decomposition: does the dip leg actually gain fills? (pooled 4 phases; attrib sums are non-compounded fractions of bar-start equity — leg-share diagnostic, NOT the reset %/mo)

Dev4 base per year [2021, 2022, 2023, 2024]:

| row | book attrib | dip attrib | book share | dip fills | mean rung w | near-cap fills (share) | over-cap |
|---|---|---|---|---|---|---|---|
| REF | 0.058, 0.244, 0.232, 0.511 | 0.253, 0.176, 0.389, 0.748 | 0.400 | 4077, 3939, 4979, 3857 | 0.099, 0.112, 0.116, 0.146 | 117, 287, 542, 250 (7.5%) | 0 |
| BT08 | 0.051, 0.182, 0.227, 0.388 | 0.252, 0.173, 0.429, 0.747 | 0.346 | 4077, 3929, 4973, 3856 | 0.099, 0.114, 0.124, 0.146 | 114, 304, 618, 252 (8.1%) | 0 |
| BT06 | 0.036, 0.153, 0.164, 0.281 | 0.251, 0.169, 0.433, 0.748 | 0.283 | 4077, 3919, 5182, 3855 | 0.099, 0.117, 0.120, 0.147 | 118, 308, 638, 253 (8.2%) | 0 |

- Dip fills barely move: BT08 vs REF per-year delta is 0, -10, -6, -1 on base
  (total -17 of ~17k); BT06 +209 only in 2023 (+4.2%) and negative elsewhere.
  On S5 BT08 fills are FLAT or DOWN every year (2023: 4362 -> 4171).
- Mean rung weight rises slightly in 2022-2023 (less size-cutting), and
  near-cap counts rise slightly — the gross cap G=2.0 still binds (max
  concurrent 2.000 in EVERY phase for ALL variants; over-cap realised fills 0
  by construction since the engine cuts to room; skips leave no event so this
  is a lower bound on cap pressure).
- Reading: the dip rung COUNT is governed by the risk budget (0.26 x 1.7) and
  the ladder triggers, not by the gross cap; the cap only trims rung SIZE.
  The book gives up ~0.20 (BT08) / ~0.41 (BT06) of attrib-sum while the dip
  gains ~0.03 — a bad trade. Win rates are identical across variants
  (all-trade 0.61-0.70 every year; Y4 base 0.6267): the trim is sizing, not
  selection.
- S5 decomposition is the same shape (book share 0.388 -> 0.340 -> 0.282;
  fills flat/down; max concurrent 2.0 everywhere).

## 5. Leakage / causality checks (how verified)

- Feature timing: no new feature; books are the frozen v154/research_books_d2
  pipeline (decision at 4h close uses only data available then; inherited G2).
  `test_pair_rungs_consecutive_and_order_invariant` + truncation-style
  determinism check on the decomposition helpers.
- Label windows: no labels fit anywhere in this study.
- Fit windows: no fits; constants 0.8/0.6 fixed in the assignment before any
  outcome; no statistic from any test year feeds any choice (S5 is a
  price-source switch, not a fit). BT08/BT06 Y4 never computed (losing
  variants' clean year untouched).
- Fill timing: win_start=5 asserted in source + test; engine fills only on 1m
  trade-through with stop-first (inherited harness).
- Gate costs inside the engine (maker 0.0002 / taker 0.00055 / longs pay
  0.0001 per 8h).
- `tests/test_oc_booktrim.py` 7/7 pass.

## 6. Post-hoc log

- analyze_booktrim.py tooling fix AFTER dev outcomes but BEFORE scoring Y4/5y:
  the last-stage assert expected {REF, pick} two-variant caches, but pick==REF
  collapses the last stage to REF-only; fixed to accept REF-only when the
  staged pick equals REF and cross-checked against the independently computed
  dev pick. No metric, gate, or selection definition changed; all rows scored
  as pre-registered.
- Engine log eq_end values were visible during the run (progress prints) but no
  reset-metric scoring was done before the dev stage completed.

## Vietnamese verdict (3 lines)

- Trim book đồng đều làm mất lợi nhuận đơn điệu trên dev4 (BT08 -0,36, BT06 -0,80 điểm %/tháng so với REF 5,601) ở cả giá Binance lẫn Bybit, DD chỉ giảm nhẹ (-0,6/-1,1), nên pick robust trên dev4 là REF và năm sạch chỉ chấm REF một lần (4,648 base / 4,443 S5).
- Dip hầu như không thêm fills nào (BT08 chênh -17 fills trên ~17 nghìn; S5 còn giảm), vì số lượng rung do risk budget quyết định còn gross cap 2,0 vẫn chạm trần ở mọi phase cho cả ba variant — book nhường ~0,20 attrib-sum mà dip chỉ nhận lại ~0,03.
- Kết luận: REJECT — book của G2 không quá cỡ; các control exposure-matched thắng G2 ở những study khác là artefact của realised scale, không phải hiệu ứng trim tổng quát; không đưa vào G2, đóng hướng này.
