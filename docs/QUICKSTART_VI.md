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
- Chân short quarterly của carry đặt đòn bẩy 10x (đã hedge bằng spot): margin trống thấp nhất 22,5% -> 32,7%; bắt buộc Cross margin; không vượt f=0,25 vì các cặp chồng nhau đã dùng ~96% USDT để mua spot (f lớn hơn phải vay USDT) [oc_utamargin2].
- Stretch D13BF+carry f=0,25 base 5,104/14,85 ĐẠT [oc_carryd13] nhưng ma sát rớt (chỉ base + S2 f=0,50 giữ) — không deploy [oc_carryfric];
MANUAL+carry tốt nhất 3,993 vẫn <5 — NO [oc_manualcarry]; plateau G2 giữ deploy [oc_plateau2]; 8-phase NO [oc_phase8]; screens expirydip/usdtdip
đóng (NO) [oc_expirydip; oc_usdtdip].
- Sau reboot: `bash scripts/restart_all.sh` (loop.sh retired), idempotent, backend local + 5 paper runner + vòng carry [restart_all.sh].
