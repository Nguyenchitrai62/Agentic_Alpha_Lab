# Tóm tắt cho chủ tài khoản — 2026-10-07 (đọc 5 phút)

> Mọi con số đều có nguồn trong ngoặc. "post-hoc" = thử sau khi đã thấy kết quả, chỉ tham khảo.

## 1. Giải pháp chốt và con số trung thực

- **Chạy BOT G2 + carry quý f=0,25 trong MỘT tài khoản Bybit UTA** (lệnh giấy `--corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0 --carry-f 0.25`, plan `trade_plan_v376.json`) [docs/PLAN_NEXT_20261006.md] [docs/FINAL_REPORT_VI.md].
- **Nghiên cứu (walk-forward 5 năm, phí gate Bybit maker 0,02%/taker 0,055%): G2 đơn 5,41 %/tháng, năm tệ nhất 2,588, DD năm 16,91/toàn đường 16,82** [docs/FINAL_REPORT_VI.md] [docs/OWNER_SUMMARY_VI.md].
- **G2+carry f=0,25 kỳ vọng chính (lãi carry tái đầu tư): 5,634 %/tháng, năm tệ nhất 2,778, DD năm 16,75/toàn đường 16,66** [docs/FINAL_REPORT_VI.md]; bản bảo thủ (year-start, không tái đầu tư) chỉ 5,533/2,736/16,78 [docs/OWNER_SUMMARY_VI.md] [docs/FINAL_REPORT_VI.md].
- **Kỳ vọng live thấp hơn số research:** luck đồng hồ dip ~0,17 điểm nên đồng hồ ngẫu nhiên chỉ ~5,24 %/tháng (giữ số 5,41 kèm giải thích) [docs/FINAL_REPORT_VI.md]; nói gọn 4–6 %/tháng, trung vị ~5 %/tháng, năm xấu chỉ ~3 %/tháng [docs/OWNER_SUMMARY_VI.md].
- **Dưới ma sát (G2+carry, lãi tái đầu tư): trễ 15 phút 5,438; trượt stop 50% 5,125; giá Bybit 5,111 — vẫn >=5; chỉ rớt ở phí gấp đôi S1 4,780 và trễ 30 phút 4,806, không năm lỗ** [docs/CLOSED_DIRECTIONS.md].
- **MANUAL (người đặt tay) tốt nhất trung thực chỉ 3,73 %/tháng (DD 17,9/17,8, thắng 64,8%), +carry cũng chỉ 3,993 — CHƯA đạt sàn 5 %/tháng, không dùng tiền thật** [docs/FINAL_REPORT_VI.md].
- **Mục tiêu stretch 8 %/tháng / DD <15 đã đóng:** biên cao nhất chỉ ~5,9 %/tháng ở DD trên 17,5; bản DD 14,98 thiếu lợi nhuận và rớt DD dưới mọi ma sát [docs/FINAL_REPORT_VI.md] [docs/PLAN_NEXT_20261006.md].

## 2. Hôm nay đã chứng minh được gì

- **Bền tham số:** jitter đồng thời ±10% (12 bộ, Kaggle): cả 12/12 đều >=5,09 (5,09–5,95, trung vị 5,54), DD năm 16,3–18,2, không năm lỗ [docs/OWNER_SUMMARY_VI.md] [docs/PLAN_NEXT_20261006.md].
- **Margin một UTA (43.824 giờ): f=0,25 an toàn — tiền trống thấp nhất còn 22,49%, 0 giờ bị chặn, gap -10% giờ tệ nhất -28,85% không cháy; f=0,50 bị chặn 1 giờ nên LOẠI** [docs/FINAL_REPORT_VI.md] [research/tournament/oc_carrymargin/REPORT.md].
- **Tuần sập:** LUNA -6,05% (hồi ~35,8 ngày), FTX chỉ -2,47% (hồi ~13,8 ngày), dip gross tối đa 0,29–0,77x, margin UTA tối đa <=0,26, 0 giờ chặn [research/tournament/oc_eventstress/REPORT.md]; COVID 03/2020 là bài nặng nhất: mix 4 pha ~-16,1%, pha đơn tệ nhất -21,8% nên cấm chạy pha đơn [docs/OWNER_SUMMARY_VI.md].
- **Sức chứa vốn (ước lượng bảo thủ): tới ~50k USDT G2 chỉ giảm -0,34 điểm %/tháng (<=10k chỉ -0,22); 100k giảm rõ -1,07; 500k không dùng được** [docs/PLAN_NEXT_20261006.md] [research/tournament/oc_capacity/REPORT.md].
- **Paper khớp research:** OOS sạch 6 ngày (30/09–06/10) +1,995%, phân vị 72,7 (p5 -3,309/p50 +0,466/p95 +7,477), DD gate 0,766%, 10 rung thắng 9 [docs/FINAL_REPORT_VI.md]; parity plan-vs-live 0 lệch [docs/OWNER_SUMMARY_VI.md]; spread Bybit thật chỉ bào ~0,7% lãi dip 5 năm [docs/OWNER_SUMMARY_VI.md].
- **Giao carry đúng giờ đáo hạn:** bán spot 6 lát 07:30–08:00 lệch chỉ -0,8±6,2bp (tệ nhất 19,6bp), tốt hơn bán một lệnh (lệch tới 75–91bp) [research/tournament/oc_deliverytrack/REPORT.md].
- **Hồ sơ dự phòng G2K20+carry (post-hoc): base 6,097/năm tệ 3,021/DD 17,64, tệ nhất S1 5,109 — giữ >=5 dưới MỌI ma sát nhưng DD cao hơn G2 ~1 điểm; đã rớt fold năm gần nhất (4,716 so với 5,06 của G2) nên G2 vẫn là chính** [research/tournament/oc_g2k20compound/REPORT.md] [research/diagnostics/oc_g2k20folds/REPORT.md].

