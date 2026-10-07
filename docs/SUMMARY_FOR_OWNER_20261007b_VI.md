# Tóm tắt cho chủ sở hữu 2026-10-07 (b) — sóng nghiên cứu ngày 07/10

## 1. Tiền của anh/chị hôm nay có gì thay đổi?
- Không có gì thay đổi trên tiền thật: vẫn là G2 + carry (BOT ~5,63 %/tháng, DD ~17; MANUAL ~3,7 vẫn dưới ngưỡng 5).
- Không triển khai thêm hướng mới nào; 7 hướng CLOSED + họ VRP đều bị loại, không đụng tới tiền.
- Các bot paper đã được sửa lỗi thoát lệnh, chạy lại bình thường; cửa sổ lỗi đã loại khỏi bảng điểm.

## 2. Lỗi bot thoát lệnh (3 dòng) — vì sao quan trọng?
- Dòng 1: Từ commit 1c0469a, lệnh market thoát (chốt/timeout/stop) vừa gửi xong đã bị chính bot hủy ngay trong cùng vòng lặp.
- Dòng 2: Hậu quả: vị thế kẹt mở không bảo vệ, cứ 2 phút gửi lại mà không bao giờ khớp (paper kẹt 18-20 mảnh/runner đêm 06-07/10).
- Dòng 3: Đã sửa ở commit cb14cb7 (không bao giờ hủy market exit đã xác nhận) + 10 test hồi quy; ý nghĩa testnet/live: không sửa thì stop-loss/timeout ngoài đời thật cũng không khớp — rủi ro giữ lệnh trần không giới hạn.

## 3. Anh/chị cần làm gì (theo thứ tự)
1. Chạy `.\scripts\register_keepalive.ps1 -Status` để xem, rồi `-Register` để đăng ký giữ bot + backend tự chạy lại.
2. Giữ các paper chạy liên tục, đừng tắt (bằng chứng prospective đang tích lũy từng ngày).
3. Testnet theo đúng docs/TESTNET_PLAN_VI.md (không bỏ bước, không tăng size sớm).
4. Ngưỡng bằng chứng (oc_paperpower): 8 tuần QUÁ YẾU (bot không edge vẫn qua cổng 38 %; lỗ 1 %/tháng vẫn qua 32 %) — 8 tuần chỉ cho phép pilot nhỏ; cần 26 tuần mới tạm tin (lọt giả còn 14 %/8 %); 52 tuần mới chắc (3 %/1 %).

## 4. Hôm nay cái gì thất bại (mỗi cái một dòng)
- oc_relflush: size theo coin "vượt trội" trong flush thua base (dSum -0,109), chiều ngược lại ăn nhưng vỡ DD — đóng.
- oc_tailhedge: mua put BTC hàng tháng tốn phí 17-42 % vốn/năm mà DD của G2 không phải dạng put cứu được — đóng dạng always-on.
- oc_ripcont: mua pullback sau rip không có edge (chỉ 1/4 năm trên +5bps) — đóng.
- oc_manualsplit: chia đôi TP cho MANUAL tăng win nhưng giảm lợi nhuận (R5 3,508 vs 3,728) — đóng.
- oc_stablegate: cửa sổ stablecoin thua cả G2 lẫn mức khống chế CTRL — đóng.
- oc_putwrite: không biến thể nào lãi (tốt nhất +0,41 %/tháng vẫn lỗ năm 2021); phủ lên G2 còn trừ 0,04 — đóng.
- oc_vrpgate: bộ lọc premium không hơn bán mọi tuần (G1 rớt DD, G2 kém R087 cả mean lẫn worst) — đóng.
- Họ VRP straddle: cú +1 điểm %/tháng hóa ra là định giá DVOL cao hơn IV thật (~0,87x); giá đúng thì overlay chỉ còn +0,14 (r0,87) và -0,35 (r0,80) — KHÔNG triển khai; kiểm toán độc lập PASS-WITH-NOTES.

## 5. Cái gì còn đang chạy (chưa kết luận)
- oc_kronoshidden: độ nghiêng dip Kronos, năm sau-release mới là phán quyết (dev chỉ là chặn trên).
- Deribit strike-level fetch: lấy giá từng strike để định giá weekly thật (mẫu BTC khớp corr ~0,999).
- bot_soakinv: soak kiểm bất biến của paper sau fix.
- Sổ paper straddle Bybit thật (scripts/straddle_paper.py): lệnh đầu tiên có thể vào sáng thứ Sáu 09/10 — đây là bằng chứng duy nhất còn lại cho họ VRP.
- Tích lũy paper/OOS hàng tuần (tuần 2: cửa sổ +1,995 %, win 90 %, pct 72,7 — còn quá sớm để kết luận).
