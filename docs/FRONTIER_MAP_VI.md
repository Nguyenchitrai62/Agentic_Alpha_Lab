# Bản đồ return–drawdown họ G2 (gate costs, 4-phase 5y)
Số liệu copy nguyên văn từ báo cáo được dẫn; bảng đủ 29 hàng ở `research/diagnostics/docs_frontier/frontier_table.csv`, vẽ bằng script cùng thư mục.
![frontier](../research/diagnostics/docs_frontier/frontier.png)
## Bảng rút gọn (5y %/tháng | DD full-path | năm gần nhất | kiểm định)
| id | 5y | DD full | gần nhất | kiểm định |
|---|---|---|---|---|
| G2 (triển khai, ★) | 5.410 | 16.82 | 4.648 | v421 PASS |
| D17BF | 5.425 | 16.90 | 5.060 | v411 PASS |
| D13BF | 4.971 | 14.86 | 4.723 | v424 PASS (không ROBUST.md) |
| G2K20 | 5.874 | 17.69 | 4.716 | v422 PASS; rớt vòng Y4 |
| G2+carry f0.25 | 5.634 | 16.66 | 4.698 | post-hoc, cần prospective |
| G2K20+carry | 6.097 | 17.54 | 4.766 | post-hoc |
| GV3 (tốt nhất họ governor) | 5.849 | 17.50 | 4.824 | REJECT (năm gần nhất < 5) |
| NO_VT | 6.119 | 18.39 | 4.772 | diagnostic |
| NO_GOV | 5.907 | 19.60 | 4.824 | diagnostic, DD ~20 |
| A1 (Amihud) | 5.624 | 16.66 | 4.750 | chọn trên dev4 |
| A1 S5 (Bybit) | 4.884 | 21.32 | — | FAIL (gap ~0, DD > 20) |
| M1 (MVRV) | 5.881 | 16.22 | 4.648 | robust nhưng hòa → không strict |
| A1+M1 post-hoc | 5.939 | 15.92 | 4.750 | tương thích, không phải lựa chọn |
| VRP FULL | 5.332 | 18.11 | 5.025 | REJECT |
| v423_X45 | 5.118 | 15.81 | 4.643 | cả 2 frontier |
| v409_D15B08 (DD thấp nhất) | 4.626 | 14.94 | 4.054 | frontier full-path |
| v407_D20B11 (R cao nhất) | 5.894 | 19.10 | 5.528 | frontier, DD > 19 |
| K2 | (không 5y; dev4 5.772) | 16.09 | 4.801 | REJECT, vắng mặt trên scatter |
1. Các điểm dial thuần (governor GV1–GV3, ablation NO_*/TOUCH, các hàng frontier v399–v407) nằm gần một đường: muốn lợi nhuận 5y cao hơn thì phải chịu DD full-path cao hơn.
2. Điểm rời khỏi đường theo hướng tốt là M1 và A1+M1 (lợi nhuận ~5.9 mà DD chỉ ~16), còn VRP rời theo hướng xấu (lợi nhuận thấp hơn G2 mà DD cao tới 18.11). LƯU Ý (leader): oc_mvrvmech cho thấy phần lợi của M1 KHÔNG đến từ tín hiệu MVRV (tách riêng, cổng MVRV làm book tệ hơn: 2.461 < 2.531) mà từ tương tác với governor theo pha (tránh một lần pha 3 bị tắt 165 thanh đầu 2024) — dựa trên 2 sự kiện và chưa kích hoạt lần nào ở năm gần nhất; A1 thì mất sạch lợi thế và DD > 20 với giá Bybit (S5). Vì vậy cả hai KHÔNG được triển khai.
3. Điểm đang triển khai là G2 vì tái tạo khớp từng chữ số trước mọi overlay, blind audit PASS, DD 16.82 dưới 20 và không năm nào lỗ — mọi biến thể khác đều đo chênh lệch so với nó.
4. Overlay carry (+0.22 điểm/tháng) và các hàng frontier lợi nhuận cao đều là post-hoc trên đúng 5 năm nghiên cứu nên chưa được chọn, cần nhật ký prospective xác nhận.
5. Chủ tài khoản đánh đổi rõ ràng: lấy DD thấp (v409_D15B08 14.94, D13BF 14.86) thì nhận ~4.6–5.0%/tháng, lấy lợi nhuận cao (G2K20+carry 6.10, NO_VT 6.12, v407 5.89) thì DD lên 17.5–19+ và kèm rủi ro quá khớp quá khứ.
Nguồn: v421/v411/v424/v422_audit, oc_carrycompound, oc_g2k20compound, oc_governor, oc_ablation, oc_lit_xs, oc_amihudrobust, oc_lit_position, oc_mvrvrobust, oc_kronoshidden, oc_vrpstrike, oc_frontier.
