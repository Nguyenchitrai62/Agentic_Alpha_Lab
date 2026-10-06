# KẾ HOẠCH CHẠY TESTNET 7 NGÀY — G2 + carry f=0.25 (Bybit TESTNET)

> Ngày lập: 2026-10-06. Phạm vi: chạy thử cơ chế (mechanics), KHÔNG đánh giá P&L.
> Giá/thanh khoản testnet khác mainnet nên lợi nhuận/DD testnet không dùng để kết luận triển khai.
> Tài liệu gốc: `docs/BOT_RUNBOOK_VI.md`, `docs/BOT_EXECUTION.md`, `docs/QUICKSTART_VI.md`,
> `docs/opencode/TESTNET_REVIEW_20261006.md`, `scripts/bot_preflight.py`, `bot/run.py`, `scripts/restart_all.sh`.
> Quy tắc: không code, không commit, không mạng ngoài Bybit V5, không bao giờ chạm/sửa `.env` ngoài việc chủ tài khoản tự điền key.

## 0. Triển khai chính xác là gì (đóng băng 7 ngày)

- Pipeline G2 = R2B1D17BF + trần dip 2x: `--corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0 --adopt-fresh --carry-f 0.25 --interval 25`, plan `artifacts/research/advisor_shadow/trade_plan_v376.json`.
- Cộng sleeve carry quý `f=0.25` trên CÙNG một UTA (`--carry-f 0.25`).
- `--adopt-fresh` BẬT (lệnh đóng băng mọi mode đều có `--adopt-fresh`; mặc định code là TẮT).
- Risk guard BẬT mặc định ở testnet/live (không thêm `--no-risk-guard`; paper/dry mới cần `--risk-guard` riêng).
- `--equity` KHÔNG dùng ở testnet/live (lấy vốn thật trên sàn). `--interval 25` (lệnh đóng băng mọi mode dùng `--interval 25`).
- Code-review bot F1-F7 + N1-N4 ĐÃ SỬA (commit 359004f, bot_reviewfix; 124 test bot xanh): testnet có carry (--carry-f 0.25) nay được phép — vẫn bắt buộc preflight PASS và testnet sạch 7 ngày trước live.
- Một runner / một thư mục state (khóa OS `runner.lock`). Tag testnet riêng, không trùng paper.

## 1. Việc chủ tài khoản làm trước ngày 0 (prerequisites)

1. Tạo tài khoản Bybit TESTNET tại `testnet.bybit.com` (sub-account riêng cho đợt này, không dùng chung với paper/live).
2. Tạo API key testnet: quyền Read-Write, bật Contracts/Derivatives (trade + read). Key testnet đọc được qua `GET /v5/user/query-api`; key Read-Only bị preflight FAIL.
3. Chỉ điền 2 dòng vào file `.env` local (không commit, không dán chat, không gửi file):
   `BYBIT_TESTNET_API_KEY=...` và `BYBIT_TESTNET_API_SECRET=...`.
4. Xác nhận `BOT_ALLOW_LIVE` KHÔNG được set (để `--mode live` luôn bị từ chối: gate live trong `main()` ở `bot/run.py`, kiểm ngày 2026-10-06 ở dòng ~1517-1518; số dòng cũ 576-577,1282-1283 đã stale).
5. Nạp vốn testnet (faucet/testnet funds): tối thiểu 5000 USDT, tốt nhất ~10000 USDT. Dưới 5000 các rung BTC bị `skipped_below_minimum` (skip bình thường, không phải lỗi).
6. Dựng backend trước bot: `.\run_backend.ps1 -Status` (chỉ `-Background` khi chưa chạy). Mở `artifacts/research/advisor_shadow/trade_plan_v376.json` xem `generated_at` phải < 4h30m, nếu cũ bot chỉ giữ exits + log `stale_plan`.

### Danh sách việc chủ tài khoản (OWNER, theo thứ tự `docs/opencode/TESTNET_READY_20261006.md`)

1. Tạo sub-account testnet riêng tại `testnet.bybit.com`.
2. Tạo API key testnet Read-Write, bật Contracts/Derivatives (trade+read); kiểm tra `BOT_ALLOW_LIVE` chưa set.
3. Tự điền `BYBIT_TESTNET_API_KEY` + `BYBIT_TESTNET_API_SECRET` vào `.env` local (không commit/dán chat).
4. Nâng UTA, bật Hedge Mode, Cross cả 5 coin, đòn bẩy perps 5x từng coin, quarterly đang giữ 10x; dọn lệnh/vị thế lạ.
5. Nạp testnet ≥5000 USDT (tốt nhất ~10000); dựng backend (`.\run_backend.ps1 -Status`, plan tươi <4h30m).
6. Chạy preflight `--mode testnet` tới PASS, rồi dry `--once`, rồi start đúng lệnh §4 với tag `tnetg2c`.

