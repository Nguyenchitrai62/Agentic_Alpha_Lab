# Từ điển thuật ngữ (VI) — cho chủ tài khoản

> Mỗi mục 1–2 câu, kèm ví dụ và tài liệu đọc thêm. Số liệu là backtest walk-forward 5 năm, xem `docs/FINAL_REPORT_VI.md`.
> Cách chạy và kỳ vọng xem `docs/QUICKSTART_VI.md`, tóm tắt xem `docs/OWNER_SUMMARY_VI.md`, vận hành xem `docs/BOT_RUNBOOK_VI.md`.

## BOT vs MANUAL
- BOT = phần mềm đặt lệnh thay người, gồm book + thang dip, chạy 24/7 [QUICKSTART_VI]. Ví dụ: BOT G2 tự đặt bid dip lúc 3h sáng.
- MANUAL = người đặt tay theo lịch, chỉ book (+ dip đặt tay hẹn giờ), không cần bot [FINAL_REPORT_VI]. Ví dụ: sáng dậy đặt 2 lệnh book rồi tối chốt.

## Hai chân lệnh
- Book = lệnh theo xu hướng giữ theo nến 4h, có SL/TP [FINAL_REPORT_VI]. Ví dụ: book long BTC vì tín hiệu 4h tăng.
- Dip ladder / bậc dip / rung = thang lệnh mua khi giá sập sâu (bắt dao rơi có chia bậc), mỗi bậc (rung) là một lệnh nhỏ từ fill tới exit [BOT_RUNBOOK_VI]. Ví dụ: BTC rớt 2,5/3/3,5/4/5 sigma thì khớp dần 5 bậc.
- Flush = cú xả mạnh cả thị trường, giá rơi nhanh trong 1 nến [OWNER_SUMMARY_VI]. Ví dụ: FTX 11/2022 là một flush.
- Sigma (σ) = đơn vị đo độ rơi so với biến động thường [QUICKSTART_VI]. Ví dụ: rơi 2,5σ nghĩa là rơi sâu gấp 2,5 lần ngày thường.
- R2 depths = độ sâu cố định của thang dip: 2,5 / 3 / 3,5 / 4 / 5 sigma [FINAL_REPORT_VI]. Ví dụ: bậc nông nhất khớp khi rơi 2,5σ.
- B1 (correlation-aware sizing) = cách chia vốn dip theo tương quan: càng nhiều coin cùng sập thì mỗi lệnh càng nhỏ [FINAL_REPORT_VI]. Ví dụ: 1 coin sập mua đủ, 4 coin cùng sập thì mỗi coin mua ít lại.

## Tên bản triển khai
- D17BF / D13BF = bản dip x1,7 kèm bear-book; số 17/13 là độ sâu nhánh [FINAL_REPORT_VI]. Ví dụ: D17BF là bản deploy cũ 5,43%/tháng.
- G2 = bản BOT đang chạy: R2B1D17BF + trần an toàn dip 2x [QUICKSTART_VI]. Ví dụ: G2 đạt 5,41%/tháng, DD ~16,9.
- G2K20 = bản lợi nhuận cao nhất đạt chuẩn (~5,87%/tháng, DD ~17,8) nhưng không triển khai vì DD cao hơn [FINAL_REPORT_VI].
- R2-4P = thang dip R2 chạy trên 4 pha giờ (4 đồng hồ), không chạy 1 pha lẻ [FINAL_REPORT_VI].
- Phase / đồng hồ (4 clocks) = chia lệnh dip theo 4 mốc giờ lệch nhau để tránh may rủi một khung giờ [OWNER_SUMMARY_VI]. Ví dụ: chạy mix 4 pha thay vì 1 pha (pha đơn COVID -21,8% vượt ngưỡng).
- Gross cap 2x = trần an toàn: tổng lệnh dip chờ + đang mở không quá 2x vốn [QUICKSTART_VI]. Ví dụ: gap -10% cả 5 coin thì lỗ 33,5% thay vì 58%.
- Bear-book filter = khi thị trường gấu thì giảm nửa lệnh book mua [BOT_RUNBOOK_VI]. Ví dụ: bear thì book long chỉ đặt nửa size.

## Carry quý
- Carry (cash-and-carry quý) = mua coin thật + bán khống futures quý bằng nhau, ăn chênh giá khi đáo hạn [QUICKSTART_VI]. Ví dụ: mua 1 BTC spot + short 1 BTC quý Dec.
- f = tỉ lệ vốn cho mỗi chân carry [QUICKSTART_VI]. Ví dụ: f=0,25 nghĩa là mỗi chân 0,25x vốn (mua spot mỗi coin = 0,25x vốn; khi BTC và ETH cùng mở và các cặp chồng nhau lúc roll, tiền mặt dùng cho spot lên tới ~96% vốn — vì vậy không vượt f=0,25 [oc_utamargin]).
- Basis = chênh giá futures so với giá hiện tại, tính %/năm [QUICKSTART_VI]. Ví dụ: basis >= 4%/năm mới vào, ETH 3,7% thì bỏ qua.

