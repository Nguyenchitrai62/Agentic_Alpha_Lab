# RESEARCH MAP DRAFT ADDENDUM 2026-10-06b (doc-sync, leader merge)

Phạm vi: mọi REPORT.md dưới research/tournament/ + research/diagnostics/ có mtime 2026-10-06 (61 file,
liệt kê đủ dưới đây kèm verdict lines), cộng audit oc_bookmodel_audit (AUDIT/COMPARISON, không phải REPORT).
Mọi số y nguyên báo cáo. Cả 5 năm walk-forward đều là research data; phát hiện cần paper triển vọng.
FINAL_REPORT_VI.md §5/§6 đã cập nhật các hướng đóng sau 482129e (btclead, rungcap, bookcorr, coinbear,
longcap, cadence, manualtsmom) + chẩn đoán (ddanat_g2, grindsignal); file này là danh mục đầy đủ để leader
merge vào map.

## A. Đề xuất merge vào map (đóng/mở sau 482129e)

- ĐÓNG dip-ladder: oc_btclead NOT PROMISING (sum 0/5: FULL 10.33 vs BASE 15.14; DD 1/5; fills 4998 vs 5498) —
  giữ B1 size-only. oc_rungcap NOT PROMISING (giữ ≥97% tổng 0/5, tốt nhất 91% 2023, raw FULL 7.45 vs 9.67;
  DD 3/5; rung bị cắt win 72-83%) — cụm crash-bar không phải chỗ cắt.
- ĐÓNG book: oc_bookcorr NOT PROMISING (DD 5/5 nhưng retention ≥90% chỉ 1/5: 0.73/0.88/0.92/0.83/0.74) —
  ý tưởng #43. oc_coinbear NOT PROMISING (DD 3/5, P&L≥95% 3/5; grind −0.0504→−0.0506) — ý tưởng #44, không
  đăng ký engine. oc_longcap NOT PROMISING (retention 0/5: 0.848-0.948; DD 1/5 strict; grind −0.0499→−0.0511) —
  ý tưởng #46. oc_cadence NOT PROMISING (8h: P&L 2/5, DD 1/5; 12h: 2/5, 3/5) — ý tưởng #47, đóng hướng cadence.
- ĐÓNG MANUAL: oc_manualtsmom — overlay TSMOM-30d 0.25x lên 3.90/DD 19.33 (excess +5/5, DD tệ hơn 5/5),
  không hàng nào chạm base MANUAL — add-on tương quan.
- MỞ (lead duy nhất): oc_bookcoinbrake PROMISING 4/5 DD + 4/5 P&L (rớt DD 24-25, rớt P&L 25-26: 0.389 vs
  0.95×0.4136=0.3929; cắt ~30% book loss grind −0.0504→−0.0354) — ý tưởng #45, ứng viên đăng ký engine + paper.
- Chẩn đoán: oc_ddanat_g2 — gate 16.91 = grind 2023-04-17→06-15 (~59d/354 bar; long −9..−11 + dip −7..−10/phase,
  BNB-led, short bù +6.8 gộp); <15 cần cắt ~11% thiệt hại cửa sổ; cascade 2024-01-03 (15.81) đã −2.5pp nhờ
  trần G=2.0. oc_grindsignal — giả thuyết breadth=1.0 (E0/E2/E3 max, E1 0.8), gate sau điều kiện trên
  over-extension.
- FIX XONG: bot_capfix — FIXED + ~không tốn (C_on 3.20%/261 vs A 3.58%/271; trần cũ 1.12%/209) — chờ merge
  bot/mirror.py + chạy lại paper có trần. oc_bookmodel_audit — FAIL F1 (rank42 làm feature, common_impl.py:
  251-256; W1 c2:141-147; N1 c1:147-148) → fix dispatched [OPENCODE_W_oc_bookmodel_fix.md] → re-audit → Kaggle.
- XONG: oc_margin — cross/5x tối thiểu (3x kẹt 22 phút-mix), G2 max ~3.4x, phút tệ nhất cần −29% mới cháy,
  gap −10%/−20% 0/65.1k phút cháy → runbook cross + 5x, không Isolated.
- Paper bots trên đĩa: paper, paper_d13bf, paper_d17bf, paper_d17bfg2, paper_g2k20 (5 thư mục; assignment ghi
  6 — leader xác nhận roster bot thứ 6). v425 pre-registered (trần hàng conservative) [d79630d].

## B. Danh mục đủ 61 REPORT 2026-10-06 + verdict (nhóm theo FINAL VI)

