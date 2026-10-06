# Xác minh sổ tay vận hành BOT (BOT_RUNBOOK_VI.md) — 2026-10-06

- Người thực hiện: vai operator mới, nói tiếng Việt, trên máy này (Windows, repo `Agentic_Alpha_Lab`).
- Sổ tay được kiểm: `docs/BOT_RUNBOOK_VI.md` (đọc ngày 2026-10-06). Đối chiếu thêm `docs/DEPLOYMENT_PLAN_VI.md`, `docs/BOT_EXECUTION.md`, `bot/run.py --help`, code `bot/run.py` / `bot/mirror.py` / `scripts/bot_health.py`.
- Phạm vi an toàn theo `docs/opencode/OPENCODE_W_ops_runbook.md`: CHỈ chạy dry `--once`, `bot.run --help`, `scripts/bot_health.py` trên thư mục đã có, `scripts/paper_report.py`, `scripts/prospective_scorecard.py`, `run_backend.ps1 -Status`. KHÔNG start/stop backend hay bot (đang chạy), KHÔNG chạm `.env`, KHÔNG credentials, KHÔNG testnet/live loop, KHÔNG commit/sửa runbook hay code.
- Thời điểm kiểm: 2026-10-06 ~02:30 UTC. Backend đang chạy, plan tươi, 3 paper runner đang chạy (xem mục 2–3).

## 0. Đầu sổ tay (dòng 3–6): pipeline, plan, tài liệu liên quan

- Đã đọc: đúng là pipeline R2B1D17BF (v411) trên Bybit USDT perps, Hedge Mode; kỳ vọng/ngưỡng go-live/dừng dẫn sang `docs/DEPLOYMENT_PLAN_VI.md`; chi tiết kỹ thuật `docs/BOT_EXECUTION.md` + `bot/run.py`.
- Kiểm: `docs/DEPLOYMENT_PLAN_VI.md` tồn tại, có bảng kỳ vọng + mục 2–4 + bootstrap/cửa sổ trượt/gap-stress; `docs/BOT_EXECUTION.md` tồn tại; `bot/run.py` tồn tại.
- Khớp thực tế: CÓ. Rõ với người mới, trừ mục CẢNH BÁO dưới đây.

## CẢNH BÁO 2026-10-06 (dòng 8–10): `--dip-gross-cap` chặt hơn engine

- Nội dung: bot-vs-engine (research/diagnostics/bot_parity_adopt) cho thấy bot cài `--dip-gross-cap` CHẶT HƠN engine (tính cả lệnh dip đang chờ, chia phòng tích lũy) → 09/2026 bot có trần chỉ +1,1% so với +3,6% không trần. Đang sửa (bot_capfix). Tới khi sửa xong: chạy KHÔNG có `--dip-gross-cap` hoặc chấp nhận lợi nhuận thấp hơn.
- Không có lệnh nào được chạy để kiểm nội dung này (thuộc nghiên cứu, không thuộc bước an toàn). Chỉ đối chiếu văn bản.
- Vấn đề: CẢNH BÁO bảo “chạy KHÔNG có cap”, nhưng mục 1 ngay dưới vẫn giữ lệnh khuyến nghị CÓ `--dip-gross-cap 2.0` và dòng 34–35 vẫn gọi đó là “pipeline khuyến nghị” / “Vì sao --dip-gross-cap 2.0”. Người mới không biết nghe theo bên nào. Xem ISSUE-01.

## 1. Lệnh khuyến nghị (R2B1D17BF + trần an toàn)

Ghi chú chung: sổ tay viết “Mọi lệnh chạy từ thư mục repo root. Windows dùng `.venv\Scripts\python.exe`.” — ĐÚNG. Trên shell bash của máy này phải viết `.venv/Scripts/python.exe` → `./.venv/Scripts/python.exe`; trong `cmd` dùng backslash như sổ tay. Không chạy lệnh paper/testnet/live dạng loop (chỉ kiểm cờ qua `--help` + báo cáo trên state có sẵn).

### 1a. Xem thử, không gửi lệnh (dry `--once`)

- Lệnh đã chạy (an toàn):
  `./.venv/Scripts/python.exe -m bot.run --once --equity 5000 --corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0`
- Kết quả: chạy xong, in JSONL các `op=cancel` (~86 lệnh, link `b*`/`d*`) rồi `op=place` (book ETH 3 lệnh + dip các coin, ví dụ `ETHUSDT Buy 0.02 @2700.74 GTC`, `BTCUSDT Buy 0.004 @84065.1`), kèm `op=bear_state bear=false opens=1200`. Không gửi lệnh thật (mode dry chỉ in).
- Khớp mô tả “Xem thử, không gửi lệnh”: CÓ. Đúng cả 4 flag đều tồn tại trong `--help` (`--corr-size`, `--dip-mult`, `--bear-book`, `--dip-gross-cap`).
- Chưa rõ với người mới: `--once` mặc định `--mode dry` (code `default="dry"`, `if not a.once` mới giữ lock) nên lệnh trên không cần `--mode` và không giữ `runner.lock`. Sổ tay không nói điều này, nhưng không sai. Nên bổ sung 1 dòng (ISSUE-08).

