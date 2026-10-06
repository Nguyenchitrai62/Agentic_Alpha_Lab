# QUICKSTART (VI) — từ 0 tới paper → testnet → live

> Một trang cho chủ tài khoản. Chi tiết đầy đủ:
> `docs/BOT_RUNBOOK_VI.md` (vận hành), `docs/DEPLOYMENT_PLAN_VI.md` (kỳ vọng + go-live/dừng, đăng ký trước 2026-10-05),
> `docs/FINAL_REPORT_VI.md` (báo cáo cuối 2026-10-06), `docs/opencode/TESTNET_REVIEW_20261006.md` (sẵn sàng testnet).

## 1. Hệ thống là gì

- **BOT = book + thang dip** (cần bot chạy 24/7). MANUAL (chỉ book + dip đặt tay) là sản phẩm riêng, chưa đạt base (~3,7 %/tháng).
- Cấu hình triển khai: **R2B1D17BF (v411) + trần dip 2x = G2 (v421)**: `--corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0`, plan `trade_plan_v376.json`.
- Bybit USDT perps, **Cross margin + Hedge Mode, đòn bẩy 5x cả 5 coin** BTC/ETH/SOL/BNB/XRP. Vốn **>= 5000 USDT, tốt nhất ~10000**.
- Kỳ vọng trung thực (nguồn trong ngoặc): **trung vị ~5 %/tháng, năm xấu ~3 %/tháng, DD tới ~18 %** (`BOT_RUNBOOK_VI` mục 6).
  - 5 năm gate: 5,43 %/tháng; giá Bybit thật ~4,97; G2 5,41, DD năm 16,9 / toàn đường 16,8 (`DEPLOYMENT_PLAN_VI` mục 1; `FINAL_REPORT_VI` mục 1–2).
  - 49 cửa sổ 12 tháng trượt: trung vị 4,89 (min 2,73 / p10 3,25 / max 11,71), DD trung vị 13,5, 100 % DD < 20, không cửa sổ lỗ.
  - Bootstrap 10.000 năm: trung vị ~5,1 %/tháng, chỉ ~52 % năm >= 5 %; P(DD > 20 %) ~11 %, P(năm lỗ) ~0,7 %. Vốn phải chịu được DD 25 %.
  - KPI: 41 % tháng >= +5 %, 72 % tháng không lỗ; win book 51,5 % / dip 68,7 % / tất cả 65,5 %.
  - Vì sao trần 2x: gap -10 % cả 5 coin nhảy qua mọi stop — phút tệ nhất không trần lỗ 58 % vốn, trần 2x còn 33,5 %; lợi nhuận giữ nguyên.

## 2. Mười bước từ 0 tới live

1. Cài đặt: clone repo, tạo `.venv`, cài deps. Không đặt secrets vào chat hay commit.
2. Dựng **backend trước**: `.\run_backend.ps1 -Status` (chỉ `-Background` khi chưa chạy). Plan `artifacts/research/advisor_shadow/trade_plan_v376.json` phải tươi (< 4h30m), không thì bot chỉ giữ exits.
3. Cài đặt **tài khoản Bybit bằng tay** (bot KHÔNG tự làm): **Cross + Hedge Mode + 5x từng coin** BTC/ETH/SOL/BNB/XRP. Không hạ đòn bẩy khi đang có vị thế.
4. Keys **chỉ trong `.env` local**: testnet `BYBIT_TESTNET_API_KEY/_SECRET`; xác nhận `BOT_ALLOW_LIVE` chưa set. Không commit `.env`.
5. Chạy thử khô: `.venv\Scripts\python.exe -m bot.run --once --equity 5000 --corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0`. Không gửi lệnh.
6. Chạy **paper >= 8 tuần**: `... -m bot.run --mode paper --equity 5000 --corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0 --tag d17bfg2`. Một runner / một thư mục state.
7. Kiểm tra **hằng ngày 5 phút**: `scripts/daily_status.py` → `scripts/bot_health.py artifacts/bot/paper_d17bfg2` → `scripts/paper_report.py ...` → `scripts/prospective_scorecard.py`. CRITICAL khi `unprotected`/`qty_mismatch`/cycle chết/cycle_error > 1h.
8. Go-live chỉ khi **đủ cả 4 sau >= 8 tuần paper**: (a) paper >= phân vị 20 bootstrap; (b) DD paper <= 15 %; (c) lệch bot vs plan <= 1,5pp/tháng (`paper_divergence.py`, đủ 14 ngày mới kết luận); (d) không cycle_error > 1h, không vị thế thiếu stop.
9. Chạy **testnet** (bắt buộc trước live): `... -m bot.run --mode testnet --corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0 --tag d17bfg2`, vốn nhỏ, xác nhận Hedge/5x, lệnh vào là PostOnly (maker; `postonly_reject` = thử lại, không đuổi giá), risk guard bật mặc định (`risk_reject` trong log), rate_limit ~ 0. Xem checklist V1–V9 trong `TESTNET_REVIEW_20261006`.
10. **Live vốn nhỏ** (chủ tài khoản mở khóa `BOT_ALLOW_LIVE=yes-real-money`), tăng vốn sau 3 tháng live nếu (a)–(c) vẫn đúng. Sau reboot/mất mạng: backend trước, rồi từng runner đúng tag, đối chiếu `actions.jsonl` với vị thế thật.

