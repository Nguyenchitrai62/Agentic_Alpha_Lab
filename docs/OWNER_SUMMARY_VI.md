# Tóm tắt cho chủ tài khoản (2026-10-06, một trang)

## 1. Chạy gì bây giờ — và vì sao
- Chạy BOT G2: lệnh giấy `--corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0`, plan `trade_plan_v376.json` [BOT_RUNBOOK_VI]. BOT là phần mềm đặt lệnh thay người; G2 là bản BOT đã chọn (R2B1D17BF + trần an toàn dip 2x, v421): 5,41 %/tháng, năm tệ nhất 2,588, DD năm 16,91 / toàn đường 16,82 [FINAL_REPORT_VI; DEPLOYMENT_PLAN_VI].
- Cộng thêm tay carry quý f=0,25 trên CÙNG MỘT tài khoản Bybit UTA [DEPLOYMENT_PLAN_VI]. UTA là tài khoản hợp nhất (một vốn dùng chung cho mọi lệnh); Cross margin là vốn chung chịu lỗ chung; Hedge Mode là giữ lệnh mua và bán riêng; 5x là đòn bẩy 5 lần trên cả 5 coin BTC/ETH/SOL/BNB/XRP [BOT_RUNBOOK_VI].
- Carry nghĩa là: khi hợp đồng quý kế tiếp còn chênh giá (basis — chênh giá futures so với giá hiện tại) >= 4%/năm và hợp đồng gần còn <= 7 ngày thì mua coin thật + bán khống futures quý bằng nhau, mỗi chân = 0,25 x vốn, giữ tới đáo hạn (~4 quyết định/năm) [DEPLOYMENT_PLAN_VI]. G2+carry f=0,25 trong một UTA (carry cộng thêm, spot làm tài sản ký quỹ): 5,533 %/tháng, năm tệ nhất 2,736, DD năm 16,78 [oc_carryfric]; nếu tách vốn riêng cho carry thì lợi nhuận gần như không đổi (5,413) nhưng DD toàn đường giảm còn 16,34 [oc_carrycombo].
- Vì sao: G2 giữ gần nguyên lợi nhuận (5,41 so với 5,43 không trần) mà DD thấp hơn ~1,4 điểm và phút sập -10% cả 5 coin chỉ mất 33,5% thay vì 58% vốn [QUICKSTART_VI]. Carry f=0,25 cho thêm ~+0,12 điểm %/tháng cho cả tài khoản (riêng phần vốn carry ~+0,21%/tháng) và giữ được ở mọi kịch bản ma sát [oc_carryfric], mà kiểm tra margin đạt (tiền trống thấp nhất còn 22,49%, 0 giờ bị chặn, gap -10% mất -28,85% không cháy tài khoản); f=0,50 bị chặn 1 giờ nên không dùng [DEPLOYMENT_PLAN_VI]. Vốn >= 5000 USDT, tốt nhất ~10000 [BOT_RUNBOOK_VI].

## 2. Kỳ vọng trung thực (khoảng, không phải một số) [BOT_RUNBOOK_VI; DEPLOYMENT_PLAN_VI]
- Tháng thường: trung vị ~5 %/tháng; 49 cửa sổ 12 tháng: thấp nhất 2,73 / p10 3,25 / giữa 4,89 / p90 8,88 / cao nhất 11,71 [DEPLOYMENT_PLAN_VI]. Giả lập 10.000 năm: giữa ~5,1 (thấp 1,5 / cao 10,3) %/tháng [DEPLOYMENT_PLAN_VI]. Nói gọn: 4–6 %/tháng [FINAL_REPORT_VI].
- Năm xấu: chỉ ~3 %/tháng; năm tệ nhất lịch sử BOT là 2,83 (G2 là 2,588) %/tháng [FINAL_REPORT_VI]. Chỉ ~52% năm đạt >= 5 %/tháng [DEPLOYMENT_PLAN_VI].
- Sụt vốn DD (mức giảm từ đỉnh): DD cửa sổ thấp nhất 8,3 / giữa 13,5 / p90 18,3 / cao nhất 18,7; DD giả lập giữa 14,5%, p95 22,6% [DEPLOYMENT_PLAN_VI]. Chuẩn bị chịu DD tới ~18%, vốn phải chịu được DD 25% [BOT_RUNBOOK_VI].
- Xác suất: P(DD > 20%) ~11%, P(năm lỗ) ~0,7%; 5 năm thật không năm nào lỗ, 49/49 cửa sổ không lỗ, 100% DD < 20 [DEPLOYMENT_PLAN_VI]. Tháng: 41% tháng >= +5%, 72% tháng không lỗ [DEPLOYMENT_PLAN_VI]. Tuần xấu mất 8–12% vài lần/năm, mất 1–4 tháng mới về đỉnh cũ là bình thường [QUICKSTART_VI].

