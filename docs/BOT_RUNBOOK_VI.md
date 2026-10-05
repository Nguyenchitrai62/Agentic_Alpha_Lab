# Sổ tay vận hành BOT khuyến nghị R2B1D17BF (cho chủ tài khoản)

> Bot gương lệnh (order-mirror) chạy pipeline R2B1D17BF (v411) trên Bybit USDT perps.
> Tài liệu chi tiết kỹ thuật: `docs/BOT_EXECUTION.md`, `docs/DEPLOYMENT_PLAN_VI.md`, code `bot/run.py`.
> Kỳ vọng trung thực và mọi ngưỡng go-live / dừng dưới đây lấy nguyên văn từ
> `docs/DEPLOYMENT_PLAN_VI.md` (đăng ký trước ngày 2026-10-05, không sửa sau khi thấy dữ liệu paper).

## 1. BOT này là gì, kỳ vọng bao nhiêu

- **Pipeline:** R2B1D17BF (v411) = book R2 + dip size theo tương quan `1/(1+n)` + dip x1.7 + bộ lọc gấu cho book long (BTC 4h open < trung bình 1200 nến).
- **Kỳ vọng trung thực (đo cân lại mỗi năm, phí Bybit, funding bất lợi):** ~**5.43 %/tháng**
  (giá Bybit + ma sát: 4.97; trễ 15 phút: 5.24). Năm xấu nhất DD 18.3, toàn đường cong 16.9,
  mọi kịch bản ma sát DD <= 20, tỉ lệ thắng ~65.5 %, không năm lỗ trong nghiên cứu.
- **Mục tiêu nền (>= 5 %/tháng, DD < 20 %, thắng > 55 %) đạt trên 5 năm dữ liệu nghiên cứu (đã audit),**
  nhưng mọi năm đều đã được xem nên bằng chứng sạch chỉ còn là paper prospective. BOT chỉ chạy tiền thật nhỏ khi đủ điều kiện mục 5.

## 2. Điều kiện tiên quyết (kiểm tra trước khi chạy)

1. **Backend chạy để có plan tươi:** bot chỉ gương theo
   `artifacts/research/advisor_shadow/trade_plan_v376.json` (backend làm tươi mỗi giờ).
   Backend tắt = plan cũ = bot chặn lệnh mới (xem mục 7).
2. **Sàn Bybit, chế độ Hedge Mode:** bot tự gọi `hedge_mode()` (long positionIdx 1, short 2).
   Nếu đã có vị thế mở hoặc đã ở hedge mode, bot ghi log `hedge_mode` rồi chạy tiếp.
3. **Khóa API trong `.env` (không bao giờ commit):**
   - testnet: `BYBIT_TESTNET_API_KEY` / `BYBIT_TESTNET_API_SECRET` (lấy ở testnet.bybit.com);
   - live: `BYBIT_API_KEY` / `BYBIT_API_SECRET` + `BOT_ALLOW_LIVE=yes-real-money` do chính chủ tài khoản đặt.
   - paper/dry: không cần khóa (paper khớp bằng giá Bybit live công khai).
4. **Vốn:** tối thiểu **~3000–5000 USDT** (`docs/DEPLOYMENT_PLAN_VI.md`).
   Dưới mức này các bậc dip BTC < 0.001 BTC bị bỏ qua do 4 khung giờ chia vốn làm 4
   (log `skipped_below_minimum`). Nghiên cứu chi tiết `research/diagnostics/oc_lots`:
   tại thời điểm viết sổ tay này **chưa tồn tại** — khi có, lấy cỡ tài khoản từ đó.
5. **Máy chạy 24/7, một runner cho mỗi mode** (khóa OS `artifacts/bot/<mode>/runner.lock`).
   Không mở 2 tiến trình cùng thư mục state.

## 3. Cách chạy: paper -> testnet -> live

Mọi lệnh chạy từ thư mục repo root. Máy Windows dùng `.venv/Scripts/python.exe`.

**a) Xem thử không gửi lệnh (dry run):**

```bat
.venv\Scripts\python.exe -m bot.run --once --equity 5000 --corr-size --dip-mult 1.7 --bear-book
```

