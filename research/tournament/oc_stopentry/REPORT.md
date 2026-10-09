# oc_stopentry — REPORT (2026-10-08)

Question (IDEAS10 #5, rank 5, prior 7%, effect ±0.1 %/mo): do breakout stop-entry
book orders (buy confirmation through the price) beat passive better-than-open limits?
PLAN.md was written BEFORE any outcome; one label-only engine-patch fix after outcomes
(see Post-hoc log) left all equity paths bit-identical (re-verified). Engine via heavy_slot
(sequential shifts, heartbeat every 600 s). pytest 5/5.

STATUS: DONE. Dev (REF/V1/V2/C_V1/C_V2 x 4 phases) + last (REF+V1) + S5 Bybit dev (REF+V1).
Both reproduction gates PASS to the digit.

## 0. Reproduction gates (PASS, to the digit — else STOP)

- Dev REF years 0..3 == `v421_result.json` G2 (R2B1D17BFG2)
  [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)].
- Last REF years 0..4 + 5y 5.410 + max yearly DD 16.91 + full-path DD 16.82 ==
  v421 G2 to the digit. The patched engine with stop_route=None is bit-identical
  to the audited engine_user.

## 1. Dev4 (anchors 2021..2024 — selection window; IDEAS10 is post-hoc so dev is labelled research data)

4-phase reset %/mo (yearly DD in brackets) [2021, 2022, 2023, 2024] | dev4 mean / WORST / DDmax_full:

| row | years R/DD | dev4 mean/W/DDmax | gap vs REF |
|---|---|---|---|
| REF | 2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27 | 5.601/2.588/16.91 | — |
| V1_STOPALL | 2.848/10.76, 3.308/17.77, 5.835/16.21, 10.936/8.37 | 5.684/2.848/17.77 | +0.083 |
| V2_STRONG | 2.588/10.86, 3.477/16.88, 6.035/16.23, 10.738/8.29 | 5.663/2.588/16.88 | +0.062 |
| C_V1 (exposure control, NOT eligible) | 2.656/11.03, 3.067/16.93, 5.997/15.83, 10.562/8.17 | 5.524/2.656/16.93 | — |
| C_V2 (exposure control, NOT eligible) | 2.588/10.86, 3.222/17.03, 6.071/15.84, 10.705/8.28 | 5.599/2.588/17.03 | — |

No losing dev year in any row. Entry mix (book fills): V1 100% stop all years;
V2 0%/31%/26%/11% stop in 2021..2024 (2021 all-passive by construction — medians NaN);
REF/C rows 0% stop. Per-year filled-gross ratios V1/REF: 1.024/0.954/0.926/0.968
(= c_y); V2/REF: 1.000/0.985/0.999/1.004.

Exposure verdict (frozen rule: V beats exposure iff mean above AND DD at or below control):
V1 vs C_V1: mean +0.160 and WORST +0.192 BUT DD 17.77 > 16.93 — beats on return, fails on DD.
V2 vs C_V2: mean +0.064, WORST tied, DD 16.88 < 17.03 — beats on both, by a whisker.
Dev4 robust pick (V1 vs V2 only): both eligible (DD <= 20, no losing year), both mean >= 5 —
highest WORST wins → **V1** (2.848 vs 2.588).

## 2. Post-release year Y4 2025-09-24..2026-09-23 (scored ONCE for REF + pick V1, labelled REF)

| row | Y4 R/DD | 5y R | full-path DD |
|---|---|---|---|
| REF | 4.648/12.90 | 5.410 | 16.82 |
| V1 | 4.654/12.26 (+0.006) | 5.477 (+0.067) | 17.69 |

Y4 book trades: REF 1096 at win 0.5365 / all-trade 0.6267; V1 1126 at 0.5444 / 0.6277.
The dev4 edge (+0.083) does not transfer: Y4 is essentially flat (+0.006) with a slightly
better DD (-0.64). All figures NET of the extra taker cost on stop entries.

