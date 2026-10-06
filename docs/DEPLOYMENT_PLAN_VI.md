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
   Kiểm tra hằng ngày bắt đầu bằng `python scripts/daily_status.py` (một trang: backend, tuổi plan, các bot, collector), rồi mới dùng `scripts/bot_health.py` soi chi tiết.
2. Testnet (tùy chọn): `--mode testnet` với khóa testnet trong `.env` để kiểm tra API thật (không ảnh hưởng tiền).
3. Tiền thật nhỏ: chỉ khi ĐỦ cả 4 điều kiện sau, đo trên bot giấy, sau tối thiểu 8 tuần:
   - (a) lợi nhuận bot giấy nằm ở phân vị >= 20 của phân phối bootstrap trung thực cho cùng số ngày (`scripts/prospective_scorecard.py`);
   - (b) DD bot giấy <= 15 %;
   - (c) sai lệch bot giấy so với kế hoạch paper <= 1.5 điểm %/tháng (đo chất lượng thực thi) — kiểm tra bằng `python scripts/paper_divergence.py <thư-mục-bot>` (trước 14 ngày báo `too early` là bình thường, đủ 14 ngày mới PASS/FAIL);
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

## 5. Cài đặt tài khoản Bybit (oc_margin, 2026-10-06; chi tiết runbook ở `docs/BOT_RUNBOOK_VI.md` mục 5)

- **Cross margin + Hedge Mode**, không dùng Isolated. Chỉnh đòn bẩy **5x trên cả 5 coin** BTC/ETH/SOL/BNB/XRP (Bybit chỉnh theo từng coin).
- Vì sao 5x (G2 `--dip-gross-cap 2.0`): **mức tối thiểu không bao giờ chặn lệnh** (IM = G/đòn bẩy <= 95% vốn mọi phút mở trong 5 năm; 3x đã chặn 22 phút mix / 31–45 phút mỗi phase). 10x/20x cũng không chặn nhưng không an toàn hơn trong cross mà chỉ làm lệnh nhầm tay to hơn — **giữ 5x**.
- Ở 5x: gross tối đa **~3,4x vốn** (không trần ~7,1x); IM tối đa **68% vốn**, thường chỉ ~7%; phút chật nhất vẫn còn >= 32% free. Thanh lý cần **sập tức thì -29% cả 5 coin** ở phút tệ nhất (thường ~300%, 99% số phút > 73–76%). Gap **-10% và -20% không phút nào cháy** trong 5 năm (0/65,1k phút; tệ nhất -10% mất ~34%, -20% mất ~68%). Sau gap kiểm tra tay; leverage bị reset thì dừng bot kiểm tra, **không tự hạ đòn bẩy khi đang có vị thế**.

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

## Chọn phiên bản có tổng quát không? (oc_wfselect) và bối cảnh hiện tại (oc_regimeexp)

Chọn walk-forward (mỗi năm chọn trong 31 biến thể chỉ bằng các năm trước) KHÔNG thắng việc luôn giữ R2B1D17BF (6,03 vs 6,08 %/tháng
trên 4 năm kiểm, LOO không ổn định) -> giữ cố định D17BF (+ trần 2x), không đổi cấu hình theo kết quả gần đây.
Bối cảnh 2026-09 (dữ liệu cuối): trên MA200, biến động thấp, xu hướng 90 ngày +35 %. Lịch sử nhóm này: 21 tháng, trung bình +8,1 %,
trung vị +5,0 %, 29 % tháng âm, tệ nhất -7,5 % (2024-01). Chỉ là bối cảnh, không phải dự báo.

## Tuần xấu trông thế nào (OpenCode oc_stresshist, D17BF + trần 2x)

Tuần tệ nhất lịch sử: 2023-12-27..2024-01-03 -12,3 % (DD 13,9 %, hồi lại sau ~54 ngày; không trần: -14,7 % / DD 16,3 %).
Các tuần xấu khác: 2025-10-10 -9,7 % (hồi ~134 ngày), 2024-07 -9,6 %, 2023-06 -8,6 %, 2024-06 -8,9 %; FTX 2022-11 -2,2 % (DD 9,2 %),
LUNA 2022-05 -3,0 % (DD 9,7 %). Hãy chuẩn bị tâm lý: vài lần mỗi năm mất 8-12 % trong một tuần và mất 1-4 tháng để về đỉnh cũ.

Dòng phụ funding thực (OpenCode oc_signedfunding; SỐ CHÍNH THỨC vẫn là mô hình gate: long trả 0,01 %/8h, short không nhận):
R2B1D17BF với funding thực có dấu 5,55 %/tháng, DD năm 18,32 (gate 5,43 / 18,33) -> mô hình gate bảo thủ hơn thực tế khoảng 0,1 %/tháng.

