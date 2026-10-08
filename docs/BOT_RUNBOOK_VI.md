# Sổ tay vận hành BOT (G2 + carry f=0.25, một Bybit UTA)

> Triển khai duy nhất: BOT G2 = R2B1D17BF + trần dip 2x (`--corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0 --adopt-fresh --carry-f 0.25 --interval 25`, plan `trade_plan_v376.json`, v421/v422 twin numbers, v422 audited: 5,41/worst 2,588 %/tháng, DD 16,91/toàn đường 16,82) + sleeve carry quý `f=0,25` trên CÙNG một Bybit UTA.
> Code-review bot F1-F7 + N1-N4 ĐÃ SỬA (commit 359004f, bot_reviewfix; 124 test bot xanh): testnet có carry (--carry-f 0.25) nay được phép — vẫn bắt buộc preflight PASS và testnet sạch 7 ngày trước live.
> Kỳ vọng, ngưỡng go-live/dừng lấy nguyên văn từ `docs/DEPLOYMENT_PLAN_VI.md` (đăng ký trước 2026-10-05, không sửa sau khi thấy dữ liệu paper).
> Chi tiết kỹ thuật: `docs/BOT_EXECUTION.md` (các mục CHANGES), code `bot/run.py`. Lịch testnet 7 ngày: `docs/TESTNET_PLAN_VI.md`. Bắt đầu nhanh: `docs/QUICKSTART_VI.md`.
> Mọi lệnh chạy từ repo root. Windows dùng `.venv\Scripts\python.exe`. GIT READ-ONLY: không bao giờ stash/reset/checkout/clean/commit.

## 1. Cài đặt một lần (chủ tài khoản làm tay, bot không tự làm)

- Bybit UTA, **Cross margin + Hedge Mode**, đòn bẩy perps **5x từng coin** BTC/ETH/SOL/BNB/XRP (Bybit chỉnh theo từng coin; 5x là mức tối thiểu không bao giờ chặn lệnh ở cap 2.0; 10x/20x không an toàn hơn trong cross). Chân short quarterly của carry để **10x** (đã hedge bằng spot tiền thật); không vượt `f=0,25` chung UTA (`f=0,50` bị chặn margin). Không hạ đòn bẩy khi đang có vị thế; Bybit không cho đổi margin khi có vị thế.
- Vốn **tối thiểu 5000 USDT, tốt nhất ~10000 USDT** (dưới mức này rung dip BTC < 0,001 BTC bị bỏ, log `skipped_below_minimum` — là skip bình thường, không phải lỗi).
- Secrets chỉ trong `.env` local (không commit, không dán chat): testnet `BYBIT_TESTNET_API_KEY` + `BYBIT_TESTNET_API_SECRET`; live `BYBIT_API_KEY` + `BYBIT_API_SECRET`. Xác nhận `BOT_ALLOW_LIVE` CHƯA set (để `--mode live` luôn bị từ chối) cho tới ngày live.
- Dựng backend TRƯỚC bot (backend làm tươi `artifacts/research/advisor_shadow/trade_plan_v376.json` mỗi giờ). Backend đang chạy thì CHỈ dùng `-Status` để kiểm; muốn chạy nền `-Background` (log `artifacts\web\backend.log`); dừng `-Stop`. Không gõ foreground đè khi backend đang chạy.

```bat
.\run_backend.ps1 -Status
REM Chỉ khi backend chưa chạy: .\run_backend.ps1 -Background
REM Dừng: .\run_backend.ps1 -Stop
```

- Plan quá **4h30m** là cũ: bot chặn lệnh mới, chỉ giữ bảo vệ (stop/TP, thoát lệnh vẫn chạy), log `stale_plan`. Việc đầu tiên là dựng lại backend, không ép bot vào lệnh. Kiểm tra nhanh `generated_at` trong `trade_plan_v376.json`; `bot_health.py` cũng báo tuổi plan.
- Sau MỌI lần cập nhật code thêm route API mới (ví dụ `/api/carry`): chủ tài khoản phải restart backend tay (`-Stop` rồi `-Background`) thì route mới mới có hiệu lực; `restart_all.sh` không restart backend đang healthy.