### 1b. Paper khuyến nghị (`--mode paper ... --tag d17bfg2`)

- KHÔNG chạy loop paper (sẽ tạo runner thứ hai / ghi state — ngoài phạm vi an toàn). Chỉ kiểm:
  - `./.venv/Scripts/python.exe -m bot.run --help` → có `--mode {dry,paper,testnet,live}`, `--equity`, `--corr-size`, `--dip-mult`, `--bear-book`, `--dip-gross-cap G`, `--tag TAG` (state dir `artifacts/bot/<mode>[_<tag>]`), `--adopt-fresh`, `--risk-mult`, `--dip-cooldown-h`, `--dip-sl-coin`, `--interval` (mặc định 20.0), `--plan`.
  - Thư mục paper có sẵn: `artifacts/bot/paper_d17bfg2/` (cùng `paper_d17bf`, `paper_g2k20`, `paper`, `paper_b1`, `paper_d18`, `dry`) đều tồn tại với `actions.jsonl`/`state.json`/`exchange.json`.
  - `scripts/paper_report.py` trên 3 dir paper (xem mục 3) cho thấy `paper_d17bfg2` start 2026-10-05T17:51:59Z, equity now 4,999.84, open 3 `[ETHUSDT|1:0.06]`, book fills 3, dip 0.
- Khớp: CÓ (cờ/tên tag/đường dẫn đúng). Sổ tay không ghi `--adopt-fresh` (có trong `--help`, mặc định off) — xem ISSUE-02.

### 1c. Kiểm tra sức khỏe hằng ngày (`bot_health.py`)

- Lệnh đã chạy: `./.venv/Scripts/python.exe scripts/bot_health.py artifacts/bot/paper_d17bfg2`
- Kết quả (02:30 UTC, exit 0):
  `[OK] artifacts\bot\paper_d17bfg2 last_cycle=2026-10-06T02:29:59+00:00 (age 11s) / plan=2026-10-06T02:01:00+00:00 age=0.5h / 24h ops: place=144 amend=10 cancel=93 fill=3 market_exit=0 stale_plan=52 errors=0 rate_limit=0 / open=3 unprotected=none qty_mismatch=none / equity 4,999.84 vs 5,000.00 (pnl -0.16) maxDD=0.01% / fills24h dip=0 book=3 other=0 closed W/L=0/0 pnl=+0.00`
- Khớp mô tả “Kiểm tra sức khỏe hằng ngày”: CÓ. Đường dẫn và output đúng như sổ tay.
- Đã kiểm thêm đa thư mục: `paper_d17bf` [OK], `paper_g2k20` [OK], `paper` [WARNING: 15 API errors 24h, toàn rate-limit], `dry` [OK + `warning: no exchange.json`], dir không tồn tại → `[CRITICAL] ... missing actions.jsonl ... EXIT:2`. Đúng tài liệu exit 0/1/2 trong `scripts/bot_health.py` (0 ok, 1 warning, 2 critical).

### 1d. Testnet (bắt buộc trước live)

- KHÔNG chạy (cần khóa testnet trong `.env` + gửi lệnh thật — ngoài phạm vi; cũng không chạm `.env`).
- Kiểm tĩnh: `--help` có `--mode testnet`; `BOT_EXECUTION.md` ghi cần `BYBIT_TESTNET_API_KEY/SECRET` trong `.env`. Sổ tay chỉ nói “khóa testnet trong .env” mà không nêu tên biến — người mới phải mở thêm `BOT_EXECUTION.md`. Đề xuất bổ sung tên biến (ISSUE-08).
- Khớp: TẠM (cờ tồn tại, nhưng thiếu tên biến + chưa thể kiểm end-to-end ở chế độ an toàn).

### 1e. Live (KHÓA)

- KHÔNG chạy (đúng theo cấm live/testnet orders).
- Kiểm tĩnh code `bot/run.py:533-534`: `if a.mode == "live" and os.environ.get("BOT_ALLOW_LIVE") != "yes-real-money": sys.exit("live trading is locked...")`. Đúng như sổ tay “thiếu `BOT_ALLOW_LIVE=yes-real-money` do chính chủ đặt thì bot từ chối”.
- Chưa rõ: sổ tay ghi `set BOT_ALLOW_LIVE=yes-real-money` là cú pháp `cmd`; trên PowerShell phải là `$env:BOT_ALLOW_LIVE="yes-real-money"`. Người mới dùng PowerShell sẽ làm sai. Xem ISSUE-08.