## 3. Quy tắc dừng (tiền thật, từ `DEPLOYMENT_PLAN_VI` mục 4)

- **DD tài khoản > 20 %**: dừng mở mới, chỉ giữ SL/TP; xem xét lại trước khi chạy tiếp.
- **Lỗ một tháng > 10 %**: halve vốn tháng sau.
- **Phân vị lợi nhuận < 5 sau >= 8 tuần**: dừng (mô hình không còn khớp nghiên cứu).

## 4. KHÔNG làm

- Không live khi chưa qua testnet sạch + đủ 4 điều kiện paper.
- Không sửa tay `state.json`; sàn là sự thật khi lệch (`qty_mismatch`).
- Không chạy 2 runner cùng `--tag`/thư mục state (kẹt `runner.lock`).
- Không dùng Isolated / one-way / đòn bẩy khác 5x cho bot; không hạ đòn bẩy khi đang có vị thế.
- Không commit `.env`, keys, hay dán vào chat; không sửa ngưỡng go-live/dừng sau khi đã thấy dữ liệu paper (nếu sửa ghi ngày + lý do).
- Không kỳ vọng 5 % mọi tháng: ~1/9 năm có thể chạm DD > 20 %; tuần xấu -8 – -12 % vài lần/năm, 1–4 tháng mới về đỉnh cũ là bình thường.

## 5. Triển khai khuyến nghị docs_update5 (2026-10-06): G2 + carry một UTA

- Cấu hình: BOT G2 (`--corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0`, 5,41 %/tháng) + carry quý f=0,25 cùng một UTA cross/hedge/5x
(roll-only f=0,25: 5,413/full 16,34 [oc_carrycombo]; ma sát year-start f=0,25: base 5,533 / S1 4,696 / S2 5,339 / S3 4,717 / S4 5,033 / S5 5,016
[oc_carryfric]; f=0,25 CLEAR margin, f=0,50 blocked 1 giờ — trên 0,25 tách vốn [oc_utamargin]; Bybit inverse Z26/H27 + linear 25DEC26 yield ≈
Binance −5% [bybitq; oc_carrycombo]).
- Carry tay 4 quyết định/năm: quarterly kế tiếp khi front còn <=7 ngày, basis ln(F/S)*365/DTE >=4%/năm, mỗi chân f x vốn (f=0,25), long spot + short
quarterly bằng nhau giữ tới delivery (≈15 vé/năm); sổ paper `scripts/carry_paper.py --once --equity 5000 --f 0.5 --tag carry` [carry_paper.py] (sổ paper chạy f=0,5 chỉ để đo; lãi/lỗ carry tỉ lệ tuyến tính theo f, khi triển khai dùng f=0,25).
- Ngày đáo hạn: bán chân spot đúng lúc giao hàng (08:00 UTC, tốt nhất chia nhỏ quanh cửa sổ tính giá index) để giá bán khớp giá thanh toán của futures; lệch giờ bán ở giờ biến động có thể lệch vài % [carry_audit, leader adjudication].
- Chân short quarterly của carry đặt đòn bẩy 10x (đã hedge bằng spot): margin trống thấp nhất 22,5% -> 32,7%; bắt buộc Cross margin; không vượt f=0,25 vì các cặp chồng nhau đã dùng ~96% USDT để mua spot (f lớn hơn phải vay USDT) [oc_utamargin2].
- Stretch D13BF+carry f=0,25 base 5,104/14,85 ĐẠT [oc_carryd13] nhưng ma sát rớt (chỉ base + S2 f=0,50 giữ) — không deploy [oc_carryfric];
MANUAL+carry tốt nhất 3,993 vẫn <5 — NO [oc_manualcarry]; plateau G2 giữ deploy [oc_plateau2]; 8-phase NO [oc_phase8]; screens expirydip/usdtdip
đóng (NO) [oc_expirydip; oc_usdtdip].
- Sau reboot: `bash scripts/restart_all.sh` (loop.sh retired), idempotent, backend local + 5 paper runner + vòng carry [restart_all.sh].