## 2. Lệnh chuẩn (đóng băng — thiếu một flag là thành pipeline khác)

Ý nghĩa flags: `--corr-size` (size dip theo tương quan) + `--dip-mult 1.7` (hệ số dip) + `--bear-book` (giảm nửa book long khi bear) + `--dip-gross-cap 2.0` (trần dip khớp engine: mỗi bid chờ <= 2x vốn sub-book trừ notional dip đang mở; trần cứng 4x; giữ ~nguyên lợi nhuận, cắt lỗ phút gap -10 % cả 5 coin từ 58 % xuống 33,5 % vốn) + `--carry-f 0.25` (sleeve carry, mỗi chân 0,25x vốn; legs carry link prefix `c`, không tính vào trần dip, short futures/coin <= 0,30x vốn). `--adopt-fresh` mặc định TẮT trong code; lệnh đóng băng triển khai BẬT `--adopt-fresh` ở mọi mode (dry/paper/testnet/live) để nhận lại vị thế book còn tươi (cửa sổ 5–65 phút sau entry). `--equity` chỉ dùng cho dry/paper; testnet/live lấy vốn thật. Risk guard BẬT mặc định ở testnet/live (không thêm `--no-risk-guard`); paper/dry mặc định TẮT. Entry book/dip là PostOnly maker (`postonly_reject` = thử lại cùng giá chu kỳ sau, không đuổi giá); TP GTC reduce-only; stop là conditional market reduce-only.

```bat
REM Chạy thử khô (không gửi lệnh):
.venv\Scripts\python.exe -m bot.run --once --equity 5000 --corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0 --adopt-fresh --carry-f 0.25 --interval 25

REM Paper triển khai G2 + carry (runner so sánh d17bfg2c, >= 8 tuần, một runner/một thư mục state):
.venv\Scripts\python.exe -m bot.run --mode paper --equity 5000 --corr-size --dip-mult 1.7 --dip-gross-cap 2.0 --bear-book --adopt-fresh --carry-f 0.25 --interval 25 --tag d17bfg2c

REM Preflight chỉ-đọc (bắt buộc PASS/exit 0 trước testnet/live lần đầu và sau mỗi lần đổi key/settings):
.venv\Scripts\python.exe scripts/bot_preflight.py --mode testnet
.venv\Scripts\python.exe scripts/bot_preflight.py --mode live

REM Testnet 7 ngày (đóng băng, tag riêng, không trùng paper; vốn testnet nhỏ):
.venv\Scripts\python.exe -m bot.run --mode testnet --corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0 --adopt-fresh --carry-f 0.25 --interval 25 --tag tnetg2c

REM Live (KHÓA — chỉ chủ tài khoản mở sau testnet sạch + đủ 4 điều kiện mục 8):
REM cmd: set BOT_ALLOW_LIVE=yes-real-money
REM PowerShell: $env:BOT_ALLOW_LIVE="yes-real-money"
REM .venv\Scripts\python.exe -m bot.run --mode live --corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0 --adopt-fresh --carry-f 0.25 --interval 25 --tag liveg2c
```

- Một runner cho mỗi thư mục state (khóa OS `runner.lock`). Báo `another bot runner holds .../runner.lock` = còn tiến trình cũ: kiểm `Get-Process python` + mtime `state.json`/`stdout.log`, không chạy đè. Không sửa tay `state.json` (sàn là sự thật khi lệch).

## 3. Routine hằng ngày (~5–10 phút) + watcher + báo cáo tuần

```bat
.venv\Scripts\python.exe scripts/daily_status.py
.venv\Scripts\python.exe scripts/bot_health.py artifacts/bot/paper_d17bfg2c
.venv\Scripts\python.exe scripts/paper_report.py artifacts/bot/paper_d17bfg2c
.venv\Scripts\python.exe scripts/prospective_scorecard.py
.venv\Scripts\python.exe scripts/paper_divergence.py artifacts/bot/paper_d17bfg2c
Select-String -Path artifacts/bot/paper_d17bfg2c/actions.jsonl -Pattern 'unprotected_close|plan_closed_divergence|skipped_below_minimum|stale_plan|postonly_reject|risk_reject|carry_unhedged|carry_close|carry_settle|protection_check|slow_cycle|lock_wait|cycle_error|maint_cancel|maint_resume' | Select-Object -Last 30
```