### 1f. “Đủ 4 flag mới đúng pipeline”

- Kiểm: 4 flag `--corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0` đều tồn tại, đúng giá trị trong lệnh mẫu. Cảnh báo “thiếu một flag là pipeline khác, kỳ vọng vô hiệu” là hợp lý (khớp DEPLOYMENT_PLAN: D17BF vs G2/D16/D18 khác `--dip-mult`/cap).
- Mâu thuẫn duy nhất là với CẢNH BÁO cap (ISSUE-01): nếu bỏ cap theo cảnh báo thì cũng thành “pipeline khác”.

### 1g. “Vì sao `--dip-gross-cap 2.0`” (gap-stress)

- Đối chiếu `DEPLOYMENT_PLAN_VI.md` mục gap-stress: phút tệ nhất không trần lỗ 58% vốn, trần 2x còn 33,5% (3x: 39%), trung vị/p99 không đổi; lợi nhuận G2 5,41 vs D17BF 5,43 %/tháng, DD 16,9 vs 18,3. Sổ tay ghi đúng số.
- Vấn đề: đây là kết quả engine/backtest, nhưng CẢNH BÁO mới nói bot cài cap CHẶT HƠN engine (tháng 9 bot +1,1% vs không trần +3,6%). Tức con số “lợi nhuận giữ nguyên” chưa đúng cho bot hiện tại. Xem ISSUE-01.

### 1h. Live bị khóa cứng / vốn nhỏ / một runner mỗi state dir

- Kiểm code: live lock đúng (mục 1e); `runner.lock` + `sys.exit("another bot runner holds ...")` đúng trong `bot/run.py:512,537` (chỉ khi không `--once`). Trên máy đang có `runner.lock` trong `paper`, `paper_d17bf`, `paper_d17bfg2`, `paper_g2k20`… và backend processes=2, tunnel=1 (mục 2) — chứng tỏ nhiều runner đang chạy song song khác tag, đúng quy tắc “một runner cho mỗi thư mục state”.
- Thông điệp lock thực tế là `another bot runner holds <path>/runner.lock`; sổ tay ghi `another bot runner holds .../runner.lock` — KHỚP.

## 2. Nguồn plan: backend phải chạy

### 2a. Backend + `-Status`

- Lệnh đã chạy (chỉ đọc, không start/stop): `powershell.exe -NoProfile -ExecutionPolicy Bypass -File run_backend.ps1 -Status`
- Kết quả: `Backend processes: 2 (background supervisor: 0) | tunnel connectors: 1 / Local health: ok. / Public https://api-crypto.nguyenchitrai.id.vn/health : OK / EXIT:0`.
- Khớp mô tả `.\run_backend.ps1` rồi `.\run_backend.ps1 -Status`: CÓ. Backend local + public đều OK, không cần dựng lại.
- Chưa rõ: sổ tay chỉ liệt kê foreground (`.\run_backend.ps1`) và `-Status`, không nhắc `-Background` (chạy ẩn, log `artifacts\web\backend.log`), `-Stop`, `-Ensure`/`-AccessLog` vốn có trong `run_backend.ps1`. Đặc biệt foreground có `Stop-All` (“one instance only: replaces a background or older run”) — người mới gõ `.\run_backend.ps1` theo mục 4 sẽ giết instance đang chạy. Xem ISSUE-05.

### 2b. Plan `trade_plan_v376.json` + `generated_at`

- Kiểm: file `artifacts/research/advisor_shadow/trade_plan_v376.json` tồn tại; `generated_at=2026-10-06T02:01:00.771038+00:00`; lúc kiểm age ~0.5h (< 4h30m) nên bot không chặn lệnh mới. `bot_health.py` cũng báo `plan age 0.5h`. Mở JSON thấy các key `generated_at, decision_bar, phases, pipeline...`.
- Sổ tay nói “backend làm tươi mỗi giờ qua scheduler” — code `backend/server.py` có job phase-plan hourly (`_run_phase_plans("hourly")`) + cycle 4h (+8 min theo header `run_backend.ps1`) + candles 15 min. Nói “mỗi giờ” là GẦN ĐÚNG cho plan v376 nhiều phase, nhưng chưa chính xác cho pipeline chính 4h. Nên ghi rõ “phase plan mỗi giờ, cycle chính mỗi 4h” (ISSUE-09).

### 2c. “Plan quá 4h30m là cũ: bot chặn lệnh mới, chỉ giữ bảo vệ, log `stale_plan`”