## 3. Cái gì thất bại / đã đóng hôm nay

- **Tăng carry f=0,5 có vay USDT THUA f=0,25 (base 5,569/5,424 so với 5,634; S1 4,696/4,550 so với 4,780) — giữ 0,25** [research/tournament/oc_carryborrow/REPORT.md] [docs/PLAN_NEXT_20261006.md].
- **Carry thêm BNB/SOL/XRP (post-hoc): +0,145 điểm %/tháng (tổng 5,771 so với 5,626) nhưng peak spot 2,0x vốn phải vay + cần tài khoản Binance — GÁC LẠI** [research/tournament/oc_carrymore/REPORT.md] [docs/PLAN_NEXT_20261006.md].
- **Carry chỉ 1 coinbasis cao nhất (post-hoc) THUA cả 2 coin (-0,10 điểm %/tháng 5 năm) — giữ cả 2 coin** [research/tournament/oc_idea4_carrymax/REPORT.md].
- **Vòng ý tưởng 05/10 (oc_idea1–oc_idea10, khác với các idea mới hôm nay): idea2 (stop XRP 5,5/rest 4) đã chấm engine 4 pha = v417-X, BỊ LOẠI (fold 0/3) [research/tournament/oc_oldidea2/REPORT.md]; còn lại ĐÓNG (lọc funding, throttle basis/dominance, TP nhanh, VRP dial…)** [research/tournament/oc_idea1/REPORT.md] [research/tournament/oc_idea8/REPORT.md].
- **Mô hình book C1/C2 ĐÓNG 2/2 (C1 dev chỉ 3,593/DD 19,17 thua cả 4 năm so với 5,601/16,91 đang chạy)** [docs/OWNER_SUMMARY_VI.md].

## 4. Rủi ro đã biết và bug đang mở

- **Bot soak 24h (crash 10/10, BTC -14,9%) tìm 3 lỗi (B1 piece book thứ 2 thiếu SL/TP, B2 lượng lẻ dưới min không bảo vệ, B3 giá 0 làm chết cycle) — ĐÃ SỬA và soak lại: lỗ hổng bảo vệ 9491 -> ~0, exception 264 -> 0; leader sửa thêm 2 điểm (piece mồ côi dùng SL/TP của chính nó; plan TP=0 thì giữ SL/TP lúc vào lệnh). Commit 40e5fdf; 6 runner tag đã chạy code mới từ 19:25 UTC 06/10 (runner `paper` R2 cũ vẫn code cũ). Soak riêng carry qua đáo hạn: 0 vi phạm** [docs/opencode/BOT_SOAKFIX_20261006.md] [docs/opencode/BOT_CARRYSOAK_20261007.md].
- **Review độc lập code sửa bot (07/10): không có lỗi chặn testnet; 2 điểm mức trung bình phải sửa TRƯỚC LIVE (dip không có backstop chỉ có TP; khởi động lại <2 phút sau lệnh market có thể hủy lệnh bảo vệ đang chờ) + 4 điểm phòng thủ — worker bot_reviewfix2 đang sửa** [docs/opencode/REVIEW_SOAKFIX_20261007.md].
- **Backend + 6 runner paper chết 10:32–14:37 UTC ngày 06/10 (plan kẹt bar 08:00, lỡ cycle 12:00, ~4h plan cũ); đã khởi động lại, nguyên nhân là console foreground bị đóng + runner nằm trong shell giới hạn thời gian** [docs/opencode/BACKEND_INCIDENT_20261006.md] [docs/PLAN_NEXT_20261006.md].
- **Thu thập liquidation/topbook mới phủ ~56% thời gian (32,7/58,0 giờ) vì backend chết — chưa dùng nghiên cứu được cho tới khi chạy liên tục >=95%** [docs/opencode/COLLECTOR_20261006.md].
- **Xác suất thật: P(DD>20%) ~11%, P(năm lỗ) ~0,7%; chuẩn bị chịu DD tới ~18%, vốn phải chịu được DD 25%** [docs/OWNER_SUMMARY_VI.md].
- **Mọi paper mới ~0,2–1,1 ngày — kết luận duy nhất là "quá sớm", chưa đủ 14/56 ngày** [docs/FINAL_REPORT_VI.md].

