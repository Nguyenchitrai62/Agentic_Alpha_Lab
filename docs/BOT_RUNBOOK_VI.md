# Sổ tay vận hành BOT khuyến nghị R2B1D17BF + trần dip (cho người vận hành)

> Bot gương lệnh chạy pipeline R2B1D17BF (v411) trên Bybit USDT perps, Hedge Mode.
> Kỳ vọng, ngưỡng go-live/dừng lấy nguyên văn từ `docs/DEPLOYMENT_PLAN_VI.md`
> (đăng ký trước 2026-10-05, không sửa sau khi thấy dữ liệu paper).
> Chi tiết kỹ thuật: `docs/BOT_EXECUTION.md`, code `bot/run.py`.

> **CẬP NHẬT 2026-10-06 (bot_capfix):** cách bot cài `--dip-gross-cap` đã được sửa cho khớp engine (mỗi lệnh dip chờ <= phần trống = 2x vốn sub-book
> trừ notional dip đang mở; giới hạn cứng 4x). Tháng 9/2026: có trần +3,20 % so với không trần +3,58 % (bản cũ chỉ +1,1 %). => Dùng lệnh (B) có
> `--dip-gross-cap 2.0` làm cấu hình khuyến nghị (trần giảm lỗ phút tệ nhất khi gap -10 % từ 58 % xuống 33,5 % vốn).

## 1. Lệnh khuyến nghị (R2B1D17BF + trần an toàn)

Mọi lệnh chạy từ thư mục repo root. Windows dùng `.venv\Scripts\python.exe`.

- (A) Không trần (chỉ để so sánh): BỎ `--dip-gross-cap`.
- (B) KHUYẾN NGHỊ (cap đã khớp engine từ 2026-10-06): THÊM `--dip-gross-cap 2.0` vào cùng lệnh.
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

Bắt đầu bằng một trang tổng quan, rồi mới soi chi tiết từng bot:

```bat
.venv\Scripts\python.exe scripts/daily_status.py
.venv\Scripts\python.exe scripts/bot_health.py artifacts/bot/paper_d17bfg2
.venv\Scripts\python.exe scripts/paper_report.py artifacts/bot/paper_d17bfg2 artifacts/bot/paper_d17bf artifacts/bot/paper_g2k20
.venv\Scripts\python.exe scripts/prospective_scorecard.py
```

Tìm hàng `bot_paper_d17bfg2` (cột `percentile`, `config`, `go_live`, `stop`); mới chạy < 8 tuần thì `percentile` NaN là bình thường.

- `scripts/daily_status.py` là điểm bắt đầu: một trang gồm (1) backend + tuổi plan, (2) mọi thư mục `artifacts/bot/paper*` (tóm tắt bot_health + equity/return/DD/fills), (3) collector (liquidations/topbook theo venue + gap > 5 phút/24h), (4) một dòng kết luận OK/WARNING/CRITICAL. Chỉ đọc file, không chạm `.env`, không start/stop process.
- `scripts/bot_health.py` soi chi tiết từng bot khi daily_status báo WARNING/CRITICAL.

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

## 4b. Bảo trì có kế hoạch + kiểm tra sau restart (`bot_maint`, 2026-10-06)

- Trước bảo trì ĐỊNH KỲ: đặt cửa sổ bảo trì để bot tự hủy bid dip đang chờ + không vào lệnh book mới
  (từ trước giờ bắt đầu 30 phút tới hết giờ kết thúc; stop/TP/backstop và chân carry giữ nguyên trên sàn):

```bat
REM Cách 1: flag khi khởi động runner (giờ UTC ISO):
REM .venv\Scripts\python.exe -m bot.run --mode paper --equity 5000 --corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0 --tag d17bfg2 --maint-start 2026-10-07T01:00:00Z --maint-end 2026-10-07T03:00:00Z

REM Cách 2 (khuyên dùng): ghi file, bot đọc mỗi vòng 20s, xóa/sửa không cần restart:
REM artifacts/bot/paper_d17bfg2/maintenance.json = {"start": "2026-10-07T01:00:00Z", "end": "2026-10-07T03:00:00Z"}
```