## 2. Cài đặt tài khoản bằng tay (bot KHÔNG tự làm — gate chặn V1)

Bot chỉ tự gọi hedge một lần và bỏ qua lỗi (`Runner.__init__` trong `bot/run.py`, kiểm ngày 2026-10-06 ở dòng ~343-346; số dòng cũ 117-120 đã stale); Cross/đòn bẩy không bao giờ tự set/check — trong `bot/` không có lệnh set leverage/margin nào, POST duy nhất là `Bybit.hedge_mode()` trong `bot/bybit_v5.py` (gọi `POST /v5/position/switch-mode`, kiểm ngày 2026-10-06 ở dòng ~449-450; tham chiếu cũ `bybit_v5.py:302-323` đã stale, nay là `sign()`/`Bybit._check`/`public()`). Làm tay trên chính sub-account testnet, kiểm tra lại trên UI:

1. Upgrade lên Unified Trading Account (UTA): avatar → Upgrade to Unified Trading Account. Preflight kiểm tra qua `GET /v5/account/wallet-balance?accountType=UNIFIED`.
2. Position Mode = Hedge Mode (Both long & short): mở chart BTCUSDT Perps → góc Position Mode → chọn Hedge. Bot gửi mọi lệnh kèm `positionIdx` 1 (long) / 2 (short); tài khoản One-Way (`positionIdx=0`) sẽ bị từ chối hàng loạt.
3. Margin = Cross cho cả 5 coin (không dùng Isolated cho bot). Bybit không cho đổi margin khi đang có vị thế — đổi trước khi chạy.
4. Đòn bẩy perps = 5x từng coin BTC/ETH/SOL/BNB/XRP (Bybit chỉnh theo từng coin, cạnh ô Cross). Đây là mức tối thiểu không bao giờ chặn lệnh ở cap 2.0. KHÔNG hạ đòn bẩy khi đang có vị thế.
5. Chân short quarterly của carry để 10x (đã hedge bằng spot mua bằng tiền thật): khi cặp carry mở, chỉnh 10x trên chính symbol quarterly đang giữ (ví dụ BTC quarterly). Không vượt `f=0.25` chung UTA; `f=0.50` bị chặn margin nên cấm.
6. Dọn sạch lệnh/vị thế lạ trên 5 coin trước giờ G (hoặc xác nhận chủ): link bot có dạng `^[bd]<phase><BTC|ETH|SOL|BNB|XRP>`; link carry prefix `c`. Lệnh lạ còn resting sẽ làm bot nhận nhầm theo symbol.

## 3. Preflight chỉ-đọc (bắt buộc PASS, exit 0 mới được tiếp)

Chỉ gọi endpoint V5 đọc (signed GET + public), không bao giờ POST nên không thể đặt/hủy lệnh hay đổi settings:

```bat
.venv\Scripts\python.exe scripts/bot_preflight.py --mode testnet
```

- PASS khi không có dòng `[FAIL]` nào (WARN vẫn exit 0, xem `run_preflight()` trong `scripts/bot_preflight.py`, kiểm ngày 2026-10-06 vẫn ở dòng ~246-380).
- 9 hàng: Mạng / API key / Tài khoản Unified / Hedge Mode / Cross margin / Đòn bẩy 5x / Vốn / Lệnh-vị thế lạ / Giờ server (< 1 s) / Minima sàn ở vốn hiện tại (cỡ lệnh ước tính theo `--dip-mult 1.7`).
- Mỗi FAIL kèm bước sửa chính xác trên Bybit UI — sửa hết rồi chạy lại. Không khởi động bot khi còn FAIL.
- Chạy khô (dry, không gửi lệnh, public data only) sau preflight PASS:
```bat
.venv\Scripts\python.exe -m bot.run --once --equity 5000 --corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0 --adopt-fresh --carry-f 0.25 --interval 25
```

## 4. Lệnh chạy testnet duy nhất trong 7 ngày (đóng băng, không đổi flags giữa chừng)

```bat
.venv\Scripts\python.exe -m bot.run --mode testnet --corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0 --adopt-fresh --carry-f 0.25 --interval 25 --tag tnetg2c
```