- Kiểm code: `bot/run.py:30 STALE_PLAN = pd.Timedelta(hours=4, minutes=30)`; khi stale chỉ giữ `tp/stop/reduce` + log `op=stale_plan`. `scripts/bot_health.py:27 PLAN_STALE_H = 4.5`, plan cũ → warning `plan age ... (>4h30m)`. Hôm nay `stale_plan` 24h: d17bfg2=52, d17bf=281, g2k20=83, paper=355 — tức đã từng stale trong 24h nhưng hiện tại plan tươi nên [OK].
- Khớp: CÓ với `BOT_RUNBOOK_VI.md`.
- Mâu thuẫn tài liệu: `docs/BOT_EXECUTION.md` dòng 26 lại ghi “a plan older than 2 h blocks new entries”. Sai so với code/runbook (4h30m). Xem ISSUE-03.

## 3. Kiểm tra hằng ngày (5 phút)

### 3a. Hai lệnh daily

- Đã chạy: `scripts/bot_health.py artifacts/bot/paper_d17bfg2` (mục 1c, [OK]) và `scripts/prospective_scorecard.py` (không tham số).
- `prospective_scorecard.py` chạy xong, in bảng lớn nhiều pipeline; hàng `bot_paper_d17bfg2`: `R2B1D17BFG2 (v421) 5.41 %/tháng, DD 16.91, config R2B1D17BF + --dip-gross-cap 2.0 (deployment)`, `started 2026-10-05 17:51 UTC`, cột go_live/stop đầy đủ. Hàng `bot_paper_g2k20`, `bot_paper_d17bf`, `bot_paper` cũng có.
- Khớp: CÓ. Nhưng sổ tay không nhắc `scripts/paper_report.py` (công cụ so sánh bot side-by-side), trong khi assignment ops_runbook lại yêu cầu nó. Đã chạy thêm: `./.venv/Scripts/python.exe scripts/paper_report.py artifacts/bot/paper_d17bfg2 artifacts/bot/paper_d17bf artifacts/bot/paper_g2k20` → bảng `return -0.00%, maxDD 0.01%, dip 0/book 3 fills, open 3, stale_plan/errors` — hữu ích và an toàn. Nên đưa vào daily (ISSUE-07).

### 3b. Ý nghĩa từng dòng `bot_health.py` (exit 0/1/2)

- `last_cycle ... age`: ĐÚNG. Code: critical nếu `>3*interval (>60s với vòng 20s)` hoặc `>5 phút` (`CRITICAL_CYCLE_S=300`). Hôm nay age 11–25s → [OK]. Sổ tay bảo “khởi động lại lệnh mục 1, kiểm tra `runner.log`, Task Manager xem tiến trình cũ còn giữ `runner.lock`” — trên Windows lệnh đúng là kiểm tra `runner.lock` + `Get-Process`, không chỉ Task Manager; và khởi động lại phải đúng `--tag` (ISSUE-05).
- `plan age ... (>4h30m)`: ĐÚNG (warning, bot chỉ giữ thoát lệnh). Hôm nay 0.5h → không warning.
- `24h ops place/amend/cancel/fill/market_exit/stale_plan/errors`: ĐÚNG định dạng. `errors>0 = warning (xem 5 dòng lỗi kèm theo; rate_limit/10006 → đợi, giảm tần suất)` — khớp code `ERROR_OPS=("error","cycle_error")`, `rate_limit` đếm riêng, chỉ lưu 5 note đầu. Hôm nay `paper` có 15 errors toàn rate-limit → [WARNING] đúng; 3 dir d17bf* errors=0.
- `cycle_error kéo dài >1 giờ = mất go-live`: tên `cycle_error` KHÔNG xuất hiện trong output `bot_health.py` (bị gộp vào `errors`). Muốn biết kéo dài >1h phải `grep cycle_error actions.jsonl` và xem timestamp. Sổ tay không chỉ cách grep. Xem ISSUE-04.
- `unprotected=[...]`: ĐÚNG là CRITICAL khi vị thế mở thiếu stop hoặc TP. Code kiểm cả hai (`stop_ok and tp_ok`), `unprotected_close` sau >2 cycles (code `run.py:454,490`). Hôm nay `unprotected=none` ở cả 4 dir. Sổ tay bảo “bot tự đặt lại trong <=20s, quá 2 vòng không stop sẽ đóng market” — khớp code (vòng 20s, ngưỡng 2 min cho `exit_sent`, flatten sau >2 cycles). Muốn xác minh phải mở `actions.jsonl` — nên ghi rõ lệnh grep (ISSUE-06).
- `qty_mismatch=[...]`: ĐÚNG là CRITICAL, “sàn là sự thật; không sửa tay `state.json`”. Hôm nay `none`. Với paper, “sàn” là `exchange.json` mô phỏng (code so `ledger` vs `exchange.pos`); với live/testnet mới là sàn thật — sổ tay không phân biệt, dễ hiểu nhầm (ISSUE-06).
- `equity ... maxDD`: ĐÚNG (lãi/lỗ + DD từ đầu paper). Hôm nay d17bfg2 `4,999.84 vs 5,000.00 (pnl -0.16) maxDD=0.01%`. So với ngưỡng dừng mục 6 thì còn rất xa (mới chạy <1 ngày, chưa kết luận được).
- `fills24h / closed W/L`: ĐÚNG “chỉ tham khảo ngắn hạn”. Hôm nay `dip=0 book=3, closed 0/0`.
- `missing actions.jsonl / state.json`: ĐÚNG. Đã kiểm dir sai → `CRITICAL: missing actions.jsonl`, `warning: missing state.json`, exit 2. Sổ tay bảo “kiểm tra lại `--tag`” — chính xác vì sai tag sẽ ra thư mục khác (`artifacts/bot/<mode>_<tag>`).

