# oc_bybitfill REPORT — recover part of G2's Bybit-price gap with tiny venue-aware price offsets?

PLAN.md was written BEFORE any outcome; no definition changed after outcomes.
Engine via heavy_slot (`oc_bybitfill_eng`; REF_S5 repro first, then the other five
rows; each row 4 phases, resume-safe cache). CPU scoring only afterwards.

STATUS: DONE. 6 engine rows (REF/TPm3/RUNp3 x base/S5, 4 phases each = 24 phase
sims) + CPU scoring. Both reproduction gates PASS to the digit.

## 0. Reproduction gates (PASS, to the digit — else STOP)

- REF_base == `v421_result.json` R2B1D17BFG2 all 5 years + 5y 5.410 + full-path DD
  16.82 (validates the vendored `engine_patch.py` is bit-for-bit G2 at (1.0, 1.0)).
- REF_S5 == `oc_c2bybit` REF_S5 all 5 years + 5y 4.883 + full-path DD 18.09
  (validates the S5 Bybit-price harness is exactly the S5 friction).
- Venue gap anchor: base -> S5 = 0.607 pp/mo dev4 (5.601 -> 4.994), 0.527 5y
  (5.410 -> 4.883). 2021 S5 is a SHORT window from 2021-11-15 (labelled `*`).

## 1. Dev4 on Bybit prices (anchors 2021..2024 — SELECTION input, the ONLY one)

4-phase reset %/mo (yearly DD in brackets) [2021*, 2022, 2023, 2024] | dev4 mean / W / maxDD:

| row (Bybit S5) | years R/DD | dev4 / W / maxDD |
|---|---|---|
| REF_S5 | 2.129/12.36, 2.735/18.11, 4.932/16.89, 10.377/9.22 | 4.994/2.129/18.11 |
| TPm3_S5 | 2.160/12.41, 2.624/18.07, 4.884/16.89, 10.339/9.23 | 4.952/2.160/18.07 |
| RUNp3_S5 | 2.118/12.55, 2.763/16.97, 4.839/16.97, 10.399/9.28 | 4.980/2.118/18.03 |

Gaps vs REF_S5 on dev4: TPm3 -0.042, RUNp3 -0.014 (both NEGATIVE).
No losing dev year in any row; all dev DD <= 20. No variant reaches mean >= 5, and
neither variant beats REF_S5 on the mean — the robust pick is REF_S5 (no offset).
(TPm3 has the highest WORST, 2.160 vs 2.129, but at a lower mean and a worse Y4/5y;
per the frozen rule the mean comes first and Y4/5y confirm the direction.)

## 2. Post-release year Y4 2025-09-24..2026-09-23 (scored ONCE, labelled diagnostic)

| row | REF_S5 | TPm3_S5 (gap) | RUNp3_S5 (gap) |
|---|---|---|---|
| Y4 R/DD | 4.443/12.37 | 4.364/12.48 (-0.079) | 4.423/12.32 (-0.020) |

Both variants lose in the labelled year too (TPm3 -0.079, RUNp3 -0.020).

## 3. Five-year path + full-path DD (v388.mix from 2021-09-24)

| row | 5y R/W/DD/full | gap 5y vs REF |
|---|---|---|
| REF_base (Binance) | 5.410/2.588/16.91/16.82 | gap anchor 0.527 |
| REF_S5 (Bybit) | 4.883/2.129/18.11/18.09 | — |
| TPm3_S5 | 4.834/2.160/18.07/18.45 | -0.049 |
| RUNp3_S5 | 4.868/2.118/18.03/18.02 | -0.015 |

Recovery share of the Bybit gap (variant-REF)/(REF_base-REF_S5):
TPm3 dev4 -6.9% / 5y -9.3%; RUNp3 dev4 -2.3% / 5y -2.8%. Neither recovers anything;
both give back a little. All full-path DDs <= 20 (worst 18.45 TPm3_S5).

## 4. Fill / TP counts vs REF_S5 (4-phase pooled per year; rung fills, TP fills, TP rate)

| year | REF_S5 (fill/TP/rate) | TPm3_S5 delta | RUNp3_S5 delta |
|---|---|---|---|
| 2021* | 3296 / 1401 / 42.5% | +0 / +29 / +0.9pp | +51 / +44 / +0.7pp |
| 2022 | 3870 / 1978 / 51.1% | +3 / +51 / +1.3pp | +73 / +69 / +0.8pp |
| 2023 | 4362 / 2275 / 52.2% | +0 / +52 / +1.2pp | +98 / +76 / +0.6pp |
| 2024 | 3875 / 2026 / 52.3% | +0 / +37 / +1.0pp | +67 / +63 / +0.7pp |
| Y4 | 4623 / 2168 / 46.9% | +0 / +41 / +0.9pp | +118 / +90 / +0.7pp |