- State: `artifacts/bot/testnet_tnetg2c/state.json`, mọi hành động: `actions.jsonl` cùng thư mục. Không chạy 2 tiến trình cùng tag/dir (kẹt `runner.lock`).
- `scripts/restart_all.sh` KHÔNG bao giờ dựng testnet/live (chỉ paper + backend local + carry paper) — sau reboot/mất điện dựng lại testnet BẰNG TAY theo mục 4 runbook: backend trước (`-Status`, plan tươi), rồi đúng lệnh trên, đối chiếu `actions.jsonl` với vị thế testnet thật.
- Kỳ vọng đúng sau fix `bot_testnetfix` (2026-10-06): entry book/add + bid dip gửi `timeInForce:"PostOnly"` (maker-only; cross bị từ chối `postonly_reject` rồi thử lại chu kỳ sau, không đuổi giá); TP/reduce GTC reduce-only; stop là conditional market reduce-only `closeOnTrigger`; market exit là market reduce-only.
- Carry (`bot_carry`): mỗi coin BTC/ETH đủ điều kiện (front quarterly còn <= 7 ngày hoặc lần đầu, basis năm hóa `ln(F/S)*365/DTE >= 4 %`) thì spot BUY + quarterly SELL cùng notional = `0.25 x equity`, link prefix `c`, không tính vào trần dip, qua `risk_guard` + trần short `<= 0.30 x vốn/coin`. Ghi chú testnet (kiểm public ngày 2026-10-06): testnet liệt kê 4 quarterly inverse đang Trading (`BTCUSDZ26 BTCUSDH27 ETHUSDZ26 ETHUSDH27`) và spot `BTCUSDT` có giá — carry được hỗ trợ trên testnet.

## 5. Theo dõi mỗi ngày (~5–10 phút/ngày, giống runbook mục 3)

```bat
.venv\Scripts\python.exe scripts/daily_status.py
.venv\Scripts\python.exe scripts/bot_health.py artifacts/bot/testnet_tnetg2c
Select-String -Path artifacts/bot/testnet_tnetg2c/actions.jsonl -Pattern 'unprotected_close|plan_closed_divergence|skipped_below_minimum|stale_plan|postonly_reject|risk_reject|carry_unhedged|carry_close|carry_settle|protection_check|slow_cycle|lock_wait|cycle_error|maint_cancel|maint_resume' | Select-Object -Last 30
```

- `daily_status.py` trước (backend + tuổi plan + tóm tắt + collector + 1 dòng OK/WARNING/CRITICAL), rồi `bot_health.py` cho dir testnet khi có WARNING/CRITICAL.
- `last_cycle age`: CRITICAL nếu > 3 lần interval (> 60 s) hoặc > 5 phút = runner chết → kiểm `runner.log`/Task Manager tiến trình cũ giữ `runner.lock`, khởi động lại đúng lệnh mục 4.
- `plan age > 4h30m`: warning = plan cũ → dựng lại backend; bot chỉ giữ exits là đúng, không ép vào lệnh.
- `24h ops place/amend/cancel/fill/market_exit/stale_plan/errors`: `errors > 0` = warning, đọc 5 dòng lỗi kèm theo; `rate_limit`/10006 = chạm giới hạn → đợi, giảm tần suất, kiểm tra 2 runner chung IP/cache dùng chung.
- `cycle_ms`: WARNING khi > 60 s (`slow_cycle`); `lock_wait` khi chờ khóa cache > 10 s.
- Nhật ký tay mỗi ngày (giờ UTC, equity, DD, fills, unprotected/qty_mismatch, cycle_error, rate_limit, postonly/risk_reject, carry events, parity paper-vs-testnet): 1 dòng/ngày, đủ 7 ngày mới kết luận.

## 6. Quy tắc dừng trong tuần testnet (stop rules — dừng mở mới trước, điều tra sau)

- `unprotected=[...]` CRITICAL (vị thế thiếu stop hoặc TP): kiểm tra ngay `actions.jsonl` + vị thế testnet thật; bot tự đặt lại <= 20 s, quá 2 vòng tự đóng market (`unprotected_close`). Còn CRITICAL sau restart thì dừng bot, không đặt tay giờ đầu.
- `qty_mismatch=[...]` CRITICAL (sổ bot lệch sàn): sàn là sự thật; kiểm tra tay, không sửa tay `state.json`.
- `cycle_error` lặp cùng lỗi > 1 giờ: mất điều kiện go-live, dừng và sửa (xem timestamp `t` trong `actions.jsonl`).
- DD tài khoản testnet > 20 %: dừng mở mới, chỉ giữ SL/TP (quy tắc runbook mục 6; testnet DD chỉ để thử quy trình dừng, không kết luận chiến lược).
- Carry `carry_unhedged` quá 2 cycles không hedge được cặp → bot tự đóng chân đã khớp (`carry_close`): dừng mở carry mới, kiểm tra minima/tick symbol dated + guard `carry_cap`.
- Sau sự cố bất ngờ (reboot/mất mạng): ưu tiên xác nhận `protection_check` + `bot_health.py` hết CRITICAL mới cho bot chạy tiếp; cửa sổ hở duy nhất là mảnh vừa khớp chưa kịp đặt exit (<= 20 s) — kiểm tra tay khi mạng về.
- Bảo trì CÓ hẹn: đặt `artifacts/bot/testnet_tnetg2c/maintenance.json` `{"start": ISO, "end": ISO}` (UTC) — bot tự hủy bid dip chờ + không vào book mới từ trước giờ bắt đầu 30 phút tới hết giờ (`op=maint_cancel` rồi `op=maint_resume`); stop/TP/backstop + chân carry giữ nguyên trên sàn.