- `daily_status.py` là điểm bắt đầu: backend + tuổi plan, mọi `artifacts/bot/paper*`, collector, mục 6 edge monitor, một dòng OK/WARNING/CRITICAL. Chỉ đọc file, không chạm `.env`, không start/stop process. `bot_health.py` soi chi tiết khi WARNING/CRITICAL (exit 0 ok / 1 warning / 2 critical): `last_cycle age` > 5 phút = runner chết; `errors` > 0 = đọc 5 dòng lỗi (`rate_limit`/10006 = chạm giới hạn Bybit → đợi); `cycle_ms` > 60s = `slow_cycle`; `lock_wait` = chờ khóa cache > 10s. `cycle_error` cùng lỗi > 1 giờ = mất điều kiện go-live. `paper_divergence.py` trước 14 ngày báo `too early` là bình thường.
- Watcher CRITICAL (chủ tự chạy tay, chỉ đọc file local, không network/credentials; 6 mục: thiếu stop/TP, lệch số liệu, cycle > 5 phút, plan > 4h30m, stop rule STOP, carry lệch hedge > 2 cycle; toast 1 lần/incident mới + log `artifacts/alerts/alerts.log`):

```bat
REM Chạy nền mỗi 300s (toast Windows + log):
.venv\Scripts\python.exe scripts/alert_watch.py --every 300
REM Kiểm tra một lần, không toast:
.venv\Scripts\python.exe scripts/alert_watch.py --once --no-toast
```

- Báo cáo tuần (chỉ đọc; markdown ra stdout + `artifacts/reports/weekly_<ISO-week>.md`; runner `paper_d17bfg2`/`paper_d17bfg2c` + ledger carry, tuần/từ-đầu return/DD/fills, win rate book/dip/carry, divergence, edge, stop-rule, số ngày bằng chứng vs tối thiểu 56 ngày, tóm tắt 3 dòng):

```bat
.venv\Scripts\python.exe scripts/weekly_report.py
```

- Sổ paper carry riêng (luật đóng băng `research/tournament/oc_cashcarry/PLAN.md`: quarterly kế tiếp khi front còn <= 7 ngày hoặc lần đầu có hàng, chỉ khi basis năm hóa `ln(F/S)*365/DTE >= 4 %`, long spot + short quarterly bằng notional, mỗi chân `f` x vốn lúc vào, giữ tới delivery; phí spot taker 0,1 %/bên, futures vào 0,055 %, giao hàng 0,02 %; chỉ đọc endpoint công khai Bybit, không key):

```bat
.venv\Scripts\python.exe scripts/carry_paper.py --once --equity 5000 --f 0.5 --tag carry
```

## 4. Bảo trì có kế hoạch (bot_maint)

- Trước bảo trì ĐỊNH KỲ: đặt cửa sổ để bot tự hủy bid dip chờ + không vào book mới (từ trước giờ bắt đầu 30 phút tới hết giờ kết thúc; stop/TP/backstop và chân carry giữ nguyên trên sàn). Cách khuyên dùng là file (bot đọc mỗi vòng 20s, sửa/xóa không cần restart); mặc định không flag/không file = chạy y hệt cũ.

```bat
REM artifacts/bot/paper_d17bfg2c/maintenance.json = {"start": "2026-10-07T01:00:00Z", "end": "2026-10-07T03:00:00Z"}
REM Hoặc flag lúc khởi động: --maint-start 2026-10-07T01:00:00Z --maint-end 2026-10-07T03:00:00Z
```

- Kiểm tra `actions.jsonl`: `op=maint_cancel` (đã chặn/hủy) rồi `op=maint_resume` (chạy lại). Tốn routine chỉ 1–2,5 % lãi dip 5 năm.
- Testnet bảo trì: file tương ứng là `artifacts/bot/testnet_tnetg2c/maintenance.json`.