Mechanics work as intended (TPm3 converts timeouts to TPs at the same rung fills:
stops/timeouts fall accordingly; RUNp3 adds rung fills +51..+118/yr and TPs
+44..+90/yr), but the extra TPs do NOT pay: TPm3's 3 bps shave on EVERY TP costs
more than the converted timeouts earn (return down every window), and RUNp3's extra
shallower fills are lower quality (return flat-to-down despite more fills).
All-trade win rates move <= 0.005 (S5 Y4: REF 0.6247, TPm3 0.6265, RUNp3 0.6249).

## 5. Binance side row (labelled, NOT for selection)

| row | dev4/W/maxDD | Y4 R/DD | 5y/full |
|---|---|---|---|
| REF_base | 5.601/2.588/16.91 | 4.648/12.90 | 5.410/16.82 |
| TPm3_base | 5.566/2.593/16.55 (-0.035) | 4.627/13.03 (-0.021) | 5.377/16.52 (-0.033) |
| RUNp3_base | 5.740/2.824/16.89 (+0.139) | 4.675/12.51 (+0.027) | 5.526/16.84 (+0.116) |

TPm3 hurts on Binance too (-0.035 dev4). RUNp3 HELPS on Binance (+0.139 dev4,
+0.116 5y, driven by 2021 +0.236 and 2023 +0.216) — but this side row was
pre-registered as labelled-only and cannot select anything; on Bybit prices (the
question asked) RUNp3 is -0.014 dev4 / -0.015 5y. Noted for the leader, not a pick.

## 6. Leakage / causality checks (how verified)

- Feature timing: dip levels use O(T) + trailing sigma (minutes strictly before the
  holding bar); fills use live minutes only (book win_start=5, dip sleeve_start=16);
  the 0.9997/1.0003 mults are constants — no fit, no threshold tuned on any year.
  Truncating the data window cannot change any bar's mult (tested).
- Label windows: none fitted; engine uses the realised 1m path only.
- Fit windows: no refit; R2 size/TP tables reused frozen (shift-specific, embargoed
  upstream); S5 is a price-source switch, not a fit. No statistic from any test year
  feeds any choice.
- Fill timing: strict trade-through (`low < lv_doc`, `high > tp_doc`) preserved in
  the patch (only lv/tp scaled); win_start=5 asserted; stop-first in a shared 1m
  bar (inherited harness); no fill in the first 5 minutes after a 4h close.
- `tests/test_oc_bybitfill.py` passes (see below).

## 7. Post-hoc log

- No PLAN definition changed after outcomes. All 6 rows scored as pre-registered;
  both reproduction gates passed to the digit before any variant claim.

## Vietnamese verdict (3 lines)

- Cả hai offset đều KHÔNG thu hẹp gap Bybit mà còn làm tệ đi một chút: TPm3 −3bps
  (dev4 −0.042, 5y −0.049, năm gần nhất −0.079) dù đổi thêm +29/+52 TP mỗi năm với
  TP-rate +1pp, vì shave 3bps trên MỌI TP tốn hơn số timeout vớt được; RUNp3 rung
  nông hơn +3bps (dev4 −0.014, 5y −0.015) dù khớp thêm +51/+98 rung và +44/+76 TP mỗi
  năm, vì các fill thêm chất lượng thấp hơn — recovery share âm cả hai (−6.9%/−9.3%
  TPm3, −2.3%/−2.8% RUNp3; gap gốc dev4 0.607, 5y 0.527; DD full-path vẫn ≤20).
- Robust pick trên dev4 là REF_S5 (giữ nguyên, không offset): không variant nào vượt
  mean 4.994 của REF, và năm gần nhất (labelled, chấm một lần) cũng âm cả hai — nên
  REJECT cả TPm3 lẫn RUNp3 trên giá Bybit.
- Hàng phụ Binance (labelled, không dùng để chọn): TPm3 cũng hại (−0.035 dev4),
  còn RUNp3 lại lợi (+0.139 dev4, +0.116 5y) — ghi nhận cho leader, không phải căn cứ
  chọn vì câu hỏi là giá Bybit.