Chênh lệch sàn Bybit vs Binance (~0,5 %/tháng, oc_venuegap + oc_bookvenue): nằm ở thang dip (ít TP hơn trên băng giá Bybit), không ở book
(khớp/stop/TP gần như giống hệt). Không có lỗi thực thi để sửa; kỳ vọng triển khai trên Bybit dùng hàng "giá Bybit" (~4,9 %/tháng, DD < 20).

## Thời gian "dưới nước" (OpenCode oc_underwater, đường liên tục 5 năm)

G2 (D17BF + trần 2x): 47 lần sụt > 5 %; thời gian dưới đỉnh trung vị ~9 ngày, p90 ~63 ngày, dài nhất ~149 ngày (2022-07..12).
~29 % thời gian ở dưới đỉnh hơn 5 %, ~5 % thời gian dưới đỉnh hơn 10 %. Các đợt sâu nhất: 16,8 % (2023-04..07, 88 ngày), 14,7 %
(2024-01-03, 48 ngày), 13,8 % (2023-07..10, 109 ngày), 13,2 % (2022-07..12, 149 ngày). D13BF (thận trọng): 35 lần, dài nhất ~149 ngày.

## Trần dip của bot đã sửa khớp engine (OpenCode bot_capfix, cửa sổ 09/2026)

Cửa sổ dùng 2026-09-01..2026-09-23 (assignment 2026-08-01..09-23); baseline engine 0,0710 (+7,10%), dip 219 / book 83 fills.
Bản sửa: mỗi bid dip chờ = min(size thường, room), room = G x vốn sub − notional dip OPEN đã fill (KHÔNG trừ bid chờ khác),
tính lại mỗi cycle; bound cứng open + resting <= 2 x G x vốn sub; cap off giữ bit-for-bit. Có trần C_on (cap 2.0 + adopt on =
cấu hình triển khai): 0,0320 (eq 10320,27), gap −0,0390, dip 261, book 19. Không trần A_off: 0,0358 (eq 10357,95), gap −0,0352,
dip 271, book 18. Trần cũ: +1,12%, dip 209, gap −5,98pp. => FIXED (209→261 dip, 62,3→76,9 phí so với 80,7 không trần; +1,12%→+3,20%):
chỉ thua không trần 0,38pp (3,20% so với 3,58%), so với trần cũ tốn 2,46pp — tốn ~không như trần G2 engine. Code bot/mirror.py đã
sửa cục bộ (chưa commit); tới khi merge xong thì chạy KHÔNG trần hoặc chấp nhận lợi nhuận thấp hơn [bot_capfix].

## May mắn seed ở cấp danh mục (OpenCode oc_seedengine)

G2 (R2B1D17BFG2) chạy đủ engine 4-phase 5 năm với 5 bộ bảng R2 (S0 triển khai + 101/202/303/404, chốt trước outcome; S0 khớp
v376/tables_hidden exact cả 4 phase nên cache v421 chính là arm S0): 5y 5,343 (S303) / 5,371 (S101) / 5,382 (S404) / 5,410 (S0) /
5,430 (S202) %/tháng (TB 5,387, std 0,034, range 0,087; triển khai hạng 2/5, hơn TB +0,023); năm tệ nhất đồng nhất 2,588 cả 5 seed
(2021 zero-dispersion: fit train <10k rows nên split HGB không ngẫu nhiên); DD toàn đường 16,54..17,03 (TB 16,76, std 0,18),
max yearly DD 16,57..17,06; không seed nào có năm lỗ. Nếu may mắn seed không lặp lại, kỳ vọng ~5,39 %/tháng, worst ~2,59,
full-path DD ~16,8 (yearly-worst ~16,8) — tức bảng triển khai 5,41/2,59/16,8 trừ ~0,02 %/tháng luck; diagnostic, không chọn lọc
[oc_seedengine].

## Trượt stop thực tế (OpenCode oc_stopslip) — vì sao giữ trần gross

1699 stops G2 (773 book_stop + 926 rung_sl, exit 2021-10-27..2026-09-22; phủ 100% cả Binance và Bybit 1m, không hàng >= 2026-09-24).
Trung vị gộp −4,6 Binance / −1,6 Bybit (open kế tốt hơn stop; chỉ 45%/48% slip dương) trong khi S4 tính ~18–19 bps trung vị
(phân số −0,49/+0,09): S4 bảo thủ ở trung vị, xấp xỉ công bằng trong biến động kiểu 2021 (frac ~0,5..1,5) và vài ô BNB/ETH
2022–2024 (~0,6..1,5), nhưng quá nhỏ cho đuôi crash (p90 +146/+197, p99 +495/+738, max +813/+1347 bps). 7,2% stops thanh Bybit
không chạm stop suy từ Binance (venue wick khác nhau); flash 75,5%/74,7% (biên phút exit trung vị ~146 bps vs trailing ~16 bps).
Top-10 toàn stop long rung dip trong FTX 2022-11-09 (SOL, Bybit 1347 bps do venue gap) và flush 2024-01-03 (XRP). Hàm ý triển khai:
giữ `--dip-gross-cap 2.0` (phút tệ nhất gap −10% không trần lỗ 58% vốn, trần 2x còn 33,5%) vì stop không cắt được đuôi crash [oc_stopslip].