## 7. Tiêu chí PASS để được xét live (đủ cả 7 ngày, thiếu 1 là FAIL)

1. `unprotected` = 0 trong toàn 7 ngày (mọi vị thế mở luôn có stop + TP native; mảnh mới khớp được gắn stop/TP trong đúng 1 chu kỳ <= 20 s; log `protection_check` sau mọi restart trống `missing`).
2. `qty_mismatch` = 0 trong toàn 7 ngày (sổ `state.json`/ledger khớp vị thế testnet thật mọi lần đối chiếu).
3. Mọi entry book/dip gửi đi là PostOnly (`timeInForce:"PostOnly"` trong `actions.jsonl` `op=place` entry; `postonly_reject` chỉ retry cùng giá, không có lệnh market/taker nào thay entry).
4. Mọi mảnh đã khớp có stop + TP kèm trong 1 chu kỳ; quá 2 vòng không stop phải có `unprotected_close` (0 lần là tốt nhất; > 0 phải giải thích được từng lần).
5. Cặp carry hedge trong <= 2 cycles (`carry_unhedged` rồi đủ 2 chân hoặc `carry_close` đúng quy tắc; không để chân đơn qua đêm không lý do).
6. Không có `cycle_error` kéo dài > 1 giờ; runner sống suốt 7 ngày (trừ restart có kế hoạch ghi log).
7. `rate_limit` ~ 0 (không có cụm 10006; signed POST burst khi nhiều exits cùng cycle là bình thường nhưng phải tự hồi chu kỳ sau, không mất lệnh bảo vệ).
8. Ghi chú parity paper-vs-testnet: số fills/maker-taker/fees khác nhau là BÌNH THƯỜNG (testnet cross thành taker ở GTC cũ / PostOnly reject ở bản mới, minima/tick/lot khác, basis/quarterly khác, Bybit rẻ hơn Binance ở BNB ~10 bps). Chỉ so cơ chế (link, kind, reduceOnly, positionIdx, stop/TP đầy đủ), không so P&L.
9. Preflight `--mode testnet` PASS suốt tuần (chạy lại sau mỗi lần đổi key/settings); `BOT_ALLOW_LIVE` chưa từng được set.

## 8. Làm gì khi FAIL từng mục (bảng tra nhanh)

