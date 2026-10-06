# Sổ tay vận hành BOT khuyến nghị R2B1D17BF + trần dip (cho người vận hành)

> Bot gương lệnh chạy pipeline R2B1D17BF (v411) trên Bybit USDT perps, Hedge Mode.
> Kỳ vọng, ngưỡng go-live/dừng lấy nguyên văn từ `docs/DEPLOYMENT_PLAN_VI.md`
> (đăng ký trước 2026-10-05, không sửa sau khi thấy dữ liệu paper).
> Chi tiết kỹ thuật: `docs/BOT_EXECUTION.md`, code `bot/run.py`.

> **CẢNH BÁO 2026-10-06:** phép đối chiếu bot-vs-engine (research/diagnostics/bot_parity_adopt) cho thấy cách bot cài
> `--dip-gross-cap` hiện CHẶT HƠN engine (tính cả lệnh dip đang chờ, chia phòng tích lũy) -> tháng 9/2026 bot có trần chỉ +1,1 % so với
> +3,6 % không trần. Đang sửa cho khớp engine (bot_capfix). Cho tới khi sửa xong: chạy KHÔNG có `--dip-gross-cap` hoặc chấp nhận lợi nhuận thấp hơn.

## 1. Lệnh khuyến nghị (R2B1D17BF + trần an toàn)

Mọi lệnh chạy từ thư mục repo root. Windows dùng `.venv\Scripts\python.exe`.

- (A) KHUYẾN NGHỊ cho tới khi bản bot_capfix được merge và `docs/BOT_EXECUTION.md` xác nhận cap khớp engine: BỎ `--dip-gross-cap` (xem CẢNH BÁO đầu sổ tay).
- (B) Chỉ dùng khi cap đã khớp engine: THÊM `--dip-gross-cap 2.0` vào cùng lệnh.
- Paper bot `d17bfg2` hiện đang chạy (B) — runner so sánh có trần, không dùng để kết luận lợi nhuận.

```bat
REM (A) Xem thử KHUYẾN NGHỊ, không gửi lệnh:
.venv\Scripts\python.exe -m bot.run --once --equity 5000 --corr-size --dip-mult 1.7 --bear-book

REM (B) Xem thử so sánh có trần (khi cap đã khớp engine):
.venv\Scripts\python.exe -m bot.run --once --equity 5000 --corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0

REM (A) Paper KHUYẾN NGHỊ (bằng chứng triển vọng):
.venv\Scripts\python.exe -m bot.run --mode paper --equity 5000 --corr-size --dip-mult 1.7 --bear-book --tag d17bf

REM (B) Paper so sánh có trần (= runner d17bfg2 hiện tại):
.venv\Scripts\python.exe -m bot.run --mode paper --equity 5000 --corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0 --tag d17bfg2

REM Kiểm tra sức khỏe hằng ngày:
.venv\Scripts\python.exe scripts/bot_health.py artifacts/bot/paper_d17bfg2

REM (A) Testnet KHUYẾN NGHỊ (bắt buộc trước live, khóa testnet trong .env):
.venv\Scripts\python.exe -m bot.run --mode testnet --corr-size --dip-mult 1.7 --bear-book --tag d17bf

REM (B) Testnet so sánh có trần: thêm --dip-gross-cap 2.0 vào lệnh trên.

REM Live (KHÓA — chỉ chủ tài khoản mở, sau testnet sạch + đủ điều kiện mục 6):
REM cmd: set BOT_ALLOW_LIVE=yes-real-money
REM PowerShell: $env:BOT_ALLOW_LIVE="yes-real-money"
REM (A) Live KHUYẾN NGHỊ: .venv\Scripts\python.exe -m bot.run --mode live --corr-size --dip-mult 1.7 --bear-book --tag d17bf
REM (B) Live có trần (khi cap đã khớp engine): thêm --dip-gross-cap 2.0 vào lệnh trên.
```

