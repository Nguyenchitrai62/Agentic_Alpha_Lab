# Web app: triển khai (FE trên Vercel, BE trên máy này qua Cloudflare Tunnel)

```
Trình duyệt ──► Vercel (frontend/, tĩnh) ──fetch──► https://api-crypto.nguyenchitrai.id.vn
                                                     │ Cloudflare Tunnel (cloudflared service)
                                                     ▼
                                   máy này: uvicorn backend.server:app @ 127.0.0.1:8724
                                   ├─ SQLite WAL  artifacts/web/app.db  (gitignored)
                                   └─ scheduler: sau mỗi nến 4h đóng (+8 phút) chạy nến → tín hiệu v205 → paper trading
```

API chỉ đọc DB, không bao giờ chạy pipeline khi có request. Pipeline chạy theo lịch hoặc khi admin bấm nút.
Hệ thống chỉ gợi ý: không có khoá sàn và không đặt lệnh.

## 1. Google OAuth client (một lần)

1. Vào https://console.cloud.google.com/apis/credentials, chọn **Create credentials → OAuth client ID → Web application**.
2. Mục **Authorized JavaScript origins**, thêm:
   - domain FE, ví dụ `https://crypto.nguyenchitrai.id.vn`;
   - domain `https://<project>.vercel.app`;
   - `http://localhost:5500` (để test cục bộ).
3. Không cần redirect URI (dùng Google Identity Services popup).
4. Chép **Client ID** vào `.env` của máy này: `GOOGLE_CLIENT_ID=...apps.googleusercontent.com`.
   FE tự đọc Client ID từ `/api/public/config`, nên không cần sửa `frontend/config.js`.

## 2. `.env` trên máy server (không commit)

Xem `.env.example`. Các khoá quan trọng:

- `ADMIN_EMAILS=trainguyenchi30@gmail.com`: admin cố định, chỉ khai báo ở đây.
- `AUTH_SESSION_SECRET`: chuỗi ngẫu nhiên dài, đã được tạo sẵn.
- `GOOGLE_CLIENT_ID`: lấy ở bước 1.
- `CORS_ALLOW_ORIGINS=https://crypto.nguyenchitrai.id.vn`: domain FE. Mặc định đã chấp nhận `*.vercel.app` và `*.nguyenchitrai.id.vn` qua regex.

Phân quyền:

- **admin** (email trong `ADMIN_EMAILS`): xem mọi trang, chạy pipeline, duyệt người dùng.
- **viewer**: email đã được admin duyệt ở trang Admin, hoặc có trong `VIEWER_EMAILS`.
- **pending**: tài khoản Google khác. Sau khi đăng nhập họ thấy trang "Đang chờ duyệt".
- Đặt `ALLOW_ANY_GOOGLE_VIEWER=true` để mọi tài khoản Google đều xem được.

## 3. Chạy backend

**Cách nhanh:** double-click `run_backend.bat` ở gốc repo, hoặc chạy `.
un_backend.ps1`. Script bật backend (cổng 8724) và
connector Cloudflare tunnel, bỏ qua phần nào đang chạy rồi, sau đó kiểm tra `/health` cả cục bộ lẫn public.
- `.
un_backend.ps1 -Status`: chỉ xem trạng thái.
- `.
un_backend.ps1 -Stop`: tắt cả hai.

Token tunnel đặt ở `CLOUDFLARE_TUNNEL_TOKEN` trong `.env` cục bộ, không commit.

Cách chạy từng phần:

```powershell
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt   # nếu thiếu thư viện
powershell -ExecutionPolicy Bypass -File deploy\start_backend.ps1          # chạy + tự khởi động lại khi lỗi
powershell -ExecutionPolicy Bypass -File deploy\install_autostart.ps1      # (tuỳ chọn) tự chạy khi đăng nhập Windows
```

Lần chạy đầu, nếu DB trống, scheduler tự tải nến, chạy tín hiệu hiện tại và backfill walk-forward 2021–2026
(khoảng 1 phút). Log nằm ở `artifacts/web/backend.log`. Kiểm tra bằng `http://127.0.0.1:8724/health`.

### Xem web trên chính máy server, không cần đăng nhập

Double-click `run_frontend.bat` (hoặc chạy `.un_frontend.ps1`) để mở `http://localhost:5500`.
- Khi request đi thẳng vào `127.0.0.1:8724` từ máy này, backend coi là admin và không cần Google.
- Request đi qua tunnel luôn phải đăng nhập, vì chúng mang header Cloudflare và host public.
- Tắt chế độ này bằng `WEB_LOCAL_NO_AUTH=false`.

## 4. Cloudflare Tunnel

Chạy PowerShell **với quyền Administrator**:

```powershell
cloudflared.exe service install <TOKEN>
```

Token lấy trên Cloudflare Zero Trust. **Không** lưu token vào repo hay `.env`.

Public hostname: `api-crypto.nguyenchitrai.id.vn` → `HTTP` → `localhost:8724`. Nếu gặp lỗi 502, đổi URL thành
`127.0.0.1:8724`, vì backend chỉ lắng nghe IPv4 loopback.

## 5. Frontend trên Vercel

1. Import repo GitHub vào Vercel. `vercel.json` ở gốc repo đã đặt `outputDirectory: frontend`, không cần build.
   Cách khác: đặt **Root Directory = `frontend`**.
2. Gắn domain FE (ví dụ `crypto.nguyenchitrai.id.vn`) trong Vercel → Domains.
3. Thêm domain đó vào Google OAuth origins (bước 1) và vào `CORS_ALLOW_ORIGINS` (bước 2), rồi khởi động lại backend.
4. Nếu API đổi domain, sửa `apiBaseUrl` trong `frontend/config.js`.

## 6. Test cục bộ

```powershell
.venv\Scripts\python.exe -m uvicorn backend.server:app --host 127.0.0.1 --port 8724
.venv\Scripts\python.exe -m http.server 5500 --directory frontend    # mở http://localhost:5500
```

## API

- **Công khai:** `GET /health`, `GET /api/public/config`, `POST /api/auth/google`, `GET /api/auth/me`.
- **Viewer:**
  - `/api/overview`
  - `/api/signals/latest`
  - `/api/signals?source=live|walkforward&symbol=&start=&end=&limit=`
  - `/api/signals/at?t=`
  - `/api/signals/{id}`
  - `/api/candles?symbol=&interval=1h|4h|1d&start=&end=&limit=`
  - `/api/positions`, `/api/trades`, `/api/equity?source=walkforward|forward`
- **Admin:**
  - `POST /api/admin/run {kind: cycle|signal|candles|forward|walkforward}`
  - `GET /api/admin/jobs`
  - `GET|POST /api/admin/users`

## Hiệu năng

- SQLite chạy WAL, `synchronous=NORMAL`, mmap 256 MB, cache 64 MB. Bảng dùng `WITHOUT ROWID` với khoá chính khớp các truy vấn theo khoảng thời gian.
- Mỗi luồng có kết nối riêng và chỉ có một luồng ghi. Người đọc không bị chặn khi pipeline đang ghi.
- Response nóng được cache dưới dạng bytes JSON đã gzip, kèm ETag (trả 304 khi không đổi). Cache bị xoá sau mỗi job.
- Giới hạn tốc độ theo IP (`CF-Connecting-IP`): 10 request/giây, burst 40.
- Test cục bộ: khoảng 3–7 ms mỗi request, khoảng 200 request/giây với 20 người dùng đồng thời trên một process.