| Triệu chứng | Nguyên nhân thường gặp | Xử lý |
|---|---|---|
| Preflight `[FAIL] API key` | key sai/hết hạn, Read-Only, thiếu Contracts | Tạo key testnet mới Read-Write + Contracts, điền lại `.env`, chạy lại preflight; chưa PASS thì không start bot |
| Preflight `[FAIL] Tài khoản/Hedge/Cross/5x` | sub-account mới mặc định One-Way/Isolated/1x | Sửa tay trên UI theo dòng `Sửa (Bybit UI)` của preflight (UTA, Hedge, Cross, 5x từng coin); không hạ đòn bẩy khi có vị thế |
| `another bot runner holds .../runner.lock` | tiến trình cũ còn sống hoặc 2 runner cùng tag | `Get-Process python` + mtime `state.json`/`stdout.log`; kill tiến trình cũ hoặc dùng tag khác; không chạy đè |
| `stale_plan` liên tục | backend chết / plan > 4h30m | `.\run_backend.ps1 -Status` → `-Background` nếu cần; chờ plan tươi; bot chỉ giữ exits là đúng |
| `unprotected` CRITICAL | stop/TP đặt lỗi, minima, mạng rớt đúng lúc fill | Đối chiếu sàn thật; chờ bot đặt lại <= 20 s; quá 2 vòng bot tự `unprotected_close`; còn CRITICAL thì dừng bot điều tra |
| `qty_mismatch` CRITICAL | fill sót (execution history bị tỉa), can thiệp tay | Sàn là sự thật; đối chiếu `actions.jsonl` vs vị thế; không sửa tay `state.json`; dừng mở mới tới khi khớp |
| `cycle_error > 1h` | plan hỏng, API đổi, bug | `grep cycle_error` lấy timestamp; dừng bot, giữ exits trên sàn, báo leader kèm log; không restart vòng lặp mù |
| `rate_limit`/10006 cụm | 2 runner chung IP, burst exits, paper nặng hơn testnet | Giữ 1 runner testnet/IP này, giữ interval 20 s, dựa cache dùng chung `artifacts/bot/_kline_cache/`; signed lỗi chỉ retry chu kỳ sau |
| `postonly_reject` bão | giá plan xa/giật, testnet spread khác mainnet | Bình thường (retry cùng giá, không đuổi); nếu kéo dài + không fill nào thì kiểm plan Binance vs Bybit (BNB ~10 bps) và minima |
| `risk_reject` nhiều | vượt trần per-coin 2.5x / dip 2.0x / total 4x / single 1x / fat 15 % | Đọc `reason` từng dòng; guard không chặn reduce-only nên stop/TP/exit luôn qua; không tắt guard bằng `--no-risk-guard` để "cho qua" |
| `skipped_below_minimum` nhiều | vốn testnet nhỏ, rung BTC < 0.001 BTC | Nạp testnet về ~10000; đây là skip bình thường, không phải lỗi |
| Carry `carry_unhedged`/`carry_close` | 1 chân khớp chân kia trượt minima/guard | Kiểm tick/lot symbol dated + `carry_cap 0.30x`; không mở carry tay bù; để bot hedge/đóng theo quy tắc |
| Lệnh/vị thế lạ (preflight WARN) | tay đặt thử hoặc runner khác cùng coin | Dọn hoặc xác nhận chủ; bot sẽ nhận nhầm nếu trùng symbol |

## 9. Lịch 7 ngày gợi ý

- Ngày 0: xong mục 1–3 (preflight PASS + dry `--once` OK), cài tay UTA/Cross/Hedge/5x + quarterly 10x khi có carry, start đúng lệnh mục 4, xác nhận `protection_check` + `bot_health` không CRITICAL sau 30 phút.
- Ngày 1–6: mỗi ngày chạy bộ 3 lệnh mục 5, ghi 1 dòng nhật ký; xử lý WARNING/CRITICAL theo mục 8 ngay trong ngày.
- Ngày 7: chạy đủ 3 lệnh + đối chiếu `actions.jsonl` vs vị thế sàn lần cuối; chấm 9 tiêu chí mục 7 (đủ mới xét live; thiếu thì lặp 7 ngày mới sau khi sửa).
- Sau 7 ngày: giữ runner chạy hoặc dừng sạch (cancel bid chờ tay trên UI, để stop/TP bảo vệ tới khi đóng hết, sao lưu `state.json` + `actions.jsonl`); live chỉ sau testnet PASS + đủ 4 điều kiện paper >= 8 tuần trong `docs/DEPLOYMENT_PLAN_VI.md` (phân vị >= 20, DD <= 15 %, lệch bot-plan <= 1.5pp/tháng đủ 14 ngày, không cycle_error > 1h/không thiếu stop).

<!--
docs_testnetfix 2026-10-06 — changes to docs/TESTNET_PLAN_VI.md only (no code, no commits):
1. §1.4: stale `bot/run.py:576-577,1282-1283` -> gate live trong `main()` ở `bot/run.py` (~1517-1518 as of 2026-10-06).
2. §2 intro: stale `bot/run.py:117-120` -> `Runner.__init__` trong `bot/run.py` (~343-346, hedge_mode try/except); stale `bot/bybit_v5.py:302-323` -> `Bybit.hedge_mode()` trong `bot/bybit_v5.py` (~449-450, sole POST switch-mode; old lines now sign/_check/public); noted no leverage/margin setter exists in bot/.
3. §3: `scripts/bot_preflight.py:246-380` verified still current -> kept, reworded to lead with `run_preflight()`.
4. §1: added OWNER 6-step checklist in the exact order of docs/opencode/TESTNET_READY_20261006.md.
5. §4 carry bullet: added note that Bybit testnet lists BTC/ETH inverse quarterlies (BTCUSDZ26 BTCUSDH27 ETHUSDZ26 ETHUSDH27) + spot BTCUSDT price, so carry is supported on testnet.
6. Function names preferred over line numbers throughout; line numbers kept only as ~as-of-2026-10-06 hints.
-->