- Đủ flag mới đúng pipeline khuyến nghị: `--corr-size --dip-mult 1.7 --bear-book` (+ `--dip-gross-cap 2.0` chỉ khi cap đã khớp engine). Thiếu một flag là thành pipeline khác, mọi kỳ vọng dưới đây vô hiệu. Không chạy (A) và (B) cùng `--tag` cùng lúc (một runner/một thư mục state).
- Vì sao `--dip-gross-cap 2.0` (kết quả engine/backtest trong `docs/DEPLOYMENT_PLAN_VI.md`): giả lập cả 5 coin sập tức thì nhảy qua mọi stop — phút tệ nhất không trần lỗ 58% vốn, có trần 2x còn 33,5% (3x: 39%), trung vị/p99 không đổi; lợi nhuận giữ nguyên (~5,41 so với 5,43 %/tháng, DD 16,9 so với 18,3). Lưu ý bot hiện tại cài cap CHẶT HƠN engine nên con số “giữ nguyên” chưa đúng cho bot (xem CẢNH BÁO).
- `--adopt-fresh` mặc định TẮT, không thuộc pipeline khuyến nghị. Chỉ bật khi được yêu cầu bằng văn bản để nhận lại vị thế book còn tươi mà bot đã bỏ lỡ (cửa sổ 5–65 phút sau entry, lệnh limit đúng giá engine, có stop/TP). Mặc định không thêm flag này.
- `--equity` chỉ dùng cho dry/paper; live/testnet lấy vốn thật trên sàn. Dry `--once` mặc định `--mode dry`, không giữ `runner.lock`. Testnet cần `BYBIT_TESTNET_API_KEY` + `BYBIT_TESTNET_API_SECRET` trong `.env` (không commit, không dán vào chat).
- Live bị khóa cứng: thiếu `BOT_ALLOW_LIVE=yes-real-money` do chính chủ đặt thì bot từ chối. Testnet trước, live bắt đầu vốn nhỏ.
- Một runner cho mỗi thư mục state (khóa OS `runner.lock`). Không mở 2 tiến trình cùng `artifacts/bot/<mode>_<tag>`.

## 2. Nguồn plan: backend phải chạy

- Bot chỉ gương theo `artifacts/research/advisor_shadow/trade_plan_v376.json`, backend làm tươi mỗi giờ qua scheduler trong backend.
- Dựng backend trước bot. Backend đang chạy thì CHỈ dùng `-Status` để kiểm. Muốn chạy nền: `-Background` (log `artifacts\web\backend.log`); dừng: `-Stop`. KHÔNG gõ `.\run_backend.ps1` foreground khi backend đang chạy vì nó thay thế instance cũ.

```bat
.\run_backend.ps1 -Status
REM Chỉ khi backend chưa chạy: .\run_backend.ps1 -Background
REM Dừng: .\run_backend.ps1 -Stop
```

- Plan quá **4h30m** là cũ: bot chặn lệnh mới, chỉ giữ bảo vệ (stop/TP, thoát lệnh vẫn chạy), log `stale_plan`. Việc đầu tiên là dựng lại backend, không ép bot vào lệnh.
- Kiểm tra nhanh: mở `trade_plan_v376.json` xem `generated_at`; `bot_health.py` cũng báo tuổi plan.

## 3. Kiểm tra hằng ngày (5 phút)

```bat
.venv\Scripts\python.exe scripts/bot_health.py artifacts/bot/paper_d17bfg2
.venv\Scripts\python.exe scripts/paper_report.py artifacts/bot/paper_d17bfg2 artifacts/bot/paper_d17bf artifacts/bot/paper_g2k20
.venv\Scripts\python.exe scripts/prospective_scorecard.py
```

Tìm hàng `bot_paper_d17bfg2` (cột `percentile`, `config`, `go_live`, `stop`); mới chạy < 8 tuần thì `percentile` NaN là bình thường.

Ý nghĩa từng dòng `bot_health.py` (exit 0 ok / 1 warning / 2 critical):

- `last_cycle ... age`: CRITICAL nếu > 3 lần interval (> 60s với vòng 20s) hoặc > 5 phút = runner đã chết → khởi động lại lệnh mục 1, kiểm tra `runner.log`, Task Manager xem tiến trình cũ còn giữ `runner.lock` không.
- `plan age ... (>4h30m)`: warning = plan cũ → dựng lại backend (mục 2). Bot lúc này chỉ giữ thoát lệnh là đúng.
- `24h ops place/amend/cancel/fill/market_exit/stale_plan/errors`: `errors` > 0 = warning (xem 5 dòng lỗi kèm theo; `rate_limit`/10006 là chạm giới hạn Bybit → đợi, giảm tần suất). Để kiểm `cycle_error` kéo dài > 1 giờ (mất điều kiện go-live, dừng và sửa), chạy: `Select-String -Path artifacts/bot/paper_d17bfg2/actions.jsonl -Pattern cycle_error | Select-Object -Last 20` (bash: `grep cycle_error ...`), xem timestamp `t`; cùng lỗi lặp > 1 giờ mới tính.
- `unprotected=[...]`: CRITICAL = vị thế mở thiếu stop hoặc TP → kiểm tra ngay `actions.jsonl` + vị thế thật; bot tự đặt lại trong <= 20s, quá 2 vòng không stop sẽ đóng market (`unprotected_close`).
- `qty_mismatch=[...]`: CRITICAL = sổ bot lệch vị thế sàn → sàn là sự thật; kiểm tra tay, không sửa tay `state.json`.
- Với paper, “sàn” là `artifacts/bot/<dir>/exchange.json`; với live/testnet mới là Bybit thật. Xem tên nội bộ (`unprotected_close`, `plan_closed_divergence`, `skipped_below_minimum`, `stale_plan`, `sync_fills`): `Select-String -Path artifacts/bot/paper_d17bfg2/actions.jsonl -Pattern 'unprotected_close|plan_closed_divergence|skipped_below_minimum|stale_plan' | Select-Object -Last 20`.
- `equity ... maxDD`: lãi/lỗ và DD từ đầu paper; so với ngưỡng dừng mục 6.
- `fills24h / closed W/L`: số khớp dip/book 24h và thắng/thua mảnh đã đóng (chỉ tham khảo ngắn hạn).
- `missing actions.jsonl / state.json`: runner chưa từng chạy đúng thư mục/tag → kiểm tra lại `--tag`.