## Phí VIP (OpenCode oc_vipfees; triển khai giữ VIP0)

Repricing cộng từng bar trên G2 (57.365 legs; maker |w| 1741,9, taker 549,9): VIP1 (giả định maker 0,0180%/taker 0,0400%) +0,1117
→ 5,7183 %/tháng; VIP2 (0,0160%/0,0375%) +0,1590 → 5,7657 %/tháng (gốc 5,6066; net 5y 2539,21% → 2712,02% → 2788,60%;
+1,35%/năm và +1,92%/năm; saving TB 0,114%/0,163%/tháng); win/DD gần như không đổi. Nhưng tau = 22,98x vốn/tháng nên 5k chỉ
114.879/tháng (1,1%/0,5% ngưỡng 10M/25M, tiết kiệm 5,70/8,13 USDT), 10k 229.758 (2,3%/0,9%), 50k 1.148.790 (11,5%/4,6%); cần
~435.241 USDT cho VIP1 và ~1.088.101 USDT cho VIP2 chỉ bằng volume (đường asset ~$100k/$250k cũng ngoài tầm) — giữ phí VIP0 [oc_vipfees].

## Paper ngày đầu (OpenCode PAPER_DAY1_20261006, 2026-10-06 ~03:28 UTC)

5 thư mục (`paper`, `paper_d17bf`, `paper_d17bfg2`, `paper_g2k20`, `paper_d13bf`; không có bot thứ 6). daily_status WARNING duy nhất
do `paper` 15 lỗi rate-limit 10006 (06:00–12:01 10-05, runner-cụ thể); backend sống, plan tươi 0,5h (`2026-10-06T03:01:12Z`).
Equity/return/maxDD/dip-book: `paper` 4998,74/−0,03%/0,09%/0/6; ba bot d17bf/d17bfg2/g2k20 mỗi bot 4999,46/−0,01%/0,01%/0/4;
`d13bf` 4999,64/−0,01%/0,01%/0/3. Toàn book fill đúng giá limit, 0 dip fill, 0 exit, mọi piece có stop+TP, unprotected/qty_mismatch
none. Stale-plan đúng: 14:03–18:13 không fill nào giữa backend outage 12:39–17:40 (plan kẹt 12:03:26Z; stale 355/281/52/83),
sau ~18:13 bám lại; `skipped_below_minimum` 596–701 dòng/bot (vài rung BTC sâu dưới minimum ở 5000 — ồn erwart); không double-spend
(market_exit 0). Chưa kết luận go-live/divergence nào trước 14 ngày. Trước testnet: tách quota kline, báo động stale-plan sớm hơn,
gộp log skipped, dán nhãn "closest plan v376 R2-4P" cho bot khác cấu hình [PAPER_DAY1_20261006].

## Screens mới đóng đợt 2026-10-06 (mỗi hướng một dòng)

- oc_agentskip (SKIP khi cả hai nửa HGB y1.0 < −0,002): 2/5 sum, 4/5 DD — NOT PROMISING (2023–2025 loại toàn winner) [oc_agentskip].
- oc_b1wide (B1-wide +0,5*n_alt): sum>=97% 3/5, DD 0/5 (full 96,2%, DD 1,79→2,01) — NOT PROMISING [oc_b1wide].
- oc_bookfunding (x0,75 long khi funding 7d > p80): P&L>=97% 3/5, DD 3/5 (5y −8,8%) — NOT PROMISING [oc_bookfunding].
- oc_tpdecay (TP decay 1,0sg→0,5sg): sum 3/5, DD 1/5 (timeout 41%→31% nhưng full chỉ +1%) — NOT PROMISING [oc_tpdecay].
- oc_trendladder (depth x0,85 up / x1,15 down theo trend BTC r30): sum 3/5, DD 2/5 (2025 1,13→1,74) — NOT PROMISING [oc_trendladder].

## Vì sao chạy bốn đồng hồ (OpenCode oc_phasedisp) — quy tắc vận hành