Chỉ in ra các lệnh đáng lẽ đặt/hủy lúc này, không cần khóa API.

**b) Paper R2B1D17BF (đang là bằng chứng triển vọng duy nhất, bắt đầu 2026-10-05):**

```bat
.venv\Scripts\python.exe -m bot.run --mode paper --equity 5000 --corr-size --dip-mult 1.7 --bear-book --tag d17bf
```

- State: `artifacts/bot/paper_d17bf/state.json`, sổ lệnh `actions.jsonl`, tài khoản mô phỏng
  `exchange.json`, log `runner.log`. Vòng lặp mỗi 20 giây.
- Không dùng tag `d17bf` sẽ ghi đè lên paper R2-4P gốc (`artifacts/bot/paper/`) — đừng làm vậy.
- Lệnh paper gốc (R2-4P, không phải bản khuyến nghị) chỉ để tham khảo:
  `python -m bot.run --mode paper --equity 5000`.

**c) Testnet (tùy chọn, kiểm tra API thật, không mất tiền):**

```bat
.venv\Scripts\python.exe -m bot.run --mode testnet --corr-size --dip-mult 1.7 --bear-book --tag d17bf
```

Điền khóa testnet vào `.env` trước. Chạy vài ngày, xác nhận không còn lỗi `cycle_error`.

**d) Live (KHÓA — chỉ chủ tài khoản mở):**

```bat
set BOT_ALLOW_LIVE=yes-real-money
.venv\Scripts\python.exe -m bot.run --mode live --corr-size --dip-mult 1.7 --bear-book --tag d17bf
```

Bot từ chối nếu thiếu `BOT_ALLOW_LIVE=yes-real-money`. Chỉ chạy sau khi đủ cả 4 điều kiện
mục 5, bắt đầu vốn nhỏ. Mọi flag phải giữ nguyên `--corr-size --dip-mult 1.7 --bear-book`;
bỏ một flag là thành một pipeline khác, vô hiệu hóa mọi kỳ vọng ở mục 1.

Luật thực thi bot đang làm (giống engine nghiên cứu): entry book là limit GTC từ phút 5 sau
giờ phát plan tới `valid_until`, không khớp thì hủy (không đuổi); mỗi mảnh đã khớp có
stop market + TP limit reduce-only riêng (tự sửa khi plan dời SL/TP, ví dụ hòa vốn);
dip là bid limit từ phút 16 tới hết nến, TP limit + backstop native 8-sigma, cắt lỗ market
khi đóng nến 5m vượt 4-sigma, hết nến thoát market. Xem `docs/BOT_EXECUTION.md`.

## 4. Checklist theo dõi hằng ngày (5 phút)

1. **Plan có tươi không:** mở `trade_plan_v376.json` xem `generated_at`. Quá 2 giờ = plan cũ,
   bot chỉ giữ thoát lệnh (log `stale_plan`). Việc đầu tiên là dựng lại backend.
2. **Runner còn sống không:** mở `artifacts/bot/paper_d17bf/runner.log` (và thư mục mode
   đang chạy) tìm `cycle_error`, `error`, `stale_plan`, `plan_closed_divergence`,
   `skipped_below_minimum`, `bear_state`. Không được có `cycle_error` kéo dài > 1 giờ,
   không vị thế nào thiếu stop.
3. **So bot với plan:**
   `.venv\Scripts\python.exe scripts/paper_compare.py` — xem lợi nhuận, max DD, fills theo
   loại (book_entry/dip/tp/stop/market_exit), win rate mảnh đã đóng, và độ lệch bot so với plan.
4. **Bảng điểm triển vọng:**
   `.venv\Scripts\python.exe scripts/prospective_scorecard.py` — lợi nhuận paper nằm ở phân vị
   nào của bootstrap trung thực cùng số ngày (cột `percentile` cho `bot_paper_d17bf`).
5. **Chế độ gấu:** log `bear_state` báo BTC dưới trung bình dài hạn → book long mới vào/thêm
   bị giảm một nửa. Đây là hành vi dự kiến, không phải lỗi.