## 5. Sau reboot / mất điện / mất mạng (restart_all, làm thay mục tay)

Bot và backend **không tự chạy lại**. Script idempotent (chỉ đọc process, không bao giờ kill; chạy lần hai không khởi động gì thêm; không đặt `BOT_ALLOW_LIVE`, không bao giờ chạy testnet/live, backend chỉ local 127.0.0.1:8724, không tunnel công khai). Thứ tự: backend local -> paper runner (`--interval 25`; `d17bfg2c` kèm `--dip-gross-cap 2.0 --adopt-fresh --carry-f 0.25`) -> vòng carry (`carry_paper.py --once --equity 5000 --f 0.5 --tag carry` mỗi 3600s) -> `bot_health` + `daily_status`. `state.json` được sao lưu (`state.json.bak_<UTC>`) và kiểm tra JSON trước khi dựng.

```bat
REM Xem kế hoạch trước (không khởi động gì):
bash scripts/restart_all.sh --dry-run
REM PowerShell: .\scripts\restart_all.ps1 -DryRun
REM Khôi phục đủ:
bash scripts/restart_all.sh
REM Chỉ một nhóm:
bash scripts/restart_all.sh --only bots      (hoặc --only backend / --only carry: chọn MỘT giá trị)
```

- Sau MỌI restart: runner tự ghi `op=protection_check` (từng mảnh mở + stop/TP native còn trên sàn không). Người trực chạy `bot_health.py`: `CRITICAL: open without stop+TP` phải trống mới cho bot chạy tiếp; mảnh thiếu stop được đặt lại <= 20s, quá 2 vòng tự đóng market (`unprotected_close`); không đặt tay trong giờ đầu. Mất mạng dài: stop market + TP limit reduce-only trên sàn vẫn bảo vệ; hở duy nhất là mảnh vừa khớp chưa kịp đặt exit (cửa sổ <= 20s) — kiểm tra tay khi mạng về. Testnet/live sau reboot dựng BẰNG TAY (backend `-Status` + plan tươi, rồi đúng lệnh mục 2, đối chiếu `actions.jsonl` với vị thế thật).

## 6. Sao lưu file untracked (snapshot_untracked)

- Vì sao: file untracked không nằm trong git theo thiết kế (AGENTS.md: kết quả để local). Script chỉ ĐỌC git qua `git ls-files`, không bao giờ stash/reset/checkout/clean/commit hay sửa/xóa nguồn. Phạm vi: `research/`, `docs/opencode/`, `tests/`, `artifacts/bot/*/{state.json,actions.jsonl,exchange.json}` (loại `data/raw`, `models`, file > 50 MB, `__pycache__`). Zip đích `artifacts/backups/untracked_<UTC>.zip` + `manifest.json` (path/size/sha256); giữ 14 bản mới nhất. Chạy tay định kỳ trước các đợt dọn git và sau mỗi tuần paper.

```bat
REM Xem kế hoạch trước (không ghi gì):
.venv\Scripts\python.exe scripts/snapshot_untracked.py --dry-run
REM Chụp thật + tỉa bản cũ:
.venv\Scripts\python.exe scripts/snapshot_untracked.py
REM Liệt kê nội dung một bản (không ghi gì):
.venv\Scripts\python.exe scripts/snapshot_untracked.py --restore-list artifacts/backups/untracked_20261006T093559Z.zip   (thay bằng tên file zip thật trong artifacts/backups)
```

## 7. Playbook sự cố (dừng mở mới trước, điều tra sau)