## 3. Ba điều CHƯA đạt (mỗi điều hai câu)
- 8 %/tháng: điểm cao nhất trên đường đánh đổi lợi nhuận-DD cũng chỉ ~5,9 %/tháng ở DD trên 17,5 [FINAL_REPORT_VI]. Muốn DD càng thấp thì lợi nhuận càng rơi, nên 8% còn xa và không đặt làm mục tiêu hiện tại [FINAL_REPORT_VI].
- DD < 15 bền vững: bản thận trọng D13BF đạt 4,97 %/tháng với DD năm 14,98 / toàn đường 14,86 trên giấy [FINAL_REPORT_VI]. Nhưng dưới ma sát thật (phí gấp đôi 15,51; trễ 15 phút 15,08; trễ 30 phút 15,62) DD đều vượt 15, nên không triển khai [FINAL_REPORT_VI].
- MANUAL (người đặt tay, không cần bot) đạt sàn 5 %/tháng: bản tốt nhất M5_human chỉ 3,73 (dev4 3,66, recent 3,99) %/tháng, DD 17,9 / 17,8, thắng 64,8%, thiếu ~1,3 điểm [FINAL_REPORT_VI]. Cộng carry vào MANUAL bản tốt nhất cũng chỉ 3,993, vẫn dưới 5 nên MANUAL chưa dùng tiền thật [DEPLOYMENT_PLAN_VI].

## 4. Đường tới tiền thật + quy tắc dừng [DEPLOYMENT_PLAN_VI]
- Paper (chạy giả lập bằng giá thật, chưa tiền thật) từ 2026-10-05 phải đủ >= 8 tuần (sớm nhất ~2026-12-01), rồi testnet (sàn thử, bắt buộc), rồi mới live vốn nhỏ; tăng vốn sau 3 tháng live nếu vẫn đạt [DEPLOYMENT_PLAN_VI].
- Live chỉ khi đủ cả 4: (a) lợi nhuận paper ở phân vị >= 20; (b) DD paper <= 15%; (c) lệch bot so với kế hoạch <= 1,5 điểm %/tháng (đủ 14 ngày mới kết luận); (d) không lỗi cycle_error > 1 giờ, không vị thế thiếu stop [DEPLOYMENT_PLAN_VI].
- Dừng: DD tài khoản > 20% thì dừng mở mới chỉ giữ SL/TP; lỗ một tháng > 10% thì halve (giảm nửa) vốn tháng sau; phân vị lợi nhuận < 5 sau >= 8 tuần thì dừng [DEPLOYMENT_PLAN_VI].
- Hôm nay 2026-10-06 mọi bot/paper mới ~0,2–1,1 ngày, kết luận đúng là "quá sớm", chưa đủ 14/56 ngày, tất cả còn trong biên [PROSPECTIVE_20261006].

## 5. Mỗi ngày xem 5 thứ + 1 lệnh cứu sau reboot [BOT_RUNBOOK_VI]
- 1) Backend sống và plan tươi < 4h30m; 2) vòng bot sống (vài chục giây); 3) không vị thế thiếu stop (unprotected) và sổ khớp sàn (qty_mismatch); 4) không cycle_error > 1 giờ; 5) equity/DD/fills và điểm prospective [BOT_RUNBOOK_VI]. Lệnh chạy: `daily_status.py` rồi `bot_health.py`, `paper_report.py`, `prospective_scorecard.py` [BOT_RUNBOOK_VI].
- Sau reboot/mất điện chỉ cần MỘT lệnh: `bash scripts/restart_all.sh` (xem trước bằng `--dry-run`; backend local rồi 5 bot paper rồi vòng carry) [BOT_RUNBOOK_VI].
