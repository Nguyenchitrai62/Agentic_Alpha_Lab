# Hỏi đáp nhanh cho chủ tài khoản (2026-10-06)

> Trả lời ngắn. Số nào cũng kèm nguồn. Đọc thêm ở mục ghi sau mỗi câu.

## 1. Cần tối thiểu bao nhiêu vốn?
Tối thiểu 5000 USDT, tốt nhất ~10000 USDT [QUICKSTART_VI §1; BOT_RUNBOOK_VI §1]. Dưới 5000 nhiều bậc dip BTC bị bỏ (`skipped_below_minimum`) [BOT_RUNBOOK_VI §1]. Đọc: `QUICKSTART_VI §1`, `BOT_RUNBOOK_VI §1`.

## 2. Đang chạy bản gì, kỳ vọng bao nhiêu?
BOT G2 + carry f=0,25 chung một Bybit UTA [OWNER_SUMMARY_VI §1]. G2 backtest 5,41 %/tháng, năm tệ nhất 2,588 %/tháng, DD năm 16,91 / toàn đường 16,82 [OWNER_SUMMARY_VI §1]. Đồng hồ ngẫu nhiên chỉ ~5,24 %/tháng (may ~+0,17pp) [OWNER_SUMMARY_VI §2]. Nói gọn 4–6 %/tháng, trung vị ~5, năm xấu ~3 [OWNER_SUMMARY_VI §2]. Đọc: `OWNER_SUMMARY_VI §1-2`.

## 3. Tháng này lỗ / thị trường yên có sao không?
Bình thường. Chỉ 41% tháng >= +5%, 70,5% tháng không lỗ [DEPLOYMENT_PLAN_VI §Rủi ro]. Tháng yên (6 flush/30d): trung vị lịch sử chỉ +0,7 %/tháng (trung bình +4,9; 4/12 tháng lỗ), ít cơ hội dip chứ không phải edge hỏng [OWNER_SUMMARY_VI §Tháng yên]. Đừng đổi cấu hình vì vài tuần yên. Đọc: `OWNER_SUMMARY_VI §Tháng yên`, `DEPLOYMENT_PLAN_VI §Cửa sổ`.

## 4. Tuần xấu / sụt vốn tối đa trông thế nào?
Tuần tệ nhất lịch sử -12,3% (hồi ~54 ngày); vài lần/năm mất 8–12%/tuần, 1–4 tháng mới về đỉnh là bình thường [QUICKSTART_VI §2]. DD trung vị 13,5, cao nhất 18,7; vốn phải chịu được DD 25% [DEPLOYMENT_PLAN_VI §Rủi ro]. P(DD > 20%) ~11%, P(năm lỗ) ~0,7% [OWNER_SUMMARY_VI §2]. Đọc: `DEPLOYMENT_PLAN_VI §Rủi ro/Tuần xấu`.

## 5. DD chạm 15% / 20% thì làm gì?
DD paper > 20%: dừng mở mới, chỉ giữ SL/TP [QUICKSTART_VI §5]. Lỗ một tháng > 10%: giảm nửa vốn tháng sau [QUICKSTART_VI §5]. Phân vị lợi nhuận < 5 sau >= 8 tuần: dừng [QUICKSTART_VI §5]. Go-live yêu cầu DD paper <= 15% [QUICKSTART_VI §3]. Đọc: `QUICKSTART_VI §5`, `DEPLOYMENT_PLAN_VI §4`.

## 6. Bot tắt / mất điện / mất mạng thì sao?
Chỉ một lệnh: `bash scripts/restart_all.sh` (xem trước bằng `--dry-run`) [OWNER_SUMMARY_VI §5]. Sau đó kiểm tra `protection_check` + `bot_health.py` hết CRITICAL mới cho chạy tiếp; không đặt tay giờ đầu [QUICKSTART_VI §6]. Stop/TP trên sàn vẫn bảo vệ; hở duy nhất là mảnh vừa khớp chưa kịp đặt exit (<= 20s) [QUICKSTART_VI §6]. Đọc: `BOT_RUNBOOK_VI §5`, `QUICKSTART_VI §6`.

## 7. Sàn / bot bảo trì có hẹn thì sao?
HỦY bid dip đang chờ từ trước giờ bắt đầu 30 phút tới hết giờ (`maintenance.json` hoặc `--maint-start/--maint-end` giờ UTC) [QUICKSTART_VI §6]. Stop/TP/backstop và chân carry giữ nguyên trên sàn [QUICKSTART_VI §6]. Tốn routine chỉ 1–2,5% lãi dip 5 năm [BOT_RUNBOOK_VI §4]. Đọc: `BOT_RUNBOOK_VI §4`.

## 8. Mỗi ngày xem gì (5 phút)?
`daily_status.py` rồi `bot_health.py`, `paper_report.py`, `prospective_scorecard.py` [OWNER_SUMMARY_VI §5]. Xem: backend sống + plan tươi < 4h30m, vòng bot sống, không thiếu stop (`unprotected`), không lệch sổ (`qty_mismatch`), không `cycle_error` > 1 giờ [OWNER_SUMMARY_VI §5]. Đọc: `BOT_RUNBOOK_VI §3`.

## 9. Carry là gì, rủi ro gì, ngày đáo hạn làm gì?
Carry = mua coin thật + short futures quý bằng nhau, vào khi basis >= 4%/năm và hợp đồng gần còn <= 7 ngày, mỗi chân 0,25x vốn, giữ tới đáo hạn (~4 quyết định/năm) [OWNER_SUMMARY_VI §1]. Cộng thêm chỉ ~+0,12–0,22 điểm %/tháng, không cứu được ma sát [OWNER_SUMMARY_VI §1]. Ngày đáo hạn: BÁN spot đúng 08:00 UTC (tốt nhất rải quanh cửa sổ tính giá index) [QUICKSTART_VI §4]. Đọc: `QUICKSTART_VI §4`, `GLOSSARY_VI §Carry`.