- **Vị thế thiếu stop/TP (`unprotected=[...]` CRITICAL):** kiểm tra ngay `actions.jsonl` + vị thế thật (paper: `exchange.json`; live/testnet: Bybit thật); bot tự đặt lại <= 20s, quá 2 vòng tự đóng market (`unprotected_close`). Còn CRITICAL sau restart thì dừng bot, không đặt tay giờ đầu.
- **Lệch số liệu (`qty_mismatch=[...]` CRITICAL):** sàn là sự thật; đối chiếu `actions.jsonl` vs vị thế; không sửa tay `state.json`; dừng mở mới tới khi khớp.
- **Plan cũ (`stale_plan`, plan > 4h30m):** dựng lại backend (`-Status` → `-Background` nếu cần), chờ plan tươi; bot chỉ giữ exits là đúng, không ép vào lệnh.
- **Mất bot/outage bất ngờ:** ưu tiên xác nhận `protection_check` + `bot_health.py` hết CRITICAL mới cho bot chạy tiếp; không đặt tay giờ đầu; để bot tự exit ở phút mở đầu tiên khi trở lại. Crash COVID 03/2020 cho thang dip: mix 4 pha ~-16,1 %, pha đơn tệ nhất -21,8 % (vượt 20 %) — không bao giờ chạy 1 pha/1 đồng hồ đơn lẻ. Gap -10 % cả 5 coin nhảy qua mọi stop: phút tệ nhất có trần 2x lỗ ~33,5 % (không trần 58 %); gap -20 % không phút nào cháy; sau gap kiểm tra tay trước khi cho bot chạy tiếp.
- **Feed dữ liệu book chết (dòng tiền cá voi aggTrades / Coinbase premium) (2026-10-07, oc_memberdrop):** KHÔNG phải sự cố dừng giao dịch. Hai member dư thừa nhau: bỏ hẳn một member dev4 chỉ đổi ±0,02 điểm %/tháng (DD toàn đường +0,5); feed dòng tiền đông cứng 72h (10 lần/năm) tốn ≈ 0 (±25 bps/lần, dấu đổi theo năm). Cứ giữ book cuối, sửa feed trong vài ngày; KHÔNG đổi nóng sang book trọng số khác.
- **Carry lệch hedge (`carry_unhedged` quá 2 cycle):** bot tự đóng chân đã khớp (`carry_close`); dừng mở carry mới, kiểm tra minima/tick symbol dated + guard `carry_cap` 0,30x; không mở carry tay bù.
- **Ngày delivery:** BÁN chân spot đúng 08:00 UTC delivery (tốt nhất rải trong cửa sổ tính giá index) để khớp giá thanh toán futures; bot đã cài (`carry_settle/carry_settled`; short futures/coin <= 0,30x vốn).
- **`cycle_error` > 1 giờ / `rate_limit` cụm / `postonly_reject` bão / `risk_reject` nhiều:** `grep cycle_error` lấy timestamp `t` (cùng lỗi > 1h mới tính); rate_limit 10006 = đợi, giảm tần suất, giữ 1 runner/IP, dựa cache dùng chung `artifacts/bot/_kline_cache/`; postonly_reject retry cùng giá là bình thường (nếu kéo dài kiểm tra plan Binance vs Bybit, BNB lệch ~10 bps); risk_reject đọc `reason` từng dòng (trần per-coin 2,5x / dip 2,0x / total 4x / single 1x / fat 15 %), guard không chặn reduce-only nên stop/TP/exit luôn qua — không tắt guard bằng `--no-risk-guard` để "cho qua".

## 8. Kỳ vọng + go-live / dừng (từ DEPLOYMENT_PLAN_VI.md)

