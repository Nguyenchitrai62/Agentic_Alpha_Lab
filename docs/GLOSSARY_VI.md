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
- Basis threshold = ngưỡng basis năm hóa `ln(F/S)*365/DTE >= 4%` mới được mở cặp carry [carry_calendar.py]. Ví dụ: basis 5,2% thì vào, 3,7% thì SKIP.
- Delivery / settlement index = giá thanh toán futures quý là INDEX (trung bình giá spot trong cửa sổ), không phải một giá in lúc 08:00 [oc_deliverytrack]. Ví dụ: short futures chốt theo index nên spot cũng phải bán rải theo index mới khớp.
- Roll window = cửa sổ mở cặp kế tiếp khi hợp đồng front còn <= 7 ngày tới đáo hạn (và chỉ khi basis đạt ngưỡng) [carry_calendar.py]. Ví dụ: front còn 6 ngày thì được xét mở cặp quý kế tiếp.
- Slice sale (bán rải 6 lát) = bán chân spot chia 6 phần đều lúc 07:34/07:39/07:44/07:49/07:54/07:59 để bám index, lệch tối đa ~20bp thay vì ~90bp khi bán một lệnh [oc_deliverytrack]. Ví dụ: không bán một cục lúc 08:00 sau đêm biến động.

## Tài khoản và lệnh sàn
- UTA = tài khoản hợp nhất Bybit: một vốn dùng chung cho mọi lệnh [BOT_RUNBOOK_VI]. Ví dụ: BOT + carry chung một UTA.
- Cross margin = vốn chung chịu lỗ chung (lệnh nào cũng trừ vào một ví) [BOT_RUNBOOK_VI]. Ví dụ: BTC lỗ thì ETH trong cùng ví cũng bị trừ.
- Hedge Mode = giữ lệnh mua và bán riêng, không triệt tiêu nhau [BOT_RUNBOOK_VI]. Ví dụ: vừa long vừa short BTC cùng lúc được.
- PostOnly = lệnh limit chỉ đứng chờ giá tới, không cướp giá (luôn phí maker rẻ) [BOT_RUNBOOK_VI]. Ví dụ: bị từ chối PostOnly thì thử lại sau, không đuổi giá.
- Maker / taker = maker là người đứng chờ (phí 0,02%), taker là người khớp ngay (phí 0,055%) [FINAL_REPORT_VI]. Ví dụ: entry/TP là maker, stop là taker.
- TP / SL / backstop = chốt lời / cắt lỗ / lưới an toàn cuối trên sàn [BOT_RUNBOOK_VI]. Ví dụ: TP limit +8σ, SL market, backstop chạm 8σ.
- Close5 stop = cắt lỗ khi nến 5 phút ĐÓNG vượt 4σ (thoát ở phút mở tiếp theo), khác backstop là cắt ngay khi giá chạm [BOT_RUNBOOK_VI]. Ví dụ: giá chạm nhẹ rồi hồi thì close5 không cắt oan.
- Time exit = tới giờ mà lệnh chưa lời thì thoát, không ôm mãi [FINAL_REPORT_VI]. Ví dụ: rung dip quá ~4h không về thì đóng.
- UTA margin / IM = ký quỹ giữ lệnh trong ví Bybit UTA chung: IM perp = giá trị gộp G2 / 5, IM carry short / 10, spot không cần IM [oc_carrymargin]. Ví dụ: G2 + carry f=0,25 dùng tối đa ~67% vốn, vượt 95% là bị chặn.
- Haircut = phần trừ khi tính giá trị spot làm tài sản đảm bảo: BTC/ETH trừ 5% (stress 10%), tiền mặt mua spot tối đa ~95,8% vốn ở f=0,25 [oc_carrymargin]. Ví dụ: spot 1000 USDT chỉ tính ~950 USDT đảm bảo.
- Dust (lượng lẻ dưới min notional) = mảnh dip khớp quá nhỏ khiến TP/stop dưới sàn 5$ nên không đặt được bảo vệ, bot log `skipped_below_minimum` [BOT_SOAK_20261006]. Ví dụ: rung SOL sâu còn 0,1 SOL thì TP/stop bị sàn từ chối.

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

## Vận hành và kiểm thử
- Cycle = một vòng bot (đồng bộ, quyết lệnh, guard, đặt/hủy), mặc định ~20–25 giây [BOT_RUNBOOK_VI]. Ví dụ: cycle > 60 giây log `slow_cycle`, quá 5 phút không cycle mới là runner chết.
- Stale plan = plan backend quá 4h30m chưa tươi, bot chặn lệnh mới chỉ giữ stop/TP cũ [BOT_RUNBOOK_VI]. Ví dụ: thấy `stale_plan` thì dựng lại backend, không ép vào lệnh.
- Soak test = chạy replay tăng tốc (24h giá thật qua sàn giả) để soi invariant, không phải đo lợi nhuận [BOT_SOAK_20261006]. Ví dụ: soak2 chạy 4320 cycle, phát hiện lỗi dust không bảo vệ.
- Alert_watch --once = kiểm tra sức khỏe một lần không toast [BOT_RUNBOOK_VI]. Ví dụ: sau reboot chạy `--once --no-toast`, còn canh liên tục dùng `--every 300`.
- WMI detached start = cách dựng backend/runner tách khỏi terminal qua `Win32_Process.Create` nên không chết theo cửa sổ console [BOT_RUNBOOK_VI]. Ví dụ: từ 2026-10-06 chỉ dựng bằng `restart_all.ps1`, cấm chạy foreground rồi đóng cửa sổ.