## 4. Sau reboot / mất điện / mất mạng: khởi động lại bằng tay

Bot và backend **không tự chạy lại**. Thứ tự:

1. Nếu backend chưa chạy: `.\run_backend.ps1 -Background`, chờ `.\run_backend.ps1 -Status` báo local OK, xác nhận `trade_plan_v376.json` có `generated_at` mới (< 4h30m). Backend đang chạy thì không gõ foreground.
2. Chạy lại đúng một runner cho mỗi mode bằng lệnh mục 1 (đúng `--tag d17bfg2` ↔ `artifacts/bot/paper_d17bfg2`). Nếu báo `another bot runner holds .../runner.lock` là còn tiến trình cũ — tìm bằng `Get-Process python` + xem `state.json` (mtime) và `stdout.log`, đừng chạy đè.
3. Đối chiếu `actions.jsonl` với vị thế sàn (paper: `exchange.json`; live/testnet: Bybit thật): stop/TP thiếu được đặt lại trong <= 20s; mảnh plan đã thoát mà sàn còn mở bị đóng market sau ~3 phút (`plan_closed_divergence`).
4. Mất mạng dài: stop market + TP limit reduce-only đã nằm trên sàn vẫn bảo vệ vị thế; phần hở duy nhất là mảnh vừa khớp chưa kịp đặt exit (cửa sổ <= 20s) — kiểm tra tay khi mạng trở lại.

## 5. Vốn, margin, đòn bẩy

- Tối thiểu **5000 USDT, tốt nhất ~10000 USDT** (`docs/DEPLOYMENT_PLAN_VI.md`). Dưới mức này bậc dip BTC < 0,001 BTC bị bỏ (`skipped_below_minimum`): 10.000 đặt được 100% book / 98% dip; 5.000: 96% / 94%; 2.000: 80% / 81% (mất ~5–20%).
- Sàn Bybit, **cross margin**. Đặt mức đòn bẩy tài khoản đủ cao cho notional dip: không trần có lúc tới **~6,4x vốn**, có trần 2x còn tối đa **~2x vốn** — đòn bẩy cài thấp sẽ thiếu margin đặt đủ rungs.
- Máy chạy 24/7 (BOT cần bot trực; bản MANUAL theo tay không cần).

## 6. Kỳ vọng thực tế + go-live / dừng (từ DEPLOYMENT_PLAN_VI.md)

- Kỳ vọng trung thực R2B1D17BF: **trung vị ~5 %/tháng, năm xấu ~3 %/tháng, DD tới ~18 %**.
- Cửa sổ 12 tháng trượt (49 cửa sổ): %/tháng min 2,73 / p10 3,25 / trung vị 4,89 / p90 8,88 / max 11,71; DD min 8,3 / trung vị 13,5 / p90 18,3 / max 18,7; không cửa sổ nào lỗ; 49% đạt >= 5 %/tháng, 61% DD < 15, 100% DD < 20.
- Bootstrap 10.000 năm: trung vị ~5,1 %/tháng (p5 1,5 / p95 10,3), chỉ ~52% năm đạt >= 5 %/tháng; DD trung vị 14,5%, p95 22,6%; P(DD > 20%) ~11%; P(năm lỗ) ~0,7%. Vốn phải chịu được DD 25%.
- KPI: 41% tháng >= +5%, 72% tháng không lỗ, chuỗi lỗ dài nhất 2 tháng; thắng book 51,5%, dip 68,7%, toàn bộ 65,5%.
- Go-live tiền thật nhỏ (sau tối thiểu 8 tuần paper, ĐỦ cả 4): (a) lợi nhuận paper ở phân vị >= 20 của bootstrap (`prospective_scorecard.py`); (b) DD paper <= 15%; (c) lệch bot so với plan <= 1,5 điểm %/tháng; (d) không `cycle_error` > 1 giờ, không vị thế thiếu stop. Tăng vốn sau 3 tháng live nếu (a)–(c) vẫn đúng.
- Dừng: DD tài khoản > 20% → dừng mở mới, chỉ giữ SL/TP; lỗ một tháng > 10% → halve vốn tháng sau; phân vị lợi nhuận < 5 sau >= 8 tuần → dừng.