## 5. Quy tắc go-live và dừng (đăng ký trước, trích nguyên văn ý chính)

**Go-live tiền thật nhỏ — chỉ khi ĐỦ cả 4 điều kiện, đo trên bot giấy, sau tối thiểu 8 tuần:**

- (a) lợi nhuận bot giấy ở phân vị >= 20 của bootstrap trung thực cùng số ngày
  (`scripts/prospective_scorecard.py`);
- (b) DD bot giấy <= 15 %;
- (c) sai lệch bot giấy so với kế hoạch paper <= 1.5 điểm %/tháng;
- (d) không lỗi `cycle_error` kéo dài > 1 giờ, không vị thế nào thiếu stop.

Tăng vốn: sau 3 tháng tiền thật nếu (a)–(c) vẫn đúng trên tiền thật.

**Ngưỡng dừng (cả hai sản phẩm, tiền thật):**

- DD tài khoản > 20 %: dừng mở lệnh mới, chỉ giữ SL/TP; xem xét lại trước khi chạy tiếp.
- Lỗ một tháng > 10 %: giảm vốn dùng một nửa trong tháng kế tiếp.
- Phân vị lợi nhuận thực < 5 sau >= 8 tuần: dừng (mô hình không còn khớp nghiên cứu).

Không sửa các ngưỡng sau khi đã thấy dữ liệu paper (nếu sửa phải ghi rõ ngày và lý do).

## 6. Sau khi reboot / mất điện / mất mạng

1. Khởi động backend trước, xác nhận `trade_plan_v376.json` có `generated_at` mới (< 2 giờ).
2. Khởi động lại đúng một runner cho mỗi mode bằng lệnh mục 3 (đúng `--tag d17bf`).
   Nếu báo `another bot runner holds .../runner.lock` là còn tiến trình cũ — đừng chạy đè,
   kiểm tra Task Manager rồi mới mở lại.
3. Xem `actions.jsonl` + vị thế thật trên Bybit: sàn là sự thật. Bot tự đối chiếu fill qua
   `executions`, đặt lại stop/TP còn thiếu trong vòng <= 20 giây, và sau 3 phút sẽ đóng market
   mảnh nào plan đã thoát mà sàn còn mở (log `plan_closed_divergence`).
4. Không sửa tay `state.json` / `exchange.json` trừ khi hiểu rõ đang làm gì.

## 7. Sự cố thường gặp

- **Plan cũ (> 2 giờ):** log `stale_plan`; bot chặn entry mới, thoát lệnh vẫn chạy.
  Sửa backend, không ép bot vào lệnh.
- **Rate limit / lỗi mạng:** log `error` / `cycle_error`; vòng lặp tự sống tiếp.
  Stop/TP native đã nằm trên sàn tiếp tục bảo vệ vị thế mở. Nếu `cycle_error` > 1 giờ,
  dừng go-live, sửa rồi chạy lại paper/testnet.
- **Sập sàn / mất kết nối dài:** stop market và TP limit reduce-only đã đặt vẫn nằm trên sàn.
  Mảnh vừa khớp chưa kịp đặt exit (cửa sổ <= 20 giây) là phần hở duy nhất — kiểm tra tay sau
  khi mạng trở lại.
- **Lệnh bị bỏ do nhỏ:** log `skipped_below_minimum` (đặc biệt BTC ở tài khoản ~2000 USDT).
  Tăng vốn tới ngưỡng mục 2 thay vì cố nhồi lệnh.
- **Giá Bybit lệch Binance:** plan tính từ giá Binance (Bybit chênh ~2 bps, BNB ~10 bps rẻ hơn).
  Chênh nhỏ là dự kiến; độ lệch lớn và kéo dài xem ở `paper_compare.py`.
- **Điểm đã biết (2026-10-05):** `--bear-book` chỉ giảm một nửa entry/add long MỚI khi vào
  vùng gấu; engine nghiên cứu còn tỉa cả long đang mở — bot chưa làm việc này. Đừng kỳ vọng
  bot tự tỉa long cũ khi `bear_state` chuyển sang true.