## 4. Sau reboot / mất điện / mất mạng: khởi động lại bằng tay

Không reboot, không start/stop (đúng cấm). Chỉ kiểm tĩnh + đọc:

1. `.\run_backend.ps1`, chờ `-Status` báo local OK, xác nhận `trade_plan_v376.json` có `generated_at` mới (<4h30m). Hôm nay `-Status` đã OK + plan 0.5h nên bước này nếu reboot sẽ đạt. Vấn đề foreground giết background như mục 2a (ISSUE-05).
2. Chạy lại đúng một runner mỗi mode bằng lệnh mục 1 (đúng `--tag d17bfg2`). Nếu báo `another bot runner holds .../runner.lock` là còn tiến trình cũ — đừng chạy đè. ĐÚNG với code `single_instance` + `sys.exit`. Nên bổ sung cách tìm tiến trình cũ (`Get-Process`, `artifacts/bot/<dir>/state.json` mtime, `stdout.log`) thay vì chỉ “Task Manager” (ISSUE-05).
3. Đối chiếu `actions.jsonl` với vị thế thật trên Bybit: stop/TP thiếu đặt lại <=20s; mảnh plan đã thoát mà sàn còn mở bị đóng market sau ~3 phút (`plan_closed_divergence`). ĐÚNG với code (`mirror.py:691`, `run.py:299` + close sau 3 min theo BOT_EXECUTION). Với paper hôm nay open=3, unprotected=none nên không có gì để đối chiếu thêm. Sổ tay không cho lệnh grep mẫu (ISSUE-06).
4. Mất mạng dài: stop market + TP limit reduce-only đã nằm trên sàn vẫn bảo vệ; hở duy nhất là mảnh vừa khớp chưa kịp đặt exit (cửa sổ <=20s). ĐÚNG với caveat `BOT_EXECUTION.md:32` (“a new fill has no exit orders until the next cycle (<=20s)”). Người mới nên được dặn kiểm tay thế nào khi mạng trở lại (mở Bybit positions vs `bot_health.py`) — hiện chỉ nói “kiểm tra tay” chung chung (ISSUE-05).

## 5. Vốn, margin, đòn bẩy

- Tối thiểu 5000 USDT, tốt nhất ~10000; dưới mức bậc dip BTC <0,001 BTC bị bỏ (`skipped_below_minimum`): 10.000 đặt 100%/98%, 5.000: 96%/94%, 2.000: 80%/81%. Đối chiếu `DEPLOYMENT_PLAN_VI.md` mục 2 + `oc_lots`: ĐÚNG số. Bằng chứng trên máy: `stdout.log` của `paper_d17bfg2` hôm nay đã có nhiều `op=skipped_below_minimum links=["d2SOL30hrvncE"]` dù equity 5000 — tức ngay vốn khuyến nghị vẫn có rung bị bỏ (phù hợp 94% dip). Sổ tay không nói operator xem `skipped_below_minimum` ở đâu (`actions.jsonl`/`stdout.log`) (ISSUE-06).
- Sàn Bybit, cross margin; notional dip không trần tới ~6,4x vốn, trần 2x còn ~2x; đòn bẩy cài thấp sẽ thiếu margin. Không thay đổi đòn bẩy trong lần kiểm (đúng cấm). Sổ tay không ghi con số đòn bẩy cụ thể cần đặt trên Bybit + đặt ở đâu (cross vs isolated, chỗ chỉnh leverage) — người mới dễ đặt sai (ISSUE-10).
- Máy chạy 24/7 (BOT cần trực; MANUAL không cần). ĐÚNG, không có gì để chạy thêm.

## 6. Kỳ vọng thực tế + go-live / dừng (từ DEPLOYMENT_PLAN_VI.md)