## Tài khoản và lệnh sàn
- UTA = tài khoản hợp nhất Bybit: một vốn dùng chung cho mọi lệnh [BOT_RUNBOOK_VI]. Ví dụ: BOT + carry chung một UTA.
- Cross margin = vốn chung chịu lỗ chung (lệnh nào cũng trừ vào một ví) [BOT_RUNBOOK_VI]. Ví dụ: BTC lỗ thì ETH trong cùng ví cũng bị trừ.
- Hedge Mode = giữ lệnh mua và bán riêng, không triệt tiêu nhau [BOT_RUNBOOK_VI]. Ví dụ: vừa long vừa short BTC cùng lúc được.
- PostOnly = lệnh limit chỉ đứng chờ giá tới, không cướp giá (luôn phí maker rẻ) [BOT_RUNBOOK_VI]. Ví dụ: bị từ chối PostOnly thì thử lại sau, không đuổi giá.
- Maker / taker = maker là người đứng chờ (phí 0,02%), taker là người khớp ngay (phí 0,055%) [FINAL_REPORT_VI]. Ví dụ: entry/TP là maker, stop là taker.
- TP / SL / backstop = chốt lời / cắt lỗ / lưới an toàn cuối trên sàn [BOT_RUNBOOK_VI]. Ví dụ: TP limit +8σ, SL market, backstop chạm 8σ.
- Close5 stop = cắt lỗ khi nến 5 phút ĐÓNG vượt 4σ (thoát ở phút mở tiếp theo), khác backstop là cắt ngay khi giá chạm [BOT_RUNBOOK_VI]. Ví dụ: giá chạm nhẹ rồi hồi thì close5 không cắt oan.
- Time exit = tới giờ mà lệnh chưa lời thì thoát, không ôm mãi [FINAL_REPORT_VI]. Ví dụ: rung dip quá ~4h không về thì đóng.

## Đo lợi nhuận và rủi ro
- DD (drawdown) = mức sụt vốn từ đỉnh; DD năm = sụt tệ nhất trong từng năm, DD toàn đường = sụt tệ nhất trên cả đường 5 năm liên tục [FINAL_REPORT_VI]. Ví dụ: DD 16,9 nghĩa là từ đỉnh mất tối đa 16,9%.
- %/tháng geometric = lợi nhuận gộp trung bình mỗi tháng (lãi nhập gốc) [FINAL_REPORT_VI]. Ví dụ: 5,41%/tháng nghĩa là ~26x sau 5 năm.
- Walk-forward / anchor / năm giấu = giả vờ đứng ở một mốc (anchor), đóng băng mọi thứ rồi chạy thử 1 năm sau đó; năm gần nhất là năm giấu, chỉ chấm 1 lần cho bản cuối [FINAL_REPORT_VI]. Ví dụ: 5 anchor 2021–2025 là 5 bài thi riêng.
- Leakage = dùng trộm dữ liệu tương lai khi nghiên cứu (cấm tuyệt đối) [FINAL_REPORT_VI]. Ví dụ: lấy giá ngày mai để quyết lệnh hôm nay là leakage.
- Placebo gate = bài kiểm tra ngẫu nhiên: trộn/xáo dữ liệu, ý tưởng thật phải thắng hẳn may rủi mới giữ [FINAL_REPORT_VI].
- Ma sát S1–S5 = các kịch bản xấu: phí gấp đôi, trễ 15/30 phút, trượt stop, giá Bybit thật, phí stress [FINAL_REPORT_VI]. Ví dụ: G2 rớt S1/S3 nhưng vẫn dưới DD 20.

## Từ paper tới tiền thật
- Paper / testnet / live = paper là chạy giả bằng giá thật; testnet là sàn thử; live là tiền thật [QUICKSTART_VI]. Ví dụ: paper >= 8 tuần rồi testnet 7 ngày rồi mới live.
- Go-live gates = 4 điều kiện lên live: paper >= phân vị 20, DD paper <= 15%, lệch bot-plan <= 1,5 điểm, không lỗi nặng > 1 giờ [BOT_RUNBOOK_VI].
- Stop rules = quy tắc dừng: DD > 20% dừng mở mới, lỗ tháng > 10% giảm nửa vốn, phân vị < 5 sau 8 tuần thì dừng [BOT_RUNBOOK_VI].
- Edge monitor = 2 đèn vàng trong báo cáo hằng ngày: lãi 6 tháng < 1,61%/tháng hoặc tỉ lệ chốt lời dip < 0,434 thì điều tra [QUICKSTART_VI].
- OOS (ngoài mẫu) = dữ liệu sau 2026-09-23, chưa từng dùng khi nghiên cứu, là bằng chứng sạch [OWNER_SUMMARY_VI]. Ví dụ: 6 ngày đầu OOS G2 +2,0% là trong biên.