R2B1D17BFG2 đơn lẻ phân tán 5 năm 3,102–6,923 %/tháng, DD toàn đường 16,91–43,55 % (phase0 6,923/16,91; phase1 4,834/22,46; phase2 5,592/20,07;
phase3 3,102/43,55; mix 5,410/16,82; năm tệ nhất đơn lẻ −2,431 %/tháng ở phase3 2023 trong khi mix vẫn +2,588 %/tháng và không năm nào lỗ;
DD năm tối đa đơn lẻ 16,91/22,46/20,07/43,23 so với mix 16,91) [oc_phasedisp]. Không đồng hồ nào thắng mọi năm nên mix 4 pha (mỗi pha 1/4 vốn
mỗi anchor, reproduce `v421_result.json` 5,41 / worst 2,588 / DD 16,91 / full 16,82) là cách khóa chênh lệch giờ [oc_phasedisp].
Quy tắc: không bao giờ chạy một pha đơn lẻ; backend + cả 4 runner phải sống (plan `trade_plan_v376.json` tươi < 4h30m, kiểm bằng
`daily_status.py` → `bot_health.py`); pha nào restart/thiếu phải khôi phục xong mới được tin các số mix [oc_phasedisp; BOT_RUNBOOK_VI].

## Độ nhạy blend 0,8/0,2 (OpenCode oc_blendsens) — giữ nguyên, không đổi

Screen vectorised open-to-open (`w(alpha)=alpha*o1+(1-alpha)*dmean`, bear v410 FIRST, cost 0,0005/unit, 10955 bars x 5 coin) [oc_blendsens]:
NOT a clean plateau (sensitivity, no selection) — bước cục bộ qua 0,8/0,2 trái dấu theo năm (E1/E2 same-sign 3/5, LOYO 2/5, không đạt 4/5+4/5)
và trung bình 0,0134 mỗi 0,1 alpha (>= ngưỡng 0,01 nên KHÔNG nhỏ); 2024 kéo về O1, 2025 kéo về D; deployed luôn interior không nhất/cuối năm nào;
worst week phẳng (<= 0,7pp mọi năm) [oc_blendsens]. Triển khai giữ nguyên 0,8/0,2, không tinh chỉnh theo năm gần nhất [oc_blendsens].

## PostOnly entries + risk guard (OpenCode bot_testnetfix, docs/BOT_EXECUTION.md CHANGES bot_testnetfix)

Triển khai testnet/live: book entries/adds + dip bids là PostOnly maker-only (đúng giả định fill research/`bot/paper.py`); chạm giá thì
`postonly_reject` và thử lại cycle sau cùng giá, không đuổi thành taker; TP/reduce GTC reduce-only, stops/market exits không đổi
[docs/BOT_EXECUTION.md CHANGES bot_testnetfix]. `risk_guard.check()` ON mặc định ở testnet/live (tắt bằng `--no-risk-guard`), OFF ở paper/dry
trừ khi `--risk-guard`; hạn per-coin 2,5x / dip 2,0x / total 4x / single 1x, từ chối log `risk_reject`, protection không bao giờ bị chặn
[docs/BOT_EXECUTION.md CHANGES bot_testnetfix]. QUICKSTART_VI bước 9: xác nhận Hedge/5x, lệnh vào PostOnly, guard bật, rate_limit ~ 0 trước live
[QUICKSTART_VI]. Paper giữ engine-faithful (không bật guard mặc định) để số paper so được với plan [BOT_EXECUTION.md CHANGES bot_testnetfix].

## Screens mới đóng đợt này (mỗi hướng một dòng, số y nguyên báo cáo)

- oc_expirybook (halving book x0,5 trong 48h trước expiry Deribit, ~6,6% bars): PROMISING 4/5 DD + 4/5 P&L>=98% (2021 fail cả hai; full P&L
2,061253→2,077167, DD 0,100471→0,090484) — hiệu ứng nhỏ parameter-free, chưa deploy, cần prospective [oc_expirybook].
- oc_expirycb (BOTH = expiry sau premium tilt, post-hoc): NOT PROMISING — P&L>base 4/5 nhưng DD<=base chỉ 1/5 (chỉ 2022 đỗ cả hai; full both 2,114578
cao nhất nhưng DD 0,089602 mất lợi expiry) — không deploy [oc_expirycb].
- oc_cbpremium (tilt long x1,15/x0,85 theo premium z ±1): NOT PROMISING — P&L 5/5 nhưng DD chỉ 2/5 (full 2,061253→2,102446, DD 0,100471→0,102295) —
return-only, không deploy [oc_cbpremium].
- oc_skewbook2 (gate long x0,75 khi skew_z90>q80 walk-forward 0,61–0,67): NOT PROMISING — P&L>=97% chỉ 1/5 (2025 0,976), DD 4/5 (full 2,061253→1,960521,
DD gần phẳng) — đóng [oc_skewbook2].
- oc_basisbook (long x0,5 khi basis impulse 7d<p20 walk-forward): NOT PROMISING — P&L 4/5 và DD 3/5 (2023 gãy cả hai: 96,7%, +0,07pp; full
2,061253→2,072244, DD 0,100471→0,098859) — đóng [oc_basisbook].
- oc_breadthbook (long x0,75 khi breadth==1,0, on 23,2%): NOT PROMISING — DD 5/5 nhưng P&L>=95% chỉ 2/5 (2024 bleed −13,6% khi on 42%; full
2,061253→1,923118) — đóng [oc_breadthbook].
- oc_breadthdip (dip x0,8 khi breadth==1,0, on-bars 2538/10956=23,2%): NOT PROMISING — DD 5/5 nhưng sum>=95% chỉ 1/5 (2025 99,6%; full 9,671→8,729,
90,3%) — giữ B1 full-size [oc_breadthdip].
- oc_bookholdcap (flat 1 bar sau 42 bars cùng dấu, 1,2–1,7% cells): NOT PROMISING — P&L>=97% 2/5, DD 2/5 (chỉ 2024 đỗ cả hai; full 1,970907→1,883804,
DD 0,104644→0,113519, cost +45%) — đóng [oc_bookholdcap].
## Screens mới đóng đợt này (mỗi hướng một dòng, số y nguyên báo cáo)