- Kỳ vọng trung thực: **trung vị ~5 %/tháng, năm xấu ~3 %/tháng, DD tới ~18 %** (49 cửa sổ 12 tháng trượt: min 2,73/trung vị 4,89/max 11,71 %/tháng; DD trung vị 13,5/max 18,7; không cửa sổ lỗ). Bootstrap 10.000 năm: trung vị ~5,1 %/tháng (p5 1,5/p95 10,3), chỉ ~52 % năm >= 5 %; P(DD > 20 %) ~11 %; P(năm lỗ) ~0,7 %; vốn phải chịu được DD 25 %. KPI (G2, oc_kpi_g2): 41 % tháng >= +5 %, 70,5 % tháng không lỗ, chuỗi lỗ dài nhất 4 tháng; win book 51,5 %/dip 68,6 %/tất cả 65,3 %. Giá Bybit thật thấp hơn Binance ~0,5pp/tháng (ở chân book, không phải thang dip — dip gap nhỏ; không phải khớp lệnh book — phần còn lại do sizing/định giá [oc_venuegap; oc_bookvenue]). Carry f=0,25 cộng thêm chỉ ~+0,12pp/tháng. Account-realistic G2+carry f=0.25 expectation is 5.634/2.778/16.75/16.66 compound [oc_carrycompound]; +0.12pp/5.533 is the conservative year-start [oc_carryfric]. Dưới ma sát compounding [oc_carryfric2]: base 5,634; S1 4,780; S2 5,438; S3 4,806; S4 5,125; S5 5,111 (không năm lỗ).
- Go-live tiền thật nhỏ (sau tối thiểu 8 tuần paper, ĐỦ cả 4): (a) paper ở phân vị >= 20 bootstrap (`prospective_scorecard.py`); (b) DD paper <= 15 %; (c) lệch bot vs plan <= 1,5pp/tháng (`paper_divergence.py`; trước 14 ngày `too early` là bình thường); (d) không `cycle_error` > 1h, không vị thế thiếu stop. Tăng vốn sau 3 tháng live nếu (a)–(c) vẫn đúng. Độ dài bằng chứng (2026-10-07, oc_paperpower, không đổi ngưỡng): với cổng (a)+(b), một quá trình KHÔNG có edge vẫn qua 38 % ở 8 tuần, 31 % ở 12, 14 % ở 26, 3 % ở 52 → 8 tuần chỉ đủ cho pilot vốn nhỏ; vốn đáng kể nên chờ ~26 tuần paper/live nhỏ. Testnet 7 ngày PASS đủ 9 tiêu chí `TESTNET_PLAN_VI.md` mục 7 (unprotected = 0, qty_mismatch = 0, mọi entry PostOnly, stop+TP trong 1 chu kỳ, carry hedge <= 2 cycle, không cycle_error > 1h, rate_limit ~ 0, preflight PASS, parity chỉ so cơ chế không so P&L).
- Dừng: DD tài khoản > 20 % → dừng mở mới, chỉ giữ SL/TP; lỗ một tháng > 10 % → halve vốn tháng sau; phân vị lợi nhuận < 5 sau >= 8 tuần → dừng. Đèn vàng edge (`daily_status.py` mục 6, vỡ = ĐIỀU TRA không tự đổi cấu hình): (1) TB 6 tháng < 1,61 %/tháng; (2) TP rate dip 182 ngày < 0,434.

## 9. KHÔNG làm

- Không live khi chưa qua testnet sạch + đủ 4 điều kiện paper >= 8 tuần. Không sửa ngưỡng go-live/dừng sau khi đã thấy dữ liệu paper (nếu sửa ghi ngày + lý do).
- Không chạy 2 runner cùng `--tag`/thư mục state; không sửa tay `state.json`; không đặt tay trong giờ đầu sau sự cố.
- Không Isolated/one-way/đòn bẩy perps khác 5x cho bot; chân short carry giữ 10x hedge bằng spot; không vượt f=0,25 chung UTA; không hạ đòn bẩy khi đang có vị thế.
- Không bao giờ chạy 1 pha/1 đồng hồ đơn lẻ; không bơm size đuổi 8 %/tháng (biên max chỉ ~5,9 %/tháng ở DD > 17,5); không kỳ vọng 5 % mọi tháng (~1/9 năm chạm DD > 20 %).
- Không commit `.env`/keys; không stash/reset/checkout/clean/commit (GIT READ-ONLY cho worker); không dùng `restart_all.sh` cho testnet/live.

## 10. Sự cố 2026-10-06 và bài học (backend + 6 runner chết lặng)

- Backend tắt ~10:32–10:47 UTC: chạy foreground bằng `run_backend.ps1` nên chết theo cửa sổ console bị đóng (log dừng giữa chừng, không dòng shutdown; plan kẹt ở `decision_bar` 08:00 UTC, lỡ chu kỳ 12:00 UTC ~4 giờ). 6 runner paper + vòng carry dừng chu kỳ từ ~11:55 UTC vì là con của một shell có giới hạn thời gian — `Start-Process` cũ chết theo shell chủ.
- Cách dựng duy nhất từ nay: `.\scripts\restart_all.ps1` (đã sửa, tách tiến trình qua WMI `Win32_Process.Create` nên sống sót khi terminal đóng). Không bao giờ dựng backend/runner từ terminal tạm/foreground rồi đóng cửa sổ.
- Kiểm tra 1 phút sau mọi lần dựng:

