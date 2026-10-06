# QUICKSTART (VI) — từ 0 tới paper → testnet → live (một trang, 2026-10-06)

> Một trang cho chủ tài khoản. Chi tiết đầy đủ: `docs/BOT_RUNBOOK_VI.md` (vận hành), `docs/DEPLOYMENT_PLAN_VI.md` (kỳ vọng + go-live/dừng, đăng ký trước 2026-10-05), `docs/OWNER_SUMMARY_VI.md` (tóm tắt), `docs/FINAL_REPORT_VI.md` (báo cáo cuối), `docs/opencode/TESTNET_REVIEW_20261006.md` (sẵn sàng testnet).

## 1. Chạy gì (BOT G2 + carry quý, một Bybit UTA)

- BOT = book + thang dip, cần bot chạy 24/7 [BOT_RUNBOOK_VI]. Bản triển khai G2 = R2B1D17BF + trần dip 2x (v421/v422 twin numbers, v422 audited): `--corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0 --adopt-fresh --carry-f 0.25 --interval 25`, plan `trade_plan_v376.json` [FINAL_REPORT_VI].
- Cộng carry quý f=0,25 trên CÙNG MỘT Bybit UTA (tài khoản hợp nhất, một vốn chung) [DEPLOYMENT_PLAN_VI]. UTA: Cross margin (vốn chung chịu lỗ chung) + Hedge Mode (giữ long/short riêng) + đòn bẩy perps 5x cả 5 coin BTC/ETH/SOL/BNB/XRP [BOT_RUNBOOK_VI].
- Chân short quarterly của carry để 10x (đã hedge bằng spot mua bằng tiền thật) [oc_utamargin2]. Vượt f=0,25 phải tách vốn: f=0,50 bị chặn 1 giờ nên không dùng chung UTA [DEPLOYMENT_PLAN_VI].
- Vốn >= 5.000 USDT, tốt nhất ~10.000 USDT (5.000 đặt gần như mọi lệnh; 2.000 chỉ ~93–96% lệnh) [oc_capscale]. Lệnh PostOnly maker khi vào, stop là market, TP là limit; risk guard bật mặc định ở testnet/live [BOT_RUNBOOK_VI].

## 2. Kỳ vọng trung thực (khoảng, không phải một số)