- Kiểm tra trong `actions.jsonl`: `op=maint_cancel` (đã chặn/hủy lệnh mới) rồi `op=maint_resume` (chạy lại).
  Mặc định không flag/không file = bot chạy y hệt cũ.
- Sau MỌI lần restart (reboot/mất điện/mất mạng): runner tự ghi `op=protection_check` liệt kê từng mảnh
  đang mở và stop/TP native còn trên sàn hay không. Người trực chạy `bot_health.py`: dòng
  `CRITICAL: open without stop+TP` phải trống mới cho bot chạy tiếp; nếu còn mảnh thiếu stop thì chờ bot đặt
  lại (<= 20s, quá 2 vòng tự đóng market `unprotected_close`), không đặt tay trong giờ đầu.

## 5. Vốn, margin, đòn bẩy (cài đặt tài khoản Bybit từ oc_margin, 2026-10-06)

- Tối thiểu **5000 USDT, tốt nhất ~10000 USDT** (`docs/DEPLOYMENT_PLAN_VI.md`). Dưới mức này bậc dip BTC < 0,001 BTC bị bỏ (`skipped_below_minimum`): 10.000 đặt được 100% book / 98% dip; 5.000: 96% / 94%; 2.000: 80% / 81% (mất ~5–20%).
- Sàn Bybit, **Cross margin + Hedge Mode** (không dùng Isolated cho bot). Chỉnh đòn bẩy tài khoản **5x trên cả 5 coin** BTC/ETH/SOL/BNB/XRP (Bybit chỉnh theo từng coin).
- Vì sao 5x (G2 `--dip-gross-cap 2.0`, `research/tournament/oc_margin/REPORT.md`): **mức tối thiểu không bao giờ chặn lệnh** (IM = G/đòn bẩy <= 95% vốn mọi phút mở trong 5 năm; 3x đã chặn 22 phút mix / 31–45 phút mỗi phase). 10x/20x cũng không chặn nhưng không an toàn hơn trong cross (thanh lý không phụ thuộc IM) mà chỉ làm lệnh nhầm tay to hơn — **giữ 5x**.
- Dư địa ở 5x: gross tối đa **~3,4x vốn** (không trần ~7,1x); IM tối đa **68% vốn** (từng phase 71–76%), thường chỉ ~7% (free trung vị 93%); phút chật nhất vẫn còn >= 32% free.
- Khoảng cách thanh lý (cross, all-long): phút thường cần sập **~300%** mới cháy, 99% số phút cần sập > 73–76%; phút tệ nhất lịch sử (2025-09-25 17:57, G 3,41) vẫn cần **sập tức thì -29% cả 5 coin** mới cháy (từng phase 26–28%).
- Gap tức thì cả 5 coin: **-10% không phút nào cháy** (0/65,1k phút; trung vị mất 0,83%, p99 ~13%, tệ nhất ~34%); **-20% cũng không phút nào cháy** (tệ nhất mất ~68%, cần ~98,5% mới cháy). Lệnh vẫn sống — nhưng sau gap kiểm tra tay trước khi cho bot chạy tiếp. Nếu Bybit báo thiếu margin / `skipped_below_minimum` nhiều: kiểm tra leverage có bị reset về thấp không — **không tự hạ đòn bẩy khi đang có vị thế**.
- Máy chạy 24/7 (BOT cần bot trực; bản MANUAL theo tay không cần).

## 6. Kỳ vọng thực tế + go-live / dừng (từ DEPLOYMENT_PLAN_VI.md)