- oc_expirybook (halving book x0,5 trong 48h trước expiry Deribit, ~6,6% bars): PROMISING 4/5 DD + 4/5 P&L>=98% (2021 fail cả hai; full P&L
2,061253→2,077167, DD 0,100471→0,090484) — hiệu ứng nhỏ parameter-free, chưa deploy, cần prospective [oc_expirybook].
- oc_expirycb (BOTH = expiry sau premium tilt, post-hoc): NOT PROMISING — P&L>base 4/5 nhưng DD<=base chỉ 1/5 (chỉ 2022 đỗ cả hai; full both 2,114578
cao nhất nhưng DD 0,089602 mất lợi expiry) — không deploy [oc_expirycb].
- oc_cbpremium (tilt long x1,15/x0,85 theo premium z ±1): NOT PROMISING — P&L 5/5 nhưng DD chỉ 2/5 (full 2,061253→2,102446, DD 0,100471→0,102295) —
return-only, không deploy [oc_cbpremium].
- oc_skewbook2 (gate long x0,75 khi skew_z90>q80 walk-forward 0,61–0,67): NOT PROMISING — P&L>=97% chỉ 1/5 (2025 0,976), DD 4/5 (full 2,061253→1,960521,
DD gần phẳng) — đóng [oc_skewbook2].
- oc_basisbook (long x0,5 khi basis impulse 7d<p20 walk-forward): NOT PROMISING — P&L 4/5 và DD 3/5 (2023 gãy cả hai: 96,7%, +0,07pp; full
2,061253→2,072244, DD 0,100471→0,098859) — đóng [oc_basisbook].
- oc_breadthbook (long x0,75 khi breadth==1,0, on 23,2%): NOT PROMISING — DD 5/5 nhưng P&L>=95% chỉ 2/5 (2024 bleed −13,6% khi on 42%; full
2,061253→1,923118) — đóng [oc_breadthbook].
- oc_breadthdip (dip x0,8 khi breadth==1,0, on-bars 2538/10956=23,2%): NOT PROMISING — DD 5/5 nhưng sum>=95% chỉ 1/5 (2025 99,6%; full 9,671→8,729,
90,3%) — giữ B1 full-size [oc_breadthdip].
- oc_bookholdcap (flat 1 bar sau 42 bars cùng dấu, 1,2–1,7% cells): NOT PROMISING — P&L>=97% 2/5, DD 2/5 (chỉ 2024 đỗ cả hai; full 1,970907→1,883804,
DD 0,104644→0,113519, cost +45%) — đóng [oc_bookholdcap].
- oc_fomcbook (halving x0,5 quanh FOMC [R−24h,R+4h], 280/10955=2,56% bars): NOT PROMISING — DD 4/5 nhưng retention>=98% chỉ 2/5 (window lãi 3/5 năm nên
halving tốn 4–5% P&L; full 1,970907→1,928287, DD 0,104644→0,103597) — đóng [oc_fomcbook].

## Cash-and-carry trên vốn nhàn (OpenCode oc_cashcarry) — add-on, chưa cộng vào số triển khai