Đã đối chiếu từng dòng với `DEPLOYMENT_PLAN_VI.md`, không chạy backtest:

- Kỳ vọng R2B1D17BF trung vị ~5%/tháng, năm xấu ~3%/tháng, DD tới ~18%: KHỚP (plan mục Rủi ro + Rolling + KPI).
- Cửa sổ 12 tháng trượt 49 cửa sổ (min 2,73 / p10 3,25 / trung vị 4,89 / p90 8,88 / max 11,71; DD min 8,3 / trung vị 13,5 / p90 18,3 / max 18,7; 49% >=5%/tháng, 61% DD<15, 100% DD<20): KHỚP nguyên văn.
- Bootstrap 10.000 năm (trung vị ~5,1, p5 1,5/p95 10,3, ~52% năm >=5%; DD trung vị 14,5/p95 22,6; P(DD>20%) ~11%; P(năm lỗ) ~0,7%; chịu DD 25%): KHỚP.
- KPI (41% tháng >=+5%, 72% tháng không lỗ, chuỗi lỗ dài nhất 2 tháng; book 51,5/dip 68,7/tổng 65,5): KHỚP.
- Go-live tiền thật nhỏ (sau tối thiểu 8 tuần paper, ĐỦ cả 4: (a) paper percentile >=20 của bootstrap (`prospective_scorecard.py`); (b) DD <=15%; (c) lệch bot vs plan <=1,5pp/tháng; (d) không `cycle_error`>1h, không thiếu stop; tăng vốn sau 3 tháng live nếu (a)–(c) vẫn đúng): KHỚP DEPLOYMENT_PLAN mục 2. Hôm nay mới chạy <1 ngày (`paper_d17bfg2` 0.38 ngày, live_pct -0.003, percentile NaN vì thiếu baseline bootstrap cho tag mới) nên CHƯA đủ điều kiện — đúng, không được live.
- Dừng (DD>20% dừng mở mới chỉ giữ SL/TP; lỗ tháng >10% halve vốn tháng sau; percentile <5 sau >=8 tuần dừng): KHỚP.
- Lưu ý: `prospective_scorecard.py` không tham số in toàn bộ bảng; operator mới khó tìm hàng `bot_paper_d17bfg2`. Nên ghi rõ cách lọc + `--json` (ISSUE-07).

## Bảng vấn đề + văn bản sửa đề xuất (tiếng Việt)