- Kỳ vọng trung thực R2B1D17BF: **trung vị ~5 %/tháng, năm xấu ~3 %/tháng, DD tới ~18 %**.
- Cửa sổ 12 tháng trượt (49 cửa sổ): %/tháng min 2,73 / p10 3,25 / trung vị 4,89 / p90 8,88 / max 11,71; DD min 8,3 / trung vị 13,5 / p90 18,3 / max 18,7; không cửa sổ nào lỗ; 49% đạt >= 5 %/tháng, 61% DD < 15, 100% DD < 20.
- Bootstrap 10.000 năm: trung vị ~5,1 %/tháng (p5 1,5 / p95 10,3), chỉ ~52% năm đạt >= 5 %/tháng; DD trung vị 14,5%, p95 22,6%; P(DD > 20%) ~11%; P(năm lỗ) ~0,7%. Vốn phải chịu được DD 25%.
- KPI: 41% tháng >= +5%, 72% tháng không lỗ, chuỗi lỗ dài nhất 2 tháng; thắng book 51,5%, dip 68,7%, toàn bộ 65,5%.
- Go-live tiền thật nhỏ (sau tối thiểu 8 tuần paper, ĐỦ cả 4): (a) lợi nhuận paper ở phân vị >= 20 của bootstrap (`prospective_scorecard.py`); (b) DD paper <= 15%; (c) lệch bot so với plan <= 1,5 điểm %/tháng — kiểm tra bằng `python scripts/paper_divergence.py artifacts/bot/paper_d17bfg2` (trước 14 ngày báo `too early` là bình thường); (d) không `cycle_error` > 1 giờ, không vị thế thiếu stop. Tăng vốn sau 3 tháng live nếu (a)–(c) vẫn đúng.
- Dừng: DD tài khoản > 20% → dừng mở mới, chỉ giữ SL/TP; lỗ một tháng > 10% → halve vốn tháng sau; phân vị lợi nhuận < 5 sau >= 8 tuần → dừng.

## 7. Preflight chỉ-đọc trước testnet/live (`scripts/bot_preflight.py`, 2026-10-06)

Chủ tài khoản chạy trước lần testnet/live đầu tiên (và sau mỗi lần đổi key/settings).
Chỉ gọi endpoint V5 đọc (signed GET + public), không bao giờ đặt/hủy lệnh hay đổi Hedge/Cross/đòn bẩy;
key đọc cùng cách `bot/run.py`, không in key. Testnet không cần mở khóa live.

```bat
.venv\Scripts\python.exe scripts/bot_preflight.py --mode testnet
.venv\Scripts\python.exe scripts/bot_preflight.py --mode live
```

Checklist in tiếng Việt, exit 0 chỉ khi không có FAIL: key+quyền trade, tài khoản Unified,
Hedge Mode, Cross, đòn bẩy 5x từng coin, vốn (cảnh báo < 10000 / < 5000), lệnh/vị thế lạ
(link bot có dạng `b/d<phase><BTC|ETH|SOL|BNB|XRP>...`, còn lại là WARN), lệch giờ server (< 1s),
minima sàn ở vốn hiện tại (cỡ lệnh theo pipeline khuyến nghị `--dip-mult 1.7`). Mỗi FAIL kèm bước
sửa chính xác trên Bybit UI. Test: `tests/test_bot_preflight.py` (mock, PASS + mỗi FAIL).

## 8. Sổ paper carry sleeve (`scripts/carry_paper.py`, 2026-10-06)

Bằng chứng triển vọng cho tay carry (quy tắc đóng băng `research/tournament/oc_cashcarry/PLAN.md`:
vào quarterly kế tiếp khi hợp đồng hiện tại còn <= 7 ngày hoặc lần đầu có hàng, chỉ khi basis
năm hóa >= 4 %, long spot + short quarterly bằng notional, mỗi chân = f x vốn lúc vào, giữ tới
giao hàng; phí spot taker 0,1 %/bên, futures vào 0,055 %, giao hàng 0,02 %). Chỉ đọc endpoint
công khai Bybit V5 (`instruments-info` linear+inverse, `tickers` spot+futures, `delivery-price`
lúc đáo hạn) — không key, không đặt/hủy lệnh, không bao giờ chạm tiền thật.

```bat
REM Paper carry (lũy thừa theo giờ hoặc chạy tay, idempotent):
.venv\Scripts\python.exe scripts/carry_paper.py --once --equity 5000 --f 0.5 --tag carry
```

## 9. Khởi động lại sau reboot bằng `scripts/restart_all.*` (2026-10-06)

Sau reboot/mất điện, thay vì làm tay từng bước mục 4, chạy MỘT trong hai script
cùng logic (`restart_all.sh` cho Git Bash, `restart_all.ps1` cho PowerShell).
Script chỉ đọc process (không bao giờ dừng/kill process), idempotent — chạy
lại lần hai không khởi động gì thêm; không đặt `BOT_ALLOW_LIVE`, không bao giờ
chạy testnet/live, không bật tunnel công khai (backend chỉ local 127.0.0.1:8724).