## 10. Có tăng carry lên f=0,5 được không?
Không, trên cùng UTA. f=0,25 tiền trống thấp nhất còn 22,49%, 0 giờ bị chặn; f=0,50 chỉ còn 1,85% và bị chặn 1 giờ nên cấm [OWNER_SUMMARY_VI §1]. Gap -10% cả 5 coin ở f=0,25 mất -28,85%, không cháy [OWNER_SUMMARY_VI §1]. Đọc: `DEPLOYMENT_PLAN_VI §Triển khai`, `BOT_RUNBOOK_VI §1`.

## 11. Sao không đặt mục tiêu 8%/tháng?
Điểm cao nhất trên đường đánh đổi cũng chỉ ~5,9 %/tháng ở DD trên 17,5 [OWNER_SUMMARY_VI §3]. Tăng size chỉ tăng lãi tuyến tính mà DD tăng nhanh hơn (edge/đơn vị bất biến) [OWNER_SUMMARY_VI §docs_update7]. Nên giữ cấu hình, không bơm size. Đọc: `OWNER_SUMMARY_VI §3 + §docs_update7`.

## 12. MANUAL (đặt tay) dùng được không?
Chưa. Bản tốt nhất M5_human chỉ 3,73 %/tháng (DD 17,9/17,8, thắng 64,8%), thiếu ~1,3 điểm so với sàn 5% [OWNER_SUMMARY_VI §3]. Cộng carry cũng chỉ 3,993, vẫn dưới 5 nên chưa dùng tiền thật [OWNER_SUMMARY_VI §3]. Đọc: `OWNER_SUMMARY_VI §3`, `FINAL_REPORT_VI`.

## 13. Khi nào được lên live?
Sau paper >= 8 tuần (sớm nhất ~2026-12-01), rồi testnet bắt buộc, rồi live vốn nhỏ [OWNER_SUMMARY_VI §4]. Đủ cả 4: (a) paper >= phân vị 20; (b) DD paper <= 15%; (c) lệch bot-plan <= 1,5 điểm %/tháng (đủ 14 ngày mới kết luận); (d) không `cycle_error` > 1h, không thiếu stop [QUICKSTART_VI §3]. Hôm nay (2026-10-06) paper mới ~0,2–1,1 ngày nên kết luận đúng là "quá sớm" [OWNER_SUMMARY_VI §4]. Đọc: `DEPLOYMENT_PLAN_VI §2`, `QUICKSTART_VI §3`.

## 14. Testnet để làm gì, PASS thế nào?
Testnet là sàn thử, chỉ kiểm cơ chế 7 ngày, KHÔNG kết luận P&L [TESTNET_PLAN_VI §0]. PASS đủ 9 tiêu chí: unprotected = 0, qty_mismatch = 0, mọi entry PostOnly, stop+TP trong 1 chu kỳ, carry hedge <= 2 cycle, không cycle_error > 1h, rate_limit ~ 0, preflight PASS [BOT_RUNBOOK_VI §8]. Đọc: `TESTNET_PLAN_VI §7`.

## 15. Làm sao biết edge còn sống?
Hai đèn vàng trong `daily_status.py` mục 6: (1) trung bình 6 tháng < 1,61 %/tháng; (2) tỉ lệ chốt lời dip nửa năm < 0,434 thì ĐIỀU TRA, không tự đổi cấu hình [QUICKSTART_VI §5]. Nền: độ dốc +0,067 (khoảng tin cậy chứa 0), 6 tháng gần nhất 7,38% — không decay [OWNER_SUMMARY_VI §docs_update7]. Đọc: `QUICKSTART_VI §5`.

## 16. Có cần sửa tham số khi thị trường đổi không?
Không. Chọn walk-forward không thắng giữ cố định; blend book 0,8/0,2 giữ nguyên [DEPLOYMENT_PLAN_VI §Chọn]. Không bao giờ chạy 1 pha/1 đồng hồ lẻ (pha đơn COVID -21,8% vượt ngưỡng, mix 4 pha ~-16,1%) [QUICKSTART_VI §6]. Không sửa ngưỡng go-live/dừng sau khi thấy dữ liệu paper [QUICKSTART_VI §7]. Đọc: `DEPLOYMENT_PLAN_VI §Chọn`, `QUICKSTART_VI §7`.

## 17. Khóa API để ở đâu, ai được bật live?
Chỉ trong `.env` local, không commit, không dán chat [QUICKSTART_VI §3]. Live bị khóa cho tới khi chủ tài khoản mở `BOT_ALLOW_LIVE=yes-real-money` sau testnet sạch + đủ 4 điều kiện [QUICKSTART_VI §3]. Trước testnet/live phải preflight PASS (exit 0): key, Unified, Hedge, Cross, 5x từng coin, vốn [QUICKSTART_VI §3]. Đọc: `BOT_RUNBOOK_VI §1-2`, `TESTNET_PLAN_VI §3`.

## 18. Backend khi nào cần khởi động lại?
Mỗi ngày kiểm tra `.\run_backend.ps1 -Status`; plan `trade_plan_v376.json` quá 4h30m là cũ (bot chỉ giữ exits) thì dựng lại backend [BOT_RUNBOOK_VI §1]. Sau MỌI lần cập nhật code thêm route API mới (ví dụ `/api/carry`) phải restart tay một lần thì route mới có hiệu lực [BOT_RUNBOOK_VI §1]. Đọc: `BOT_RUNBOOK_VI §1`.