## 6. Bổ sung docs_update6 (2026-10-06)

- May mắn đồng hồ (`oc_clockluck`): bốn đồng hồ giờ triển khai may ở sleeve dip — kỳ vọng đồng hồ ngẫu nhiên ~5,24 %/tháng thay vì 5,41 deployed
(24 offset S min 4,55/max 9,67/mean 7,12; deployed 0=9,67 pct 100%/60=7,54/120=8,76/180=4,90; mean 7,72 vs 7,12 gap −0,59; gap 2023 −0,42 + 2025 −0,15;
adjusted yearly 2,593/3,233/5,453/10,691/4,401) — giữ số cũ 5,41 kèm giải thích ~0,17pp luck, biên mỏng, proxy; nửa giờ kém cấu trúc nên giữ mix 4 pha
[oc_clockluck]. Kỳ vọng mục 1 đọc là ~5,24 (proxy) thay vì 5,41, phạm vi 4–6% giữ nguyên kèm caveat này.
- Carry: short quarterly 10x (hedge bằng spot; f=0,25 free 22,49%→32,67%, bắt buộc Cross), trần một UTA f=0,25; f=0,375 @10x chỉ nếu chấp nhận borrow
(spot peak 139%); f=0,50 không clear mọi đòn bẩy [oc_utamargin2]. FAR thắng 4/5 năm nhưng là exposure không phải rate — KHÔNG adopt, giữ base
next-quarterly f=0,25; hướng carry ĐÓNG 2/2 [oc_carryfar Leader decision].
- Vốn (`oc_capscale`): >=5.000 USDT đặt gần như mọi lệnh (book 0,9990/0,9995; dip 0,9780/0,9985/0,9967); 2.000 USDT ~93–96% count (book 0,9585/0,9704;
dip 0,9269/0,9950/0,9804; bottleneck BTC/ETH) [oc_capscale].
- Paper `paper_d17bfg2c` (G2 + carry 0,25) started 2026-10-06 07:19 UTC (BTCUSDT-25DEC26 f=0,25 basis ~5,31%, `--carry-f 0.25`); caveat: carry orders
trong paper bị generic diff hủy ngày 2026-10-06, fix đang làm [artifacts/bot/paper_d17bfg2c; docs/BOT_EXECUTION.md].
- Đóng hôm nay: oc_linvinv 0 vào NOT USEFUL [oc_linvinv]; oc_marktrig sum 4/5 nhưng DD/worst 2/5 NOT PROMISING [oc_marktrig]; oc_discsniper 0/5 năm
(5y −0,5291, placebo 13,3) NOT PROMISING [oc_discsniper]; oc_manual2coin 3,73 vs 3,24 vs 3,39/24,3 FAIL — cả ba NO [oc_manual2coin]; oc_phase8 8-phase
4,960 vs 4-phase 5,410 NO [oc_phase8].
