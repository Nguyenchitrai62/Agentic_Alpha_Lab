# Keepalive 2026-10-07 (owner chạy một lần)
Lệnh (PowerShell tại repo root, xem trước rồi mới đăng ký):
`.\scripts\register_keepalive.ps1 -Status`
`.\scripts\register_keepalive.ps1 -Register -EveryMinutes 10`
Task 1 `AlphaLabRunnersKeepAlive`: mỗi N phút chạy
`restart_all.ps1 -Only bots` + action 2 `-Only carry` (paper only).
Idempotent: đang chạy thì bỏ qua; chỉ bù lệnh còn thiếu.
Task 2 backend: nếu `AlphaLabBackendWatchdog` còn thì in định nghĩa
rồi Enable; nếu mất mới tạo `AlphaLabBackendKeepAlive`
chạy `run_backend.ps1 -Ensure` mỗi N phút.
Vì sao không giới hạn thời gian: `restart_all.ps1` dùng
`Start-Process cmd.exe /c ...` (wrapper sống suốt đời bot) và vòng
carry dùng `Start-Process powershell`; con sống khi cha thoát
nhưng scheduler kill theo job khi hết time-limit sẽ kéo theo cả
bot/supervisor, nên cả 2 task đặt ExecutionTimeLimit = 0 (không giới hạn).
Cả 2 task: user hiện tại, chỉ chạy khi đã logon, ẩn, không lưu mật khẩu,
working dir = repo root, Parallel (restart_all idempotent; IgnoreNew có thể kẹt nếu bot con giữ task ở trạng thái Running).
Không đụng BOT/paper đang chạy, không tạo order, không đổi code.
Kiểm tra: `Get-ScheduledTask AlphaLabRunnersKeepAlive, AlphaLabBackend*`
`Get-ScheduledTaskInfo -TaskName AlphaLabRunnersKeepAlive`
`.venv\Scripts\python.exe scripts/bot_health.py artifacts/bot/paper ...`
`.\run_backend.ps1 -Status` (backend + tunnel).
Gỡ: `.\scripts\register_keepalive.ps1 -Unregister` (xóa 2 task trên,
giữ nguyên Watchdog; tắt hẳn bằng Task Scheduler nếu cần).
Đăng ký là quyết định của OWNER; agent không chạy -Register.