| ID | Vị trí trong sổ tay | Vấn đề (đã kiểm chứng) | Văn bản sửa đề xuất (tiếng Việt) |
|---|---|---|---|
| ISSUE-01 | CẢNH BÁO dòng 8–10 vs mục 1 dòng 17–21, 34–35 | Mâu thuẫn hành động: CẢNH BÁO bảo “chạy KHÔNG có `--dip-gross-cap` hoặc chấp nhận lợi nhuận thấp hơn” vì bot cài chặt hơn engine (09/2026 +1,1% vs +3,6%), nhưng mục 1 vẫn gọi `--dip-gross-cap 2.0` là “khuyến nghị” và giữ lý do gap-stress “lợi nhuận giữ nguyên (~5,41 vs 5,43)”. Người mới không biết chọn bên nào. | Thay CẢNH BÁO + đầu mục 1 bằng: “**TẠM THỜI (từ 2026-10-06 tới khi có bản bot_capfix): lệnh mặc định để paper là KHÔNG có `--dip-gross-cap` (bỏ flag). Lệnh có `--dip-gross-cap 2.0` chỉ dùng cho runner so sánh `paper_d17bfg2` và không dùng để kết luận lợi nhuận. Sau khi bản sửa được merge và parity đạt, mới quay lại lệnh 4-flag ở mục 1.**” |
| ISSUE-02 | Mục 1 (danh sách cờ) | Thiếu `--adopt-fresh`: cờ tồn tại trong `bot/run.py --help` và `BOT_EXECUTION.md` (“adopt a fresh paper book position… default off”), mặc định off nên lệnh mục 1 không đổi, nhưng operator không biết khi nào cần. Sổ tay không nhắc một chữ nào. | Thêm sau dòng 4-flag: “`--adopt-fresh` mặc định TẮT, không thuộc pipeline khuyến nghị. Chỉ bật khi được yêu cầu bằng văn bản để nhận lại vị thế book còn tươi mà bot đã bỏ lỡ (cửa sổ 5–65 phút sau entry, lệnh limit đúng giá engine, có stop/TP). Mặc định không thêm flag này.” |
| ISSUE-03 | Mục 2 dòng 49 vs `BOT_EXECUTION.md` dòng 26 | Lệch ngưỡng stale giữa tài liệu: runbook + code (`STALE_PLAN=4h30m`, `PLAN_STALE_H=4.5`) là 4h30m, nhưng `BOT_EXECUTION.md` ghi “a plan older than 2 h blocks new entries”. Người mới đọc kỹ thuật sẽ hiểu sai. | Sửa `BOT_EXECUTION.md` dòng 26 thành: “Safety: a plan older than 4h30m blocks new entries (exits keep running); …” và giữ nguyên runbook 4h30m. |
| ISSUE-04 | Mục 3 dòng 63 (`cycle_error` >1h) | `bot_health.py` không có cột `cycle_error` riêng (gộp vào `errors`; code `ERROR_OPS=("error","cycle_error")`, chỉ hiện 5 note). Operator không thể kiểm “kéo dài >1 giờ” từ output health. Đã kiểm: `paper` có 15 errors nhưng không biết có `cycle_error` nào. | Sửa thành: “`errors` > 0 = warning. Để kiểm `cycle_error` kéo dài >1 giờ, chạy: `Select-String -Path artifacts/bot/paper_d17bfg2/actions.jsonl -Pattern cycle_error \| Select-Object -Last 20` (hoặc `grep cycle_error ...`), xem timestamp `t`; nếu cùng lỗi lặp >1 giờ thì mất điều kiện go-live.” |
| ISSUE-05 | Mục 3 dòng 61 + mục 4 (restart) + `run_backend.ps1` | Thiếu/hở hướng dẫn khởi động lại: (a) `.\run_backend.ps1` foreground có `Stop-All` (giết instance đang chạy) nhưng sổ tay không cảnh báo; (b) không nhắc `-Background` (chạy ẩn, log `artifacts\web\backend.log`), `-Stop`, `-Ensure`; (c) chỉ nói “Task Manager xem `runner.lock`” mà không cho lệnh thay thế; (d) không nói rõ ánh xạ `--tag` ↔ `artifacts/bot/<mode>_<tag>`. | Thêm hộp “Khởi động lại an toàn”: “Backend đang chạy thì CHỈ dùng `.\run_backend.ps1 -Status` để kiểm. Muốn chạy nền: `.\run_backend.ps1 -Background` (log `artifacts\web\backend.log`); dừng: `.\run_backend.ps1 -Stop`. KHÔNG gõ `.\run_backend.ps1` foreground khi backend đang chạy vì nó thay thế instance cũ. Bot: chạy lại đúng `--tag` (ví dụ `d17bfg2` ↔ `artifacts/bot/paper_d17bfg2`); nếu báo `another bot runner holds .../runner.lock` thì tìm tiến trình cũ bằng `Get-Process python` + xem `state.json` (mtime) và `stdout.log`, không chạy đè.” |
| ISSUE-06 | Mục 3 dòng 64–65, 68 + mục 4 bước 3 + mục 5 | Các tên nội bộ (`unprotected_close`, `plan_closed_divergence`, `sync_fills`/`seen_exec`, `skipped_below_minimum`) được nêu nhưng không chỉ chỗ xem. Với paper, “sàn là sự thật” thực chất là `exchange.json` mô phỏng, không phải Bybit thật — dễ hiểu nhầm. | Thêm: “Với paper, ‘sàn’ là `artifacts/bot/<dir>/exchange.json`; với live/testnet mới là Bybit thật. Kiểm nhanh: `Select-String -Path artifacts/bot/paper_d17bfg2/actions.jsonl -Pattern 'unprotected_close\|plan_closed_divergence\|skipped_below_minimum\|stale_plan' \| Select-Object -Last 20`. Không sửa tay `state.json`.” |
| ISSUE-07 | Mục 3 dòng 54–57 | Thiếu `paper_report.py`: assignment ops yêu cầu nó và nó hữu ích (side-by-side paper), nhưng runbook daily chỉ liệt kê `bot_health.py` + `prospective_scorecard.py`. Ngược lại `prospective_scorecard.py` không tham số in bảng rất rộng, người mới khó tìm hàng bot. | Sửa mục 3 thành: “```bat\n.venv\\Scripts\\python.exe scripts/bot_health.py artifacts/bot/paper_d17bfg2\n.venv\\Scripts\\python.exe scripts/paper_report.py artifacts/bot/paper_d17bfg2 artifacts/bot/paper_d17bf artifacts/bot/paper_g2k20\n.venv\\Scripts\\python.exe scripts/prospective_scorecard.py\n``` Tìm hàng `bot_paper_d17bfg2` (cột `percentile`, `config`, `go_live`, `stop`); mới chạy <8 tuần thì `percentile` có thể NaN là bình thường.” |
| ISSUE-08 | Mục 1 (testnet/live/equity/shell) | Thiếu chi tiết thực thi: (a) testnet không nêu tên biến `.env` (`BYBIT_TESTNET_API_KEY/SECRET` theo `BOT_EXECUTION.md`); (b) live `set BOT_ALLOW_LIVE=...` là cú pháp `cmd`, trên PowerShell phải `$env:BOT_ALLOW_LIVE="yes-real-money"`; (c) `--equity 5000` cho dry/paper nhưng testnet/live không có `--equity` (vốn lấy từ sàn) — không giải thích; (d) dry `--once` mặc định `--mode dry`, không giữ lock — không nói; (e) ví dụ dùng `REM` (cmd) lẫn `.\run_backend.ps1` (PowerShell) gây lẫn shell. | Thêm chú thích shell + biến: “Dùng `cmd`: `set BOT_ALLOW_LIVE=yes-real-money`; dùng PowerShell: `$env:BOT_ALLOW_LIVE='yes-real-money'`. Testnet cần `BYBIT_TESTNET_API_KEY` + `BYBIT_TESTNET_API_SECRET` trong `.env` (không commit, không dán vào chat). `--equity` chỉ dùng cho dry/paper; live/testnet lấy vốn thật trên sàn. Dry `--once` mặc định `--mode dry`, không giữ `runner.lock`.” |
| ISSUE-09 | Mục 2 dòng 41 (“backend làm tươi mỗi giờ”) | Chưa chính xác lịch scheduler: code có phase-plan hourly (`_run_phase_plans("hourly")`) + cycle chính mỗi 4h close (+8 min) + candles 15 min (header `run_backend.ps1`, `backend/server.py`). Nói “mỗi giờ” khiến người mới tưởng mọi plan đều hourly. | Sửa thành: “Backend làm tươi plan phase v376 mỗi giờ (đúng grid từng phase), cycle pipeline chính sau mỗi nến 4h (+8 phút), candles mỗi 15 phút. Plan hiển thị `generated_at`; quá 4h30m là cũ.” |
| ISSUE-10 | Mục 5 (cross margin, đòn bẩy) | Khuyến nghị “đặt mức đòn bẩy tài khoản đủ cao” nhưng không ghi số/bybit UI: notional không trần ~6,4x vốn, trần 2x còn ~2x (theo DEPLOYMENT_PLAN). Người mới/Việt Nam dễ để leverage thấp → thiếu margin đặt đủ rungs, hoặc đặt isolated nhầm. | Thêm: “Trên Bybit đặt tài khoản **Cross margin**, chỉnh đòn bẩy (Leverage) đủ cho notional tối đa (~6,4x vốn nếu không trần; ~2x nếu trần 2x). Không dùng Isolated cho bot. Nếu thấy nhiều `skipped_below_minimum` hoặc thiếu margin, dừng và hỏi chủ tài khoản trước khi đổi đòn bẩy.” |
| ISSUE-11 | Mục 2–3 (`-Status`, health chữ Việt) | Lỗi hiển thị tiếng Việt trên máy kiểm: `run_backend.ps1 -Status` in `Local health: ok. Đăng nhập dashboard...` bị mojibake trong shell thu log (`�?��ng nh��-p...`), do console không UTF-8. Không chặn vận hành nhưng người mới dễ tưởng lỗi. | Thêm vào script hoặc runbook: “Nếu chữ Việt hiện lỗi font trong terminal, chạy `chcp 65001` trước, hoặc đọc `artifacts\web\backend.log`. Đây là lỗi font, không phải backend lỗi (căn cứ `Local health: ok` + `Public ... : OK`).” |

## Kết luận cho operator mới

- Sổ tay ĐÚNG ở phần cốt lõi đã kiểm an toàn: 4 flag tồn tại, dry `--once` không gửi lệnh, `bot_health.py` + exit codes đúng, plan `trade_plan_v376.json` tươi (0.5h), backend local+public OK, 3 paper runner [OK] (`paper` WARNING rate-limit là bình thường), `prospective_scorecard.py` chạy được, lock `runner.lock` + live lock đúng code.
- CHƯA ĐẠT để live: mới paper <1 ngày, percentile NaN, chưa đủ 8 tuần và 4 điều kiện mục 6. Tiếp tục paper + health daily.
- Ưu tiên sửa trước khi giao cho người không chuyên: ISSUE-01 (chọn cap hay không cap), ISSUE-05 (restart/backend foreground), ISSUE-08 (shell/testnet/live vars), ISSUE-03 (2h vs 4h30m), ISSUE-04/06 (cách grep `cycle_error`/locks/divergence).

---
*Phạm vi kiểm: chỉ các bước an toàn (không start/stop backend/bot, không chạm `.env`, không gửi lệnh). Các lệnh loop paper/testnet/live, đổi leverage, sửa backend/bot không được thực thi.*