```bat
REM Xem kế hoạch trước (không khởi động gì):
bash scripts/restart_all.sh --dry-run
REM PowerShell: .\scripts\restart_all.ps1 -DryRun

REM Khôi phục đủ (thứ tự: backend local -> 5 bot paper -> vòng carry -> bot_health + daily_status):
bash scripts/restart_all.sh
REM Chỉ một nhóm: bash scripts/restart_all.sh --only bots|backend|carry
```

- Backend: nếu `/health` đã OK thì bỏ qua; nếu chưa, dựng uvicorn local
  (`backend.server:app`, 127.0.0.1:8724, không tunnel), chờ `/health` rồi chờ
  plan tươi (< 1h15m). Vòng `loop.sh` cũ đã ngừng từ 2026-09-30 (backend tự chạy
  advisor shadow), script không dựng lại.
- Mỗi bot paper chỉ dựng khi không còn tiến trình giữ `runner.lock`
  (`paper`: R2-4P không tag; `d17bf`/`d13bf`/`d17bfg2`/`g2k20` đúng `--tag`;
  `d17bfg2`/`g2k20` kèm `--dip-gross-cap 2.0 --adopt-fresh`; tất cả
  `--interval 25` như đang chạy). Trước khi dựng, `state.json` được sao lưu
  (`state.json.bak_<UTC>`) và kiểm tra JSON hợp lệ.
- Vòng carry (`carry_paper.py --once --equity 5000 --f 0.5 --tag carry`, mỗi
  3600 s) chỉ dựng một bản khi chưa chạy. Cuối cùng script in `bot_health.py`
  cho cả 5 runner và tóm tắt `daily_status.py`.
- Kiểm thử: `tests/test_restart_all.py` (nội dung kế hoạch + idempotent với
  danh sách process giả, không chạy script thật).

- State `artifacts/bot/paper_carry/state.json` (vị thế, basis lúc vào, phí, MtM theo giá mid,
  P&L thực khi giao hàng) + `actions.jsonl` (entry/hold/settle/skip/no_eligible/delisted/error).
  Sha256 quy tắc in đầu mỗi run; đổi quy tắc là đổi sha (không sửa lén).
- Không hợp đồng đủ điều kiện / basis < 4 % / delist / lỗi API (retry/backoff) đều chỉ ghi log,
  không crash vòng lặp. Kiểm tra: `tests/test_carry_paper.py` (client giả: vào, giữ, đáo hạn,
  skip, delist, lỗi).

## 10. Triển khai khuyến nghị docs_update5: G2 + carry f=0.25 một UTA (2026-10-06)

KHUYẾN NGHỊ: BOT G2 (`--corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0`, v421 5,41/worst 2,588/maxDD 16,91/full 16,82) + sleeve carry quý
f=0,25 cùng một UTA cross/hedge/5x [oc_carrycombo; oc_utamargin]. Roll-only (vận hành thật): f=0,25 5,413/2,647/16,78/full 16,34; f=0,50 5,418/2,705/
16,65/15,86 [oc_carrycombo]. Ma sát (`oc_carryfric` year-start): f=0,25 base 5,533 / S1 4,696 / S2 5,339 / S3 4,717 / S4 5,033 / S5 5,016 (f=0,50 5,654 /
4,820 / 5,463 / 4,853 / 5,166 / 5,147) — rớt S1/S3 kể cả f=0,50 [oc_carryfric]. Margin (`oc_utamargin`): f=0,25 CLEAR (free min 22,49%, 0 blocked, gap
−10% −28,85% không liq); f=0,50 KHÔNG clear (1 giờ blocked 2025-09-25 18:00, spot cost 179,9%) — trên 0,25 tách vốn [oc_utamargin]. Bybit live:
linear BTCUSDT-25DEC26/26MAR27/25JUN27 + inverse BTCUSDZ26/H27 (cả ETH), yield inverse ≈ Binance (−5%) [oc_carrycombo; bybitq].
Bước tay carry (đóng băng `oc_cashcarry`): quarterly kế tiếp khi front còn <=7 ngày, basis ln(F/S)*365/DTE >=4%/năm, mỗi chân f x vốn (f=0,25), long
spot + short quarterly bằng notional, giữ tới delivery (~4 quyết định/năm ≈ 15 vé/năm) [carry_paper.py; oc_manualcarry]. Stretch D13BF+carry f=0,25
base 5,104/14,85 ĐẠT [oc_carryd13] nhưng ma sát chỉ còn base + S2 f=0,50 — không deploy stretch [oc_carryfric]. MANUAL+carry tốt nhất 3,993 vẫn <5 —
NO [oc_manualcarry]. Plateau G2 trong 0,3%/0,5pp giữ deploy [oc_plateau2]; 8-phase 4,960/17,32 NO [oc_phase8]. Screens đóng: expirydip +0,0164 vs gate
+0,273 NO [oc_expirydip]; usdtdip +0,047 NO [oc_usdtdip]. Restart: `bash scripts/restart_all.sh` (loop.sh retired 2026-09-30), xem mục 9
[restart_all.sh].