Đã vào FINAL VI §1-4/Bổ sung (không nhắc lại số): oc_frontier (REPORTING, 80 hàng v399-v423; D17BF
5.425/18.33/16.90 nằm TRONG cả hai biên; v423 audit PASS), oc_kpi_g2 (G2: 5.41/DD 16.91/16.82, win all 65.3%,
gross tệ nhất 3.0x vs 6.4x), oc_tsmom_official (D13BF 4.97/năm 14.98/toàn đường 14.86; +TSMOM-0.10 lên 5.03
nhưng DD 15.42 — không tổ hợp nào đồng thời ≥5% và DD<15), oc_rolling17 (49 cửa sổ: min 2.73/p10 3.25/
trung vị 4.89/p90 8.88/max 11.71; 49% ≥5%, 100% DD<20), oc_stresshist (tuần tệ nhất 2023-12-27..2024-01-03
−12.3%/DD 13.9%/hồi ~54d), oc_gapstress (−10% phút tệ nhất không trần −58% vốn → trần 2x còn 33.5%),
oc_contrib (shallow dips + TPs + book longs earn the return), oc_venuegap (XRP rungs gánh gap dip-ladder
nhưng chỉ ~4% rung P&L — S5 drag nằm ở BOOK), oc_bookvenue (drag KHÔNG nằm ở book execution),
oc_signedfunding (funding thực +0.12-0.15pp/tháng vs gate — gate bảo thủ hơn), oc_regimeexp (2026-09:
trên MA200, vol thấp, trend 90d +35%; nhóm lịch sử 21 tháng TB +8.1%/trung vị +5.0%), oc_wfselect
(NOT PROMISING — giữ cố định D17BF+G2: 6.03 vs 6.08), oc_manualcap (M5_human 3.73/17.8, G15 3.01/14.9,
G10 2.62/13.5 — Direction CLOSED cap thuần túy), oc_collectors (KHỎE từ restart 2026-10-05 17:40 UTC:
9.06h, 0 gap>60s, 326.813 topbook rows, 802 liqs).
Đã vào FINAL VI §5 từ trước (screens/OpenCode): oc_b1soft NOT PROMISING (SOFT>2/5 chỉ 1/5 — giữ B1 F=2.5),
oc_adaptsig NOT PROMISING (DD 4/5 nhưng efficiency 3/5 — giữ sigma360), oc_bullbook NOT PROMISING (P&L 5/5
nhưng DD episode nằm ngoài stretch boost), oc_deeptp NOT PROMISING (1/5 cả hai chân — giữ TP 1.0),
oc_rungspace NOT PROMISING (sum không thấp hơn chỉ 1/5 dù DD 5/5 — giữ spacing R2), oc_bookexit
NOT PROMISING (+1.0 ATR bank), oc_phaserebal NOT PROMISING (rebalance tháng/tuần đều −0.15/−0.18pp 5y),
oc_bookoffset PROMISING 5/5 nhưng là vol-scaled offset (trade-mode entries đã sigma-scaled — xem commit
bookoffset closed), oc_bookcoinwf PROMISING 5/5 nhưng VACUOUS (gate không loại coin nào — closed),
oc_postflush NOT PROMISING (mean âm 3/5, events 2-10/năm < floor 10), oc_lowvolrung NOT PROMISING
(sum 3/5, DD tệ hơn 5/5), oc_dipbe NOT PROMISING (giữ ≥97% tổng 0/5, DD 3/5 — giữ exit D0),
oc_condhold NOT PROMISING (sum 3/5, DD 1/5 — timeout vẫn exit ở open tiếp theo), oc_holdext NOT PROMISING
(1/5 cả hai — timeout giữ nguyên), oc_bybittp (TP lệch gần như toàn thành timeout 84%),
oc_diptilt NOT PROMISING (return 4/5 nhưng DD chỉ 1/5 — tilt bull 1.2x scale cả climb lẫn dip),
oc_tsmom NOT PROMISING (overlay 0.25x return +5/5 nhưng gate rớt), oc_tsmomcombo (combo D13BF+0.10 chạm
stretch trên lưới daily — check official đã rớt), oc_tsmomvar NOT PROMISING (DIV 0/5 cả hai variant —
đóng, không sleeve), oc_xsrev NOT PROMISING (thua 5/5: net −2.5..−5.4%/tháng, DD tệ hơn 5/5 — đóng),
oc_earlystart PROMISING 4/5 + 4/5 NHƯNG fragile (3/4 năm thắng ~0, 2023 −0.68/DD gấp đôi, full-path về BASE —
cần paper trước mọi engine), oc_manualshallow (NO row passes base MANUAL — best 3.73),
oc_regimetrue (diagnostic: TRUE pairs mọi depth đều thắng), oc_depthregime (deep rungs thua MỌI regime),
oc_deepcheck (xác nhận oc_depthregime), oc_recent (năm gần nhất margin thấp, tập trung hơn),
oc_ladderfill (diagnostic fills, không rule), oc_liqlive PATCHY-nhưng-loadable, oc_topbook
PATCHY-nhưng-loadable.
Ops/thực thi 2026-10-06: bot_parity (bot khớp engine rules — Verdict YES), bot_bookgap (exits-per-piece
~1.0 sau fix; chỉ còn test cũ pin hành vi OLD rớt), bot_parity_adopt (adopt_fresh Verdict NO — +1 fill,
vẫn −64 vs engine, return không đổi; arm C cũ +1.12% vs +3.58% → bot_capfix đã sửa), ops_liveparity
(placement parity PASS so far; win n/a — 0 closed), ops_enginespeed (đo tốc độ engine — xem REPORT),
bot_capfix (FIXED, xem mục A).
Mới trong draft này (FINAL VI §5/§6 đã cập nhật): oc_btclead, oc_ddanat_g2, oc_rungcap, oc_manualtsmom,
oc_bookcorr, oc_coinbear, oc_bookcoinbrake (PROMISING — mở), oc_longcap, oc_grindsignal, oc_margin (XONG),
oc_cadence, oc_bookmodel_impl (implementation-only, smokes C1 25.1s/C2 18.7s, 8 tests pass — chờ fix audit).
Audit kèm theo (không phải REPORT): oc_bookmodel_audit/AUDIT.md (F1 blocker + W1/W2/N1, 9 tests) +
COMPARISON.md (bookmodel: FAIL — chưa upload Kaggle).