Triển khai gợi ý f=0.25 mỗi coin (spot + short quarterly bằng notional, ENTER iff basis năm hóa >=4%/yr, giữ tới delivery, drag phí 0.275%
allocated) theo đúng roll rule PLAN.md [oc_cashcarry]. Số vận hành: sum năm (allocated) 2021 0.0470 / 2022 0.0528 / 2023 0.2960 / 2024 0.1219 /
2025 0.0058 (BTC/ETH chi tiết: 2021 0.0261+0.0209 / 2022 0.0424+0.0105 / 2023 0.1579+0.1381 / 2024 0.0638+0.0581 / 2025 0.0058+0; mean basis
8.9/8.0, 5.6/5.7, 13.3/12.7, 7.4/7.4, 4.2/—%); worst MtM allocated -1.01/-0.71/-2.65/-0.39/-2.17% -> account f=0.25 tệ nhất -0.66% (2023),
f=0.50 -1.33%; gộp 5 năm +13.09% (f=0.25) = +0.218%/th số học (+0.213% hình học), f=0.50 +26.17% = +0.436% (+0.416% hình học); năm gần nhất
~+0.01%/th (1/6 cơ hội vượt filter) [oc_cashcarry]. Margin Bybit cross 5x Hedge: worst IM/equity 0.53/0.53/0.57/0.67 (f=0.25, s0..s3) và
0.55/0.55/0.60/0.72 (f=0.50), blocked 0/5 năm (limit 0.95; phút tệ nhất 2023-10-24 vẫn >=28% free) — mua bằng cash nhàn (median ~93% equity
free), không chạm margin BOT [oc_cashcarry; oc_margin]. PENDING: combo BOT+carry và khả dụng Bybit (oc_carrycombo) — tới khi xong thì chạy
carry paper riêng, không cộng +0.21%/th vào kỳ vọng G2 [oc_cashcarry].

## Quy tắc phương pháp mới (OpenCode oc_placebo, oc_placebo_dip, oc_premexpo, oc_usdt4p, oc_cmegap4p, oc_expiry4p)

Book ideas đi thẳng engine 4-phase: 3/3 vectorised book screens rớt full engine R2B1D17BFG2 (base 5.410 / 16.91 / 16.82) — EXP 5.498 nhưng 2021
-0.341 (rớt chân năm-tệ) [oc_expiry4p]; CME 5.424 nhưng full DD 17.03 (+0.21pp) và 2023 -0.416 (rớt 2 chân) [oc_cmegap4p]; USDT 5.168 (gap -0.242,
2024 -0.701, 2023 -0.421; DD 17.00 +0.18pp; rớt 3/4 chân) dù USDT là ALPHA vs exposure-matched control (gain +0.049084, pct 99.4)
[oc_premexpo; oc_usdt4p]; placebo cho thấy expiry-legs FPR 3.7% và CME-strict 0.2%/loose 2.4% (real CME pct 63.0/48.1 = typical null)
[oc_placebo]. Dip screens giữ chân DD và cộng gate placebo p95 +0.273 (pooled 300 rules FPR 6.7% -> 0.7% khi require full legs + dSum>=+0.273,
~3.5% base 7.718) [oc_placebo_dip]. Vận hành: không deploy tilt/halving nào (kể cả USDT ALPHA, expiry PROMISING vectorised) khi chưa PASS
engine 4-phase + paper; dip rule mới phải qua legs + p95 trước khi xin engine slot [oc_placebo; oc_placebo_dip].

## Mô hình book v427 C2 (OpenCode v427_c2_rank_calibrated, v427_audit COMPARISON) — pending, không đổi triển khai

Lần Kaggle đầu bug calibration (Platt label rank>0 base ~0.4 -> score p*2-1<0 gần luôn luôn -> mọi member short/flat mọi năm; dev 0.88%/th —
KHÔNG phải model result), đã fix centre trên calibration-fold base rate (pre-cutoff only), run buggy giữ làm C2-bug [v427_c2_rank_calibrated.py
PROCESS NOTE]. Audit mù v427_out: PASS (16 files x 2190 bars trong [anchor,anchor+365d); train 2022 A n=44338 cutoff 2022-09-17 last label end
2022-09-16 20:00<=cutoff, embargo 7d=42 bars +1-bar margin; feature recompute diffs 0.0/fp 4.44e-16; reproduction Spearman 1.0 diff 3.997e-15;
2025 sealed max 2025-09-23 20:00; majors-only; hashes khớp prereg) [v427_audit COMPARISON]. Fixed-run result pending — triển khai giữ D17BF+G2,
không chờ C2 [v427_c2_rank_calibrated.py; v427_audit COMPARISON].

## Anatomy phase-3 2023 để trực ca (OpenCode oc_clockanat) — mix sống nhờ dilution