## 11. Bổ sung docs_update7 (2026-10-06)

- Crash COVID cho thang dip (`research/tournament/oc_crash2020/REPORT.md`): mix 4 pha ~-16.1%, pha đơn tệ nhất -21.85% (DD 22.30) — vượt ngưỡng 20%
nên không bao giờ chạy 1 pha đơn lẻ. Trần 2.0x không kích hoạt trong crash (peak gross max 1.03x) nhưng vẫn giữ để chặn gap lúc yên (58%→33.5%).
- Bảo trì/mất bot (`research/tournament/oc_outage/REPORT.md`): trước bảo trì CÓ KẾ HOẠCH thì HỦY các bid dip đang chờ, xong đặt lại khi bot lên
(giữ nguyên TP native + backstop 8-sigma trên sàn; tốn lỡ lệnh giờ yên ~0.4 fill/giờ không đáng kể). Sau sự cố bất ngờ: để bot tự exit ở phút mở đầu tiên
khi trở lại, người trực chỉ xác nhận không còn vị thế mở mà thiếu stop (unprotected) và mọi rung mở còn backstop native, không đặt tay giờ đầu tiên.
Routine 1-2.5% tổng dip 5 năm, DD gần như không đổi; giờ xấu nhất lịch sử +0.684 (~9% tổng 5 năm), DD +0.26.
- Carry đáo hạn (`research/tournament/carry_audit/COMPARISON.md` Leader adjudication + `docs/BOT_EXECUTION.md` bot_carry): BÁN chân spot đúng giờ delivery
(08:00 UTC, tốt nhất rải trong cửa sổ trung bình index) để khớp đúng index đáo hạn; bot đã cài (spot bán market sau delivery + buy-back an toàn cho sim,
log `carry_settle/carry_settled`, short futures/coin <=0.30x vốn, không tính vào trần dip). Quy tắc vào giữ nguyên: quarterly kế tiếp khi front <=7 ngày,
basis >=4%/năm, mỗi chân f x vốn (f=0,25), giữ tới delivery.
- Bão hòa (`research/diagnostics/oc_saturation/REPORT.md`): 8%/tháng không tới bằng tăng size — biên max ~5.9%/tháng ở DD>17.5; edge/đơn vị bất biến
(0.0029→0.0028), B1 cắt ~35% notional, trần 2x gần miễn phí. Không tăng kd để đuổi return.
- Cảnh báo sớm edge đã vào kiểm tra hằng ngày (`research/diagnostics/oc_edgedecay/REPORT.md` + `scripts/edge_monitor.py` + `scripts/daily_status.py` mục 6):
không decay (slope +0.067 CI [-0.158;+0.160]; sau 6.61 > đầu 5.59). `daily_status.py` mục 6 hiện báo cho paper_d17bfg2/c: (1) TB 6 tháng <1.61%/tháng,
(2) TP rate dip 182 ngày <0.434 — vỡ = ĐIỀU TRA, không tự đổi cấu hình.
- Book-model đóng (`research/parallel/rounds/parallel-20260906-r2/v428/result_manifest.json`): C1 dev 1.927/1.768/3.191/7.590 mean 3.593 DD 19.17
vs book triển khai 5.601/16.91 → REJECTED; C2 cũng rejected; hướng đóng 2/2 — giữ flags triển khai mục 1, không chờ model.
- Screens đóng: oc_carrytopup CLOSE (top-up 7d f=0.125 lỗ cả 5/5 năm hai venue + stack phải vay) [oc_carrytopup]; oc_bidttl NOT PROMISING (TTL 120' mất
-1.339 5y, late fills toàn winner 59-69%) [oc_bidttl]; oc_marktrig NOT PROMISING (sum 4/5 nhưng DD 2/5, mark fire sớm hơn trong crash) — giữ last-price
[oc_marktrig].