- G2 backtest 5 năm: 5,41 %/tháng, năm tệ nhất 2,588 %/tháng, DD năm 16,91 / toàn đường 16,82 [FINAL_REPORT_VI]. Đồng hồ ngẫu nhiên chỉ ~5,24 thay vì 5,41 (triển khai may ~+0,17pp luck dip-clock, biên mỏng, method proxy) — đọc 5,41 kèm caveat này, phạm vi 4–6 %/tháng giữ nguyên [oc_clockluck].
- Carry f=0,25 cộng thêm khoảng +0,22 điểm %/tháng cho cả tài khoản (G2 5,41 -> 5,63, DD năm 16,75, toàn đường 16,66 khi lãi carry tái đầu tư [oc_carrycompound]; ước lượng bảo thủ +0,12 (ma sát base 5,533 so với G2 trần 5,41; rớt S1/S3) [oc_carryfric]. Giá Bybit thật thấp hơn Binance ~0,5pp/tháng, nằm ở chân book (không phải thang dip — dip gap nhỏ; không phải khớp lệnh book — phần còn lại do sizing/định giá) [oc_venuegap; oc_bookvenue; DEPLOYMENT_PLAN_VI].
- 49 cửa sổ 12 tháng trượt: min 2,73 / p10 3,25 / trung vị 4,89 / p90 8,88 / max 11,71 %/tháng; DD trung vị 13,5 (max 18,7); 100 % DD < 20, không cửa sổ lỗ [DEPLOYMENT_PLAN_VI].
- Bootstrap 10.000 năm: trung vị ~5,1 %/tháng; chỉ ~52 % năm >= 5 %; P(DD > 20 %) ~11 %; P(năm lỗ) ~0,7 %; vốn phải chịu được DD 25 % [DEPLOYMENT_PLAN_VI].
- KPI (G2, oc_kpi_g2): 41 % tháng >= +5 %, 70,5 % tháng không lỗ, chuỗi lỗ dài nhất 4 tháng; win book 51,5 % / dip 68,6 % / tất cả 65,3 % [DEPLOYMENT_PLAN_VI]. Tuần xấu G2 tệ nhất -12,3 % (hồi ~54 ngày); vài lần/năm mất 8–12 %/tuần, 1–4 tháng mới về đỉnh là bình thường [DEPLOYMENT_PLAN_VI].
- Cú sập nặng nhất cho thang dip là COVID 03/2020: mix 4 pha ~-16,1 %, pha đơn tệ nhất -21,8 % (vượt ngưỡng 20 % nên không bao giờ chạy 1 pha đơn) [oc_crash2020]. Gap -10 % cả 5 coin nhảy qua mọi stop: phút tệ nhất không trần lỗ 58 % vốn, trần 2x còn 33,5 % [DEPLOYMENT_PLAN_VI].

## 3. Mười bước paper → testnet → live

1. Cài đặt: clone repo, tạo `.venv`, cài deps; secrets chỉ trong `.env` local, không commit/không dán chat [BOT_RUNBOOK_VI].
2. Dựng backend trước: `.\run_backend.ps1 -Status` (chỉ `-Background` khi chưa chạy); plan `trade_plan_v376.json` phải tươi (< 4h30m) không thì bot chỉ giữ exits [BOT_RUNBOOK_VI].
3. Cài tay tài khoản Bybit: Cross + Hedge Mode + 5x từng coin (bot không tự làm); không hạ đòn bẩy khi đang có vị thế [BOT_RUNBOOK_VI].
4. Chạy thử khô: `.venv\Scripts\python.exe -m bot.run --once --equity 5000 --corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0 --adopt-fresh --carry-f 0.25 --interval 25` (không gửi lệnh) [BOT_RUNBOOK_VI].
5. Chạy paper combo đúng MỘT lệnh (G2 + carry 0,25): `.venv\Scripts\python.exe -m bot.run --mode paper --equity 5000 --corr-size --dip-mult 1.7 --dip-gross-cap 2.0 --bear-book --adopt-fresh --carry-f 0.25 --interval 25 --tag d17bfg2c` (>= 8 tuần; một runner/một thư mục state) [restart_all.sh].
6. Kiểm tra hằng ngày 5 phút: `scripts/daily_status.py` (gồm mục 6 edge monitor) → `scripts/bot_health.py artifacts/bot/paper_d17bfg2c` → `scripts/paper_report.py ...` → `scripts/prospective_scorecard.py` [BOT_RUNBOOK_VI].
7. Preflight chỉ-đọc trước testnet/live lần đầu: `.venv\Scripts\python.exe scripts/bot_preflight.py --mode testnet` rồi `--mode live` (exit 0 mới tiếp; kiểm tra key, Unified, Hedge, Cross, 5x từng coin, vốn) [BOT_RUNBOOK_VI].
8. Chạy testnet bắt buộc trước live: cùng flags paper nhưng `--mode testnet` vốn nhỏ, xác nhận Hedge/5x, lệnh vào PostOnly (`postonly_reject` = thử lại, không đuổi giá), risk guard bật, rate_limit ~ 0; checklist V1–V9 trong TESTNET_REVIEW [BOT_RUNBOOK_VI; TESTNET_REVIEW_20261006].
9. Go-live chỉ khi đủ cả 4 sau >= 8 tuần paper: (a) paper >= phân vị 20 bootstrap; (b) DD paper <= 15 %; (c) lệch bot vs plan <= 1,5pp/tháng (đủ 14 ngày mới kết luận, trước đó `too early`); (d) không cycle_error > 1h, không vị thế thiếu stop [DEPLOYMENT_PLAN_VI].
10. Live vốn nhỏ (chủ tài khoản mở `BOT_ALLOW_LIVE=yes-real-money`), tăng vốn sau 3 tháng live nếu (a)–(c) vẫn đúng; sau reboot/mất mạng: `bash scripts/restart_all.sh` (xem trước `--dry-run`; backend local 127.0.0.1:8724 rồi 5 paper runner rồi vòng carry), đối chiếu `actions.jsonl` với vị thế thật [BOT_RUNBOOK_VI].

## 4. Carry làm tay (~4 quyết định/năm, ~15 vé/năm)

- Khi hợp đồng front còn <= 7 ngày (hoặc lần đầu có hàng) thì xét hợp đồng quarterly KẾ TIẾP (chu kỳ Mar/Jun/Sep/Dec, thứ Sáu cuối tháng) [oc_carrycombo].
- Chỉ vào khi basis năm hóa ln(F/S)*365/DTE >= 4 %/năm (ETH skip ví dụ 3,7 %) [oc_carrycombo; PROSPECTIVE_20261006].
- Mỗi chân = 0,25 x vốn lúc vào (f=0,25): long spot + short quarterly notional bằng nhau, giữ tới delivery; drag phí ~0,275 % allocated [oc_carrycombo].
- Ngày đáo hạn: sell spot at 08:00 UTC delivery — bán chân spot đúng lúc giao hàng 08:00 UTC (tốt nhất chia nhỏ quanh cửa sổ tính giá index) để giá bán khớp giá thanh toán futures [carry_audit].
- Sổ paper riêng: `.venv\Scripts\python.exe scripts/carry_paper.py --once --equity 5000 --f 0.5 --tag carry` (sổ đo dùng f=0,5 tuyến tính theo f; triển khai dùng f=0,25) [carry_paper.py].

## 5. Quy tắc dừng + hai đèn vàng edge

- DD tài khoản > 20 %: dừng mở mới, chỉ giữ SL/TP; xem xét lại trước khi chạy tiếp [DEPLOYMENT_PLAN_VI].
- Lỗ một tháng > 10 %: halve (giảm nửa) vốn tháng sau [DEPLOYMENT_PLAN_VI].
- Phân vị lợi nhuận < 5 sau >= 8 tuần: dừng (mô hình không còn khớp nghiên cứu) [DEPLOYMENT_PLAN_VI].
- Đèn vàng edge (đã vào `daily_status.py` mục 6, vỡ = ĐIỀU TRA không tự đổi cấu hình): (1) trung bình 6 tháng < 1,61 %/tháng; (2) tỉ lệ chốt lời dip nửa năm < 0,434 (không decay: slope +0,067, CI chứa 0) [oc_edgedecay].

## 6. Bảo trì / mất điện / mất mạng

- Bảo trì CÓ hẹn: HỦY bid dip đang chờ từ trước giờ bắt đầu 30 phút tới hết giờ kết thúc (file `maintenance.json` hoặc flags `--maint-start/--maint-end` giờ UTC ISO); stop/TP/backstop và chân carry giữ nguyên trên sàn; tốn routine chỉ 1–2,5 % lãi dip [BOT_RUNBOOK_VI; oc_outage].
- Sau sự cố bất ngờ: ưu tiên xác nhận mọi vị thế mở còn stop/TP native trên sàn (`protection_check` + `bot_health.py` phải hết CRITICAL) rồi mới cho bot chạy tiếp; không đặt tay giờ đầu [BOT_RUNBOOK_VI; oc_outage].
- Mất mạng dài: stop market + TP limit reduce-only trên sàn vẫn bảo vệ; hở duy nhất là mảnh vừa khớp chưa kịp đặt exit (cửa sổ <= 20s) — kiểm tra tay khi mạng về [BOT_RUNBOOK_VI].

## 7. KHÔNG làm

- Không live khi chưa qua testnet sạch + đủ 4 điều kiện paper >= 8 tuần [DEPLOYMENT_PLAN_VI].
- Không chạy 2 runner cùng `--tag`/thư mục state (kẹt `runner.lock`); không sửa tay `state.json` (sàn là sự thật khi `qty_mismatch`) [BOT_RUNBOOK_VI].
- Không Isolated / one-way / đòn bẩy perps khác 5x cho bot; chân short carry giữ 10x hedge bằng spot; không vượt f=0,25 chung UTA; không hạ đòn bẩy khi đang có vị thế [BOT_RUNBOOK_VI; oc_utamargin2].
- Không bao giờ chạy 1 pha/1 đồng hồ đơn lẻ (pha đơn COVID -21,8 % vượt ngưỡng; mix ~-16 % nằm trong DD) [oc_crash2020].
- Không bơm size đuổi 8 %/tháng (biên max chỉ ~5,9 %/tháng ở DD > 17,5; edge/đơn vị bất biến) [oc_saturation]; không kỳ vọng 5 % mọi tháng (~1/9 năm chạm DD > 20 %) [DEPLOYMENT_PLAN_VI].
- Không commit `.env`/keys; không sửa ngưỡng go-live/dừng sau khi đã thấy dữ liệu paper (nếu sửa ghi ngày + lý do) [DEPLOYMENT_PLAN_VI].