Phase-3 2023 DD 43.23% (peak close 2024-01-03 11:00 1.3076 -> trough marked 2024-09-20 03:00 0.7424, drop -0.5649/1566 bars ~8.5 tháng, year end
0.7443 R -2.431%/th; split book -0.1317/dip -0.4332; exits 85 stop/326 TP/267 timeout 215 losers) là slow bleed + 3 cụm stop cascade (fills vài
phút trước cascade rồi stopped ngay: BTC 01-03 -717 bps, XRP 06-07 -979/-914/-849 bps trong 5 phút, BNB 04-13 -1103/-1028 bps, XRP 04-12 -1304 bps;
top-10 loss -0.7011 vượt year net nên +0.44 kiếm lại giữa episodes; mix cùng ngày -0.6129, lỗ 7/10 ngày; mix year end 2.02 so với phase-3 0.74)
[oc_clockanat]. Hàm ý trực: DD gate tới từ grind đồng bộ (không phải một crash để hedge), mix 4 pha là cách khóa chênh lệch giờ — pha nào
restart/thiếu phải khôi phục xong mới tin số mix; kỳ vọng vài lần mỗi năm mất 8-12%/tuần và 1-4 tháng về đỉnh [oc_clockanat; oc_stresshist].

## Screens đóng đợt này — mỗi hướng một dòng, không đổi triển khai (số y nguyên báo cáo)

- oc_fillttl: T240 3/1/1 + T120 3/2/2 (sum/DD/disp) — NOT PROMISING, giữ time exit theo đồng hồ 4h (win cao hơn nhưng sums thua 2021/2025, tails tệ
hơn) [oc_fillttl].
- oc_stoptf: S15 sums 4/5 nhưng DD 2/5 (+0.100/+0.027/+0.047; 2021-12-04 -3.68 so với -2.87) / S1 DD 5/5 nhưng sums 2/5 — NOT PROMISING, giữ close5
stop [oc_stoptf].
- oc_seasondepth: sum 1/5 (chỉ 2022) + DD 1/5 (chỉ 2024) — NOT PROMISING, giữ sigma_4h [oc_seasondepth].
- oc_rearm: V1 sum 3/5 nhưng DD 0/5 (tệ mọi năm +0.13..+0.21; re-armed win 69.0% nhưng short-gamma 2021 -0.96x/2022 -0.26x rule total) — NOT
PROMISING, giữ once-per-bar rung [oc_rearm].
- oc_usdtprem: P&L 4/5 nhưng DD 2/5 (full +0.091 nhưng 2023-2025 DD +0.0001/+0.0037/+0.0028) — NOT PROMISING, không tilt inflow [oc_usdtprem].
- oc_premexpo: USDT ALPHA (+0.049084, pct 99.4) / CB EXPOSURE (+0.035170, pct 88.2) / COMBINED ALPHA (+0.042640, pct 97.2) — nhưng ALPHA vẫn NO ở
engine, không deploy [oc_premexpo; oc_usdt4p].
- oc_usdt4p / oc_cmegap4p / oc_expiry4p: cả ba VERDICT NO (USDT -0.242 + DD +0.18pp; CME +0.014 nhưng DD +0.21pp + 2023 -0.416; EXP +0.088/DD -0.29pp
nhưng 2021 -0.341) — không deploy tilt/halving nào [oc_usdt4p; oc_cmegap4p; oc_expiry4p].
- oc_placebo / oc_placebo_dip: FPR book-legs 3.7%/0.2%/2.4% -> joint tails FPR 0.2%/0.0% (không real nào pass) / dip pooled 6.7% -> +p95 gate 0.7% —
áp làm gate từ nay [oc_placebo; oc_placebo_dip].
- oc_liqhist: UM liquidationSnapshot trống cả 5 symbols (0 files/rows) — USABLE NO; COIN-M sai margin + dừng 2023-06..2024-10; alternatives chỉ
recent-only/proxy/OI — không feature liq lịch sử cho 2021-2026 [oc_liqhist].

## Triển khai khuyến nghị hiện tại docs_update5 (2026-10-06): G2 + carry f=0.25 một UTA

