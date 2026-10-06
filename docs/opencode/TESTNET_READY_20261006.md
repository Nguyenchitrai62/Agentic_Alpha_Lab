# TESTNET READY — G2 + carry f=0.25 (ngày kiểm 2026-10-06, không key, không đặt lệnh)

> Chỉ đọc code + endpoint công khai testnet. Không chạm `.env`, không sửa state, không set `BOT_ALLOW_LIVE`.

## Preflight ở chế độ không key
- `scripts/bot_preflight.py` KHÔNG có chế độ no-key riêng; chỉ `--help` chạy được không key (in mô tả chỉ-đọc, PASS).
- `bot_preflight.py --mode testnet` khi thiếu key thoát 1, in đúng 1 dòng:
  `thiếu BYBIT_TESTNET_API_KEY/_SECRET trong .env (xem runbook mục V2).` — không gọi mạng, không in key.
- Đọc code: preflight chỉ dùng `client.get` (signed GET) + `client.public`; grep không thấy `.post`/`.place`/`order/create` — xác nhận chỉ-đọc.

## Đối chiếu từng bước TESTNET_PLAN_VI.md
- §0 lệnh đóng băng: mọi flag `--corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0 --adopt-fresh --carry-f 0.25 --interval 25 --tag/--mode/--once/--equity` đều tồn tại trong `bot/run.py` argparse — READY.
- §1 prerequisites (tài khoản, key, vốn, backend): cần chủ tài khoản làm tay — OWNER (BLOCKED tới khi xong).
- §2 cài tay UTA/Hedge/Cross/5x/quarterly 10x: code đúng như mô tả — bot chỉ tự gọi hedge 1 lần và bỏ qua lỗi (`run.py:343-346`); không có lệnh set leverage/margin nào trong `bot/` (chỉ 1 POST `switch-mode` trong `hedge_mode`, `bybit_v5.py:450`) — READY (phần việc tay: OWNER).
- §3 preflight + dry `--once`: preflight 9 hàng đúng code (`bot_preflight.py:246-380`); dry mặc định không cần key — READY.
- §4 lệnh testnet 7 ngày: flag/mode/testnet tag hợp lệ; `runner.lock` một-runner (`run.py:1480-1521`); `restart_all.sh` chỉ paper, không bao giờ dựng testnet/live, không set `BOT_ALLOW_LIVE` — READY.
- §5 theo dõi ngày: `daily_status.py`, `bot_health.py <dir>`, pattern `actions.jsonl` đều khớp code — READY.
- §6 stop rules / §7 PASS 9 tiêu chí / §8 bảng tra: log `unprotected_close/qty_mismatch/postonly_reject/risk_reject/carry_unhedged/carry_close/protection_check/slow_cycle/lock_wait/cycle_error/maint_cancel/maint_resume` đều có trong code — READY.
- Khóa live: `--mode live` bị từ chối khi thiếu `BOT_ALLOW_LIVE=yes-real-money` (`run.py:1517-1518`) — READY. Lưu ý: số dòng `bot/run.py:576-577,1282-1283`, `run.py:117-120`, `bybit_v5.py:302-323` ghi trong plan đã cũ so với code hiện tại (gate nay ở 1517-1518, hedge ở 343-346, switch-mode ở 450) — hành vi vẫn đúng, nên sửa số dòng tham chiếu.

## Endpoint + carry trên testnet (chỉ public, đã gọi thử)
- `TESTNET=https://api-testnet.bybit.com`, `MAINNET=https://api.bybit.com` (`bybit_v5.py:20-21`) — đúng host testnet Bybit — READY.
- Testnet public liệt kê 4 quarterly inverse đang Trading: `BTCUSDZ26 BTCUSDH27 ETHUSDZ26 ETHUSDH27`; spot `BTCUSDT` có giá — carry testnet được hỗ trợ — READY.

## Việc chủ tài khoản làm theo thứ tự (OWNER)
1. Tạo sub-account testnet riêng tại `testnet.bybit.com`.
2. Tạo API key testnet Read-Write, bật Contracts/Derivatives (trade+read); kiểm tra `BOT_ALLOW_LIVE` chưa set.
3. Tự điền `BYBIT_TESTNET_API_KEY` + `BYBIT_TESTNET_API_SECRET` vào `.env` local (không commit/dán chat).
4. Nâng UTA, bật Hedge Mode, Cross cả 5 coin, đòn bẩy perps 5x từng coin, quarterly đang giữ 10x; dọn lệnh/vị thế lạ.
5. Nạp testnet ≥5000 USDT (tốt nhất ~10000); dựng backend (`run_backend.ps1 -Status`, plan tươi <4h30m).
6. Chạy preflight `--mode testnet` tới PASS, rồi dry `--once`, rồi start đúng lệnh §4 với tag `tnetg2c`.