## 12. Sao lưu file untracked (`scripts/snapshot_untracked.py`, 2026-10-06)

- Vì sao: ngày 2026-10-06 một worker chạy `git stash -u` làm mất ~860 file untracked khỏi cây làm việc
  (file untracked không nằm trong git theo thiết kế — AGENTS.md: kết quả để local). Script này chụp nhanh
  để lần sau khôi phục được. GIT READ-ONLY: script chỉ ĐỌC qua `git ls-files`, không bao giờ
  stash/reset/checkout/clean/commit, không bao giờ sửa/xóa file nguồn.
- Phạm vi: file untracked + gitignored dưới `research/`, `docs/opencode/`, `tests/` và
  `artifacts/bot/*/{state.json,actions.jsonl,exchange.json}` (loại `data/raw`, `models`, file > 50 MB,
  `__pycache__`). Zip đích: `artifacts/backups/untracked_<UTC>.zip` gồm file (đường dẫn tương đối) +
  `manifest.json` (mỗi mục: path, size, sha256). Giữ 14 bản mới nhất; chỉ xóa zip snapshot cũ do chính
  script tạo, không chạm gì khác.

```bat
REM Xem kế hoạch trước (không ghi gì):
.venv\Scripts\python.exe scripts/snapshot_untracked.py --dry-run

REM Chụp thật + tỉa bản cũ:
.venv\Scripts\python.exe scripts/snapshot_untracked.py

REM Liệt kê nội dung một bản (không ghi gì):
.venv\Scripts\python.exe scripts/snapshot_untracked.py --restore-list artifacts/backups/untracked_<UTC>.zip
```

- Kiểm thử: `tests/test_snapshot_untracked.py` (repo git tạm, không chạm cây thật). Chạy tay định kỳ
  trước các đợt dọn git (stash/clean/reset) và sau mỗi tuần paper.

## 13. Watcher cảnh báo CRITICAL (`scripts/alert_watch.py`, 2026-10-06)

- Chủ tự chạy tay (không tự khởi động, không network, không credentials — chỉ đọc file local):

```bat
REM Chạy nền mỗi 300s (toast Windows + log artifacts/alerts/alerts.log):
.venv\Scripts\python.exe scripts/alert_watch.py --every 300

REM Kiểm tra một lần, không toast:
.venv\Scripts\python.exe scripts/alert_watch.py --once --no-toast
```

- Mỗi vòng đọc health nhanh/local của 2 runner triển khai (`paper_d17bfg2`, `paper_d17bfg2c`)
  bằng đúng hàm `bot_health.check_dir` + `daily_status.check_plan` + `stop_rules.summarize_runner`
  (không đọc parquet collector, không chạm `.env`, không start/stop process).
  6 mục CRITICAL: vị thế thiếu stop/TP, lệch số liệu với sàn, chu kỳ cuối > 5 phút,
  plan > 4h30m, stop rule STOP (DD > 20% / lỗ tháng > 10% / phân vị < 5 sau >= 8 tuần),
  carry lệch hedge > 2 cycle.
- Toast Windows dùng `[Windows.UI.Notifications]` có sẵn (BurntToast không cài sẵn);
  lỗi thì fallback `msg` / beep console. Mỗi incident mới toast ĐÚNG 1 lần
  (de-dup trong bộ nhớ tiến trình); hết thì ghi `RESOLVED` vào `alerts.log`.
  Khi toast nổ: chạy `daily_status.py` + `bot_health.py` như mục 3 rồi xử lý theo mục 4/6.
- Kiểm thử: `tests/test_alert_watch.py` (health giả + notifier giả, không toast thật).