## 5. Việc của chủ (làm đúng thứ tự)

1. **Bật watchdog backend:** chạy `run_backend.ps1 -Ensure` + bật Task `AlphaLabBackendWatchdog` (đang Disabled từ 02/10) để backend/tunnel tự sống lại [docs/opencode/BACKEND_INCIDENT_20261006.md] [docs/PLAN_NEXT_20261006.md].
2. **Sau mọi reboot/mất điện chỉ chạy MỘT lệnh:** `.\scripts\restart_all.ps1` (chạy từ console của bạn; Start-Process ẩn — bản WMI đã bỏ vì bot chết sau ~30 phút) — không dùng shell tạm [docs/PLAN_NEXT_20261006.md].
3. **Mỗi ngày xem 5 thứ:** backend sống + plan tươi <4h30m; vòng bot sống; không vị thế thiếu stop; không cycle_error >1h; equity/DD/fills — bằng `daily_status.py` rồi `bot_health.py`, `paper_report.py` [docs/OWNER_SUMMARY_VI.md].
4. **Testnet: đã gỡ chặn phía code** (soak fix + carry soak xong). Làm theo docs/TESTNET_PLAN_VI.md: sub-account testnet, key testnet tự điền vào .env, UTA/Hedge/Cross/5x, nạp 5-10k USDT testnet, preflight -> dry --once -> chạy 7 ngày. Live chỉ sau 7 ngày testnet sạch + >= 8 tuần paper + 4 cổng [docs/TESTNET_PLAN_VI.md] [docs/DEPLOYMENT_PLAN_VI.md].
5. **Testnet (sau khi hết chặn):** theo `docs/TESTNET_PLAN_VI.md` 7 ngày, đủ 9 điều kiện mới xét; lệnh vào PostOnly, risk_guard ON ở testnet/live [docs/FINAL_REPORT_VI.md].
6. **Live chỉ khi đủ cả 4 (sau >=8 tuần paper, sớm nhất ~01/12/2026):** paper ở phân vị >=20; DD paper <=15%; lệch bot-vs-plan <=1,5 điểm %/tháng (đủ 14 ngày); không lỗi cycle >1h [docs/OWNER_SUMMARY_VI.md] [docs/FINAL_REPORT_VI.md].

## 6. Phiên nghiên cứu tiếp theo làm gì

- Cả 6 ý tưởng của bản rà soát 07/10 đều ĐÓNG (Kelly rung, stop dip, carry bậc, carry 1 coin, MANUAL nghỉ 4h, D13BF+carry) [docs/CLOSED_DIRECTIONS.md]; mọi audit hôm nay PASS (capacity, eventstress, deliverytrack, carryborrow, carrymore). Biên lợi nhuận-DD đã cạn: chỉ còn chờ bằng chứng paper/testnet.
- Nuôi paper đủ >=8 tuần + 4 cổng go-live; divergence >=14 ngày mới kết luận; OOS hằng tuần bằng `score_oos.py --fetch --run` [docs/FINAL_REPORT_VI.md].
- Chỉ nghiên cứu mới khi có dữ liệu thật mới (liquidation đủ 3 tháng sớm nhất 04/01/2027, log prospective); không lặp lại hướng trong `docs/CLOSED_DIRECTIONS.md` [docs/PLAN_NEXT_20261006.md] [docs/CLOSED_DIRECTIONS.md].