## 3. S5 Bybit-price row, dev window (pick V1 + REF only; 2021 = SHORT window from 2021-11-15, labelled)

| row | years R/DD (S5) | dev4 mean | full-path DD |
|---|---|---|---|
| REF | 2.129/12.36, 2.735/18.11, 4.932/16.89, 10.377/9.22 | 4.994 | 18.09 |
| V1 | 2.396/12.35, 2.277/18.76, 5.199/17.06, 10.711/9.36 | 5.091 (+0.097) | **21.07** |

V1 keeps a small dev4 edge on Bybit prices (+0.097) but its full-path DD breaches 20
(21.07 vs REF 18.09; 2022 DD 18.76 vs 18.11). S5 book win rates move ≤ 0.02 (V1 2022 book
win 0.481 vs REF 0.507 — the worst year for both).

## 4. Leakage / causality checks (how verified)

- Feature timing: stop levels from minute-0 1m open only (known at T); |w|/medians from
  close-known post-bear book weights (shifted clocks ffill latest standard row r <= t_s).
  `test_median_truncation_causal` recomputes medians/routes from a truncated books panel —
  identical on the kept prefix; V2 routes ⊂ {stop, passive}; 2021 medians NaN (empty window).
- Label windows: no labels fit anywhere (entries mechanical, exits SL/TP/timeout).
- Fit windows: stop 5bps + THETA/band/COOL frozen ex-ante; R2 size/TP agents pre-date anchors;
  med_k from [2021-09-24, A_k-7d), >= 120 active-signal obs else NaN→passive; C_* use in-year
  realised fills (labelled diagnostic, never picked); S5 is a price-source switch, not a fit.
- Fill timing: patched trade-mode asserts win_start=5 for new orders (no fill minutes 0-4),
  strict 1m trade-THROUGH both sides (touch == no fill, unit-tested), stop-first in shared bars
  (inherited engine), stop entries taker 0.00055 / passive maker 0.0002 (gate costs inside).
  Synthetic hand-check (tmp/dbg_stop.py): rising-through-100.05 bar fills the stop at minute 10
  at 100.05 and leaves the 99.875 passive limit unfilled — side, price, minute and fee all exact.
- No test-year statistic feeds any tradable choice (dev pick uses 2021-2024 only; Y4/S5 scored
  once for REF+pick). `tests/test_oc_stopentry.py` 5/5 pass.

## 5. Post-hoc log

- 2026-10-08, after dev/last/S5 outcomes: stop_patch recorded every stop fill with
  entry_type "limit" (the is_stop flag was cleared one statement before the book_fill event;
  caught by tmp/dbg_stop.py where the fill price/minute/fee were already exact). Fixed to use
  the pre-clear local _fill_stop in the event + counter + fee lines. LABEL-ONLY: all equity
  paths re-ran bit-identical (dev V1 5.684/2.848/17.77, V2 5.663/2.588/16.88, ctrl.json,
  last and S5 eq_ends all unchanged); only stop_share diagnostics changed (were all 0.0).
  Original rows kept; no extra variant. PLAN.md post-hoc log updated identically.

## Vietnamese verdict (3 lines)

- V1 hơn REF nhẹ trên dev4 (+0.083 %/tháng, WORST +0.26) nhưng DD tệ hơn (+0.86, 17.77 so với 16.91) và năm sạch gần như không hơn (+0.006); trên giá Bybit full-path DD vượt ngưỡng 20 (21.07 so với 18.09 của REF).
- So với control khớp phơi nhiễm, V1 chỉ hơn về lợi nhuận chứ thua về DD (17.77 so với 16.93 của C_V1); hiệu ứng nằm trong biên ±0.1 đã báo trước, đúng prior thấp 7% của ý tưởng chase-breakout.
- Kết luận: REJECT — giữ nguyên limit thụ động của G2, không adopt stop-entry; đóng hướng này ở dạng hiện tại (kết quả âm sạch cũng là kết quả hợp lệ).
