# Kế hoạch triển khai thực tế (đăng ký trước, 2026-10-05)

Tài liệu này cố định TRƯỚC khi có kết quả paper: kỳ vọng trung thực, điều kiện để chuyển sang tiền thật và ngưỡng dừng.
Không sửa các ngưỡng sau khi đã thấy dữ liệu paper (nếu sửa phải ghi rõ ngày và lý do).

## 1. Kỳ vọng trung thực (dev 2021-09..2025-09 + năm giấu, đánh giá 4 pha đồng hồ, phí Bybit, funding bất lợi)

| Sản phẩm | Pipeline | %/tháng kỳ vọng | DD kỳ vọng | Ghi chú |
|---|---|---|---|---|
| BOT | R2-4P (v376) | 4.8 (thước đo cân lại mỗi năm, 5 năm; từng năm 2.0 / 3.8 / 4.0 / 10.6 / 3.9); thực tế trên Bybit + ma sát ~3.5-4.4 | 25 (năm xấu nhất), tới ~28 khi trượt stop / giá Bybit | cần bot chạy 24/7, 4 khung giờ lệch 1h; không năm lỗ trong mọi kịch bản ma sát (research/diagnostics/r2_4p_robust5) |
| **BOT khuyến nghị (paper từ 2026-10-05)** | **R2B1D17BF (v411)** | **5.43** (giá Bybit + ma sát: 4.97; trễ 15': 5.24) | năm xấu nhất 18.3, toàn đường cong 16.9; mọi kịch bản ma sát <= 20 | size dip theo tương quan + dip x1.7 + bộ lọc gấu cho book; thắng 65.5 %, không năm lỗ; bot: `--corr-size --dip-mult 1.7 --bear-book` |
| BOT (các điểm khác) | R2B1D18 (v408) / R2B1D16 (v406) | 5.45 / 5.14 (5 năm 2021-2026; ma sát thực tế D16: 4.8-5.1) | năm xấu nhất 19.1 / 17.3; toàn đường cong 17.6 / 16.4 | size dip theo tương quan (cần bot chỉnh lệnh theo phút), tỉ lệ thắng 65 %, không năm lỗ; cổng nền PASS (audit OpenCode); bot: `--corr-size --dip-mult 1.8` |
| MANUAL | M4 / M5 | ~3.5 với người thật (trễ 15', bỏ nến đêm) | 22-24 % (pha xấu 32-34 %) | dùng ~80 % vốn -> ~2.8 %/tháng, DD < 20 % |

Mục tiêu 5 %/tháng với DD <= 20 % CHƯA đạt một cách trung thực; các con số trên là trần của thông tin hiện có.
Cập nhật 2026-10-05: thước đo cũ (mix 4 pha liên tục) phóng đại các năm sau; con số trên dùng thước đo cân lại 1/4 mỗi pha đầu mỗi năm.

## 2. BOT: lộ trình

1. Paper (đang chạy từ 2026-10-05): kế hoạch paper `trade_plan_v376.json` (backend) + bot giấy khớp theo giá Bybit thật
   (`python -m bot.run --mode paper --equity 5000`, `artifacts/bot/paper/exchange.json`).
2. Testnet (tùy chọn): `--mode testnet` với khóa testnet trong `.env` để kiểm tra API thật (không ảnh hưởng tiền).
3. Tiền thật nhỏ: chỉ khi ĐỦ cả 4 điều kiện sau, đo trên bot giấy, sau tối thiểu 8 tuần:
   - (a) lợi nhuận bot giấy nằm ở phân vị >= 20 của phân phối bootstrap trung thực cho cùng số ngày (`scripts/prospective_scorecard.py`);
   - (b) DD bot giấy <= 15 %;
   - (c) sai lệch bot giấy so với kế hoạch paper <= 1.5 điểm %/tháng (đo chất lượng thực thi);
   - (d) không có lỗi `cycle_error` kéo dài > 1 giờ, không có vị thế nào thiếu stop.
   Vốn tối thiểu ~5000 USDT (dưới mức này các bậc dip BTC nhỏ hơn 0.001 BTC bị bỏ do 4 khung chia vốn làm 4). Kiểm chứng khối lượng tối thiểu Bybit cho R2B1D17BF (research/diagnostics/oc_lots): 10.000 USDT đặt được 100 % lệnh book / 98 % bậc dip (giữ ~100 % lãi/lỗ); 5.000 USDT: 96 % / 94 % (~99.5 %); 2.000 USDT: 80 % / 81 % (mất ~5-20 %, chủ yếu BTC); khuyến nghị >= 5.000 USDT, tốt nhất ~10.000.
4. Tăng vốn: sau 3 tháng tiền thật nếu (a)-(c) vẫn đúng trên tiền thật.

## 3. MANUAL: cách theo

- Theo M4 hoặc M5 trên web, 5 lần/ngày (07, 11, 15, 19, 23 giờ VN; bỏ 03 giờ), đặt lệnh trong 15 phút sau khi đóng nến 4h.
- Mỗi lệnh dip là lệnh limit mua kèm TP limit và SL sàn (đặt một lần, không cần theo dõi).
- Dùng ~80 % vốn tài khoản cho pipeline (giữ DD < 20 %).

## 4. Ngưỡng dừng (cả hai sản phẩm, tiền thật)

- DD tài khoản > 20 %: dừng mở lệnh mới, chỉ giữ SL/TP; xem xét lại trước khi chạy tiếp.
- Lỗ một tháng > 10 %: giảm vốn dùng một nửa trong tháng kế tiếp.
- Phân vị lợi nhuận thực < 5 sau >= 8 tuần: dừng (mô hình không còn khớp với nghiên cứu).

## Rủi ro thống kê của R2B1D17BF (bootstrap, OpenCode oc_mcdd, 2026-10-05)

Bootstrap khối dừng (khối TB 20 ngày, 10.000 năm giả lập từ 5 năm 2021-09..2026-09, metric reset theo năm):
- Xác suất một năm 12 tháng lỗ: ~0,7 %. Trung vị lợi nhuận ~5,1 %/tháng (p5 1,5 / p95 10,3); chỉ ~52 % năm đạt >= 5 %/tháng.
- DD đánh dấu 1 ngày: trung vị 14,5 %, p95 22,6 %; P(DD > 20 %) ~11 %, P(DD > 25 %) ~2 %.
- Nghĩa là: kỳ vọng hợp lý là 4-6 %/tháng với DD 12-18 %, nhưng khoảng 1/9 năm có thể chạm DD > 20 %. Vốn nên là số tiền chịu được DD 25 %.

## Cửa sổ 12 tháng trượt (OpenCode oc_rolling17, 49 cửa sổ bắt đầu ngày 24 mỗi tháng 2021-09..2025-09)

R2B1D17BF: không cửa sổ nào lỗ; %/tháng min 2,73 / p10 3,25 / trung vị 4,89 / p90 8,88 / max 11,71; DD min 8,3 / trung vị 13,5 /
p90 18,3 / max 18,7; 49 % cửa sổ đạt >= 5 %/tháng, 61 % có DD < 15, 100 % có DD < 20. Kỳ vọng thực tế: khoảng 5 %/tháng trung vị,
một năm xấu có thể chỉ ~3 %/tháng.

KPI (oc_kpi): 41 % số tháng >= +5 %, 72 % số tháng không lỗ, chuỗi lỗ dài nhất 2 tháng; win book 51,5 %, rung dip 68,7 %, tất cả 65,5 %.
Lưu ý đòn bẩy: notional dip có lúc tới ~6,4x vốn khi thị trường yên (stop gần) - đặt đòn bẩy tài khoản Bybit đủ cao (cross margin) và
cân nhắc trần notional (v421 G2: cùng lợi nhuận, DD năm 16,9; đang kiểm tra robustness).

## Cú sốc giá tức thì (OpenCode oc_gapstress) - lý do nên bật trần notional dip

Giả lập: mọi phút có vị thế mở trong 5 năm, cả 5 coin sụt tức thì (sàn sập / flash crash nhảy qua mọi stop), đóng ở giá sập.
Sụt -10 %: trung vị lỗ 0,85 % vốn, p99 13 %, nhưng phút tệ nhất (mọi thang dip đầy cùng lúc, vd 2025-08-14) lỗ 58 % vốn (một phase 71 %).
Với trần notional dip 2x vốn (v421 G2, `--dip-gross-cap 2.0`): phút tệ nhất còn 33,5 % (3x: 39 %); trung vị và p99 không đổi.
Lịch sử 5 năm: G2 5,41 %/tháng, DD năm 16,9 / toàn giai đoạn 16,8 (D17BF 5,43 / 18,3 / 16,9). Khuyến nghị: chạy thật nên bật
`--dip-gross-cap 2.0` (đang có bot paper d17bfg2 song song d17bf và g2k20 để so sánh tiến cứu).

Robustness G2 (v421 audit, OpenCode): dưới mọi ma sát DD thấp hơn D17BF - chi phí x2: 4,57 %/tháng DD 17,45; trễ 15 phút 5,21 / 16,91;
trễ 30 phút 4,58 / 17,32; trượt stop 50 %: 4,90 / 17,31 (D17BF 19,97); giá Bybit: 4,88 / 18,11 (D17BF 19,85). => D17BF + trần 2x là bản triển khai.