```bat
.venv\Scripts\python.exe scripts/alert_watch.py --once --no-toast
.venv\Scripts\python.exe scripts/daily_status.py --fast
.\run_backend.ps1 -Status
```

- Tuỳ chọn của chủ tài khoản (quyết định riêng, chưa bật mặc định): enable Task Scheduler `AlphaLabBackendWatchdog` / `run_backend.ps1 -Ensure` để tự dựng lại backend sau reboot/chết; cân nhắc chạy `alert_watch` thường trực (sự cố 4 giờ không ai biết). Chi tiết chẩn đoán: `docs/opencode/BACKEND_INCIDENT_20261006.md`, `docs/opencode/PAPER_DAY5_20261006.md`.

<!-- consistfix 2026-10-06: §8 appended account-realistic G2+carry f=0.25 expectation 5.634/2.778/16.75/16.66 compound [oc_carrycompound] with +0.12pp/5.533 labelled conservative year-start [oc_carryfric], plus fric2 compounded friction row (base 5.634, S1 4.780, S2 5.438, S3 4.806, S4 5.125, S5 5.111, no losing year). Sources re-checked: oc_carrycompound REPORT (5.634/+0.224), oc_carryfric REPORT (5.533/+0.12), oc_carryfric2 REPORT (S-table). -->

## 11. Đánh giá FM paper K2/C2 hàng tuần (fm_paper_eval, 2026-10-08)

- So tilt runner (`paper_d17bfg2k2` K2 / `paper_d17bfg2ch` C2) với twin không tilt (`paper_d17bfg2`) trên giờ chạy chung (return/DD/fills/win rate) + counterfactual tilt trên fill dip thật của twin (chỉ hàng feed prospective/late và is_prospective; hàng backfill không bao giờ khớp) + bootstrap CI theo tuần + đếm k2_missing/outage gap/stale_plan. Chỉ đọc file, không chạm process đang chạy.

```bat
.venv\Scripts\python.exe scripts/fm_paper_eval.py --feed kronos --boot 2000
.venv\Scripts\python.exe scripts/fm_paper_eval.py --feed chronos --boot 2000
```

- Đọc kết quả: chưa có common uptime (runner ch mới 1 điểm equity) hay `joined` = 0 (29/29 fill dip của twin rơi vào cửa sổ correction 06-10) là bình thường khi runner còn non trẻ — đợi thêm, không sửa ngưỡng; bootstrap cần >= 2 tuần có fill mới có CI.
- Script gốc `scripts/k2_paper_eval.py` giữ nguyên CLI (không xóa/không đổi); kiểm thử: `.venv\Scripts\python.exe -m pytest tests/test_fm_paper_eval.py -q`.

## 11b. So sánh B7 / B7xC2 / C2 hàng tuần (fm_paper_eval --all, 2026-10-08)
- Chạy mỗi sáng thứ Hai: `.venv\Scripts\python.exe scripts/fm_paper_eval.py --all --boot 2000` (chỉ đọc file, so mọi tilt với twin `paper_d17bfg2` trên giờ chạy chung SAU restart 04:50 UTC 08-10).
```bat
.venv\Scripts\python.exe scripts/fm_paper_eval.py --all --boot 2000
```
- Chưa vội đổi khi `joined` = 0 hay bootstrap `n/a` (runner non trẻ) — đợi >= 2 tuần có fill.
- Chỉ xem xét chuyển tilt khi một feed thắng twin cả realised lẫn counterfactual, bootstrap P(diff>0) >= 0,9 qua >= 4 tuần và DD không tệ hơn.
- Mọi ngưỡng đổi tilt phải đăng ký trước, không sửa sau khi thấy số paper.
