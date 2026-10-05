# Kế hoạch triển khai thực tế (đăng ký trước, 2026-10-05)

Tài liệu này cố định TRƯỚC khi có kết quả paper: kỳ vọng trung thực, điều kiện để chuyển sang tiền thật và ngưỡng dừng.
Không sửa các ngưỡng sau khi đã thấy dữ liệu paper (nếu sửa phải ghi rõ ngày và lý do).

## 1. Kỳ vọng trung thực (dev 2021-09..2025-09 + năm giấu, đánh giá 4 pha đồng hồ, phí Bybit, funding bất lợi)

| Sản phẩm | Pipeline | %/tháng kỳ vọng | DD kỳ vọng | Ghi chú |
|---|---|---|---|---|
| BOT | R2-4P (v376) | ~4.0-4.6 (năm giấu 3.9) | 19-25 % | cần bot chạy 24/7, 4 khung giờ lệch 1h |
| MANUAL | M4 / M5 | ~3.5 với người thật (trễ 15', bỏ nến đêm) | 22-24 % (pha xấu 32-34 %) | dùng ~80 % vốn -> ~2.8 %/tháng, DD < 20 % |

Mục tiêu 5 %/tháng với DD <= 20 % CHƯA đạt một cách trung thực; các con số trên là trần của thông tin hiện có.

## 2. BOT: lộ trình

1. Paper (đang chạy từ 2026-10-05): kế hoạch paper `trade_plan_v376.json` (backend) + bot giấy khớp theo giá Bybit thật
   (`python -m bot.run --mode paper --equity 5000`, `artifacts/bot/paper/exchange.json`).
2. Testnet (tùy chọn): `--mode testnet` với khóa testnet trong `.env` để kiểm tra API thật (không ảnh hưởng tiền).
3. Tiền thật nhỏ: chỉ khi ĐỦ cả 4 điều kiện sau, đo trên bot giấy, sau tối thiểu 8 tuần:
   - (a) lợi nhuận bot giấy nằm ở phân vị >= 20 của phân phối bootstrap trung thực cho cùng số ngày (`scripts/prospective_scorecard.py`);
   - (b) DD bot giấy <= 15 %;
   - (c) sai lệch bot giấy so với kế hoạch paper <= 1.5 điểm %/tháng (đo chất lượng thực thi);
   - (d) không có lỗi `cycle_error` kéo dài > 1 giờ, không có vị thế nào thiếu stop.
   Vốn tối thiểu ~3000-5000 USDT (dưới mức này các bậc dip BTC nhỏ hơn 0.001 BTC bị bỏ do 4 khung chia vốn làm 4).
4. Tăng vốn: sau 3 tháng tiền thật nếu (a)-(c) vẫn đúng trên tiền thật.

## 3. MANUAL: cách theo

- Theo M4 hoặc M5 trên web, 5 lần/ngày (07, 11, 15, 19, 23 giờ VN; bỏ 03 giờ), đặt lệnh trong 15 phút sau khi đóng nến 4h.
- Mỗi lệnh dip là lệnh limit mua kèm TP limit và SL sàn (đặt một lần, không cần theo dõi).
- Dùng ~80 % vốn tài khoản cho pipeline (giữ DD < 20 %).

## 4. Ngưỡng dừng (cả hai sản phẩm, tiền thật)

- DD tài khoản > 20 %: dừng mở lệnh mới, chỉ giữ SL/TP; xem xét lại trước khi chạy tiếp.
- Lỗ một tháng > 10 %: giảm vốn dùng một nửa trong tháng kế tiếp.
- Phân vị lợi nhuận thực < 5 sau >= 8 tuần: dừng (mô hình không còn khớp với nghiên cứu).