KHUYẾN NGHỊ: BOT G2 (R2B1D17BF + `--dip-gross-cap 2.0`, v421: 5,41 %/tháng, worst 2,588, maxDD 16,91, full 16,82) + sleeve cash-and-carry quý f=0,25 trên
CÙNG MỘT Bybit UTA (cross, hedge, 5x cả 5 coin) [oc_carrycombo; oc_utamargin].
Số base hai quy ước (ghi cả hai cho trung thực): roll-only rebalance (vận hành thật) G2+carry f=0,25: 5,413 / 2,647 / 16,78 / full marked 16,34
(close 15,60); f=0,50: 5,418 / 2,705 / 16,65 / 15,86 [oc_carrycombo]; year-start rebalance G2+carry f=0,25: 5,533 / 2,736 / 16,78; f=0,50: 5,654 /
2,881 / 16,64 (lift cao hơn, KHÔNG dùng làm kỳ vọng) [oc_carryfric]. Caveat: overlay cần tới 2f cash EXTRA (f=0,25 -> 1,5x funded), R tính trên base
equity [oc_carrycombo].
Dưới ma sát (`oc_carryfric`): G2+carry f=0,25: base 5,533; S1 4,696; S2 5,339; S3 4,717; S4 5,033; S5 5,016 (f=0,50: 5,654 / 4,820 / 5,463 / 4,853 /
5,166 / 5,147) — giữ >=5,0 ở base/S2/S4/S5, RỚT S1 và S3 kể cả f=0,50 (4,820 / 4,853); sleeve chỉ +0,12–0,15pp (f=0,25), bớt DD 0,1–0,3pp, không năm lỗ
[oc_carryfric].
Margin một UTA (`oc_utamargin`): f=0,25 free min 22,49% / IM max 77,51% / 0 blocked / 0 MM breach / gap −10% −28,85% không liq — CLEAR; f=0,50 free min
1,85% / IM 98,15% / 1 giờ blocked 2025-09-25 18:00 / spot cost 179,9% (thiếu USDT) — KHÔNG clear, trên 0,25 tách vốn [oc_utamargin].
Khả dụng Bybit (`oc_carrycombo` §3; `bybitq`): linear Trading BTCUSDT-25DEC26 / 26MAR27 / 25JUN27 (cả ETH) + inverse Trading BTCUSDZ26 / BTCUSDH27 /
ETHUSDZ26 / ETHUSDH27, deliveryFeeRate 0, fundingInterval 0, phí đúng gate/carry (taker 0,055%/maker 0,02%, spot 0,1%), collateral spot 95%;
yield inverse ≈ Binance (−5%: +0,4973/23 trades so với +0,5234/25; f=0,25 +0,207% số học/+0,202% hình học so với +0,218/+0,213) [bybitq; oc_carrycombo].
Bước chủ tài khoản (quy tắc đóng băng `oc_cashcarry` PLAN + `carry_paper.py` docstring): xếp quarterly tăng dần; khi front còn <=7 ngày hoặc lần đầu có
hàng thì xét hợp đồng KẾ TIẾP (chu kỳ Mar/Jun/Sep/Dec thứ Sáu cuối tháng); basis năm hóa ln(F/S)*365/DTE >=4%/năm mới vào (ETH skip vd 3,7%
[PROSPECTIVE_20261006]); mỗi chân = f x vốn lúc vào (f=0,25), long spot + short quarterly notional bằng nhau, giữ tới delivery, drag phí 0,275%
allocated; ~4 quyết định/năm ≈ 15 vé tay/năm [oc_carrycombo; oc_manualcarry]. Sổ paper:
`.venv\\Scripts\\python.exe scripts/carry_paper.py --once --equity 5000 --f 0.5 --tag carry` (public REST only, state `artifacts/bot/paper_carry/`,
sha256 in đầu run) [carry_paper.py]; paper thực 10-06 f=0,5 BTC-25DEC26 entered basis +5,42%, ETH skip, alloc −0,15% quá sớm [PROSPECTIVE_20261006].
Stretch DD<15: D13BF+carry f=0,25 base 5,104/14,85 (f=0,50 5,234/14,71) ĐẠT cả 4 bar [oc_carryd13] NHƯNG dưới ma sát chỉ còn base + S2 f=0,50
(5,062/14,80); S1/S3/S4/S5 kể cả f=0,50 đều rớt (tốt nhất 4,845/15,82) — báo cáo trung thực, không deploy stretch [oc_carryfric].
MANUAL+carry vẫn <5: M5_human+carry f=0,50 tốt nhất 3,993 (equity-level 3,765), thiếu ~1,0–1,2pp; G15/G10/humanBF/top2 đều rớt return hoặc DD —
verdict NO [oc_manualcarry].
G2 plateau: ref 5,410/2,588/16,91/16,82; TP08 5,183/15,84/15,82; TP12 5,482/18,19/18,08; SL35 5,324/17,15; SL45 5,394/16,80; G175 5,503/16,74;
G225 5,252/16,87 — trong 0,3%/tháng + 1,5pp fullDD cả hai phía, giữ nguyên deploy [oc_plateau2]. 8-phase: mix 8 đồng hồ 4,960/17,98/17,32 so với
4-phase 5,410/16,91/16,82 (−0,45pp return, +0,5pp DD; BTC 47–60% lệnh dưới minimum ở 1250/clock) — NO [oc_phase8].
Restart sau reboot: `bash scripts/restart_all.sh` (`--dry-run`, `--only bots|backend|carry`), idempotent, backend local 127.0.0.1:8724 chờ plan <1h15m,
loop.sh RETIRED 2026-09-30, 5 runner paper theo runner.lock + state.json backup, vòng carry mỗi 3600s, KHÔNG live/testnet [restart_all.sh].
Screens đóng: oc_expirydip NOT PROMISING (dSum +0,0164 vs gate +0,273, 24 fills) [oc_expirydip]; oc_usdtdip NOT PROMISING (+0,047, 3/5 sums, 3/5
control) [oc_usdtdip].
