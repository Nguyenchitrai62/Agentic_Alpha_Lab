# Web app: triển khai (FE trên Vercel, BE trên máy này qua Cloudflare Tunnel)

```
Trình duyệt ──► Vercel (frontend/, tĩnh) ──fetch──► https://api-crypto.nguyenchitrai.id.vn
                                                     │ Cloudflare Tunnel (cloudflared service)
                                                     ▼
                                   máy này: uvicorn backend.server:app @ 127.0.0.1:8724
                                   ├─ SQLite WAL  artifacts/web/app.db  (gitignored)
                                   └─ scheduler: sau mỗi nến 4h đóng (+1 phút) cập nhật dữ liệu → cả 5 trade plan
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
- `CORS_ALLOW_ORIGINS=https://crypto.nguyenchitrai.id.vn`: domain FE. Chỉ chấp nhận các origin được liệt kê chính xác; thêm domain Vercel cụ thể nếu sử dụng.

Phân quyền:

- **admin** (email trong `ADMIN_EMAILS`): xem mọi trang, chạy pipeline, duyệt người dùng.
- **viewer**: email đã được admin duyệt ở trang Admin, hoặc có trong `VIEWER_EMAILS`; xem tín hiệu của những pipeline admin đã mở khóa (mặc định 3 pipeline cuối).
- **pending**: tài khoản Google khác. Sau khi đăng nhập họ thấy trang "Đang chờ duyệt".
- Đặt `ALLOW_ANY_GOOGLE_VIEWER=true` để mọi tài khoản Google đều xem được.

BE mặc định xếp 5 pipeline theo thứ tự: **lợi nhuận/tháng năm kiểm chứng giảm dần → sụt giảm vốn tăng dần → tỷ lệ thắng năm kiểm chứng giảm dần**;
cuối cùng theo mã pipeline để thứ hạng ổn định khi hòa. Đọc `monthly_last_year`, `gate_dd`, `win_hidden` từ dashboard;
thiếu số liệu thì dùng snapshot trong `backend/catalog.py`. Đây là thứ hạng sản phẩm/hiển thị và lịch chạy theo yêu cầu
người dùng 2026-10-02, không dùng để huấn luyện, thay đổi tham số hay lựa chọn model nghiên cứu.
Với số liệu hiện tại, admin giữ riêng **G2/v301** và **CS/v295**; viewer xem **CB/v285**, **C4/v269**, **C5/v266**.
Cả 5 pipeline vẫn xuất hiện với đầy đủ chỉ số đánh giá lịch sử, kể cả pipeline bị khóa, kèm liên kết mail admin.
Ở trang **Admin → Thứ tự pipeline & quyền xem tín hiệu**, dùng ↑ ↓ để đổi thứ tự, khóa/mở từng pipeline rồi bấm **Lưu cấu hình pipeline**.
Khóa/mở áp dụng cho tất cả viewer, độc lập với thứ tự; có thể mở cả 5 hoặc khóa cả 5. Admin luôn xem được tất cả.
**Dùng thứ tự tự động** khôi phục xếp theo chỉ số, giữ trạng thái khóa đã chọn; cần bấm Lưu để áp dụng.
Cấu hình được lưu trong SQLite, có hiệu lực với access token đang sử dụng và giữ nguyên sau khi khởi động lại.
FE cập nhật quyền khi đổi tab và mỗi phút; BE kiểm tra quyền trên từng request. Nếu hai admin cùng sửa,
phiên bản cũ bị từ chối bằng HTTP 409; dùng **Tải lại cấu hình** trước khi chỉnh và lưu lại.
Scheduler luôn chạy cả 5, ưu tiên pipeline chưa hoàn thành rồi theo thứ tự admin đã lưu (hoặc thứ tự tự động).
Đặt `WEB_ADMIN_CONTACT_EMAIL` để đổi địa chỉ liên hệ. Liên kết chỉ mở email nháp, không gửi mail tự động.

API kiểm tra quyền trước cache cho trade plan, overview, signal/ID, orders, positions, trades và equity;
dữ liệu pipeline cũ chỉ dành cho admin. `/api/auth/me` trả `allowed_pipelines` để FE chọn đúng danh sách.
Không trả signal, vị thế, kế hoạch lệnh, đường vốn hay kết quả paper của pipeline bị khóa.

Đăng nhập Google tạo access JWT mặc định 15 phút (`AUTH_ACCESS_TTL_SECONDS=900`) và refresh token ngẫu nhiên
có thời hạn tuyệt đối 7 ngày (`AUTH_REFRESH_TTL_SECONDS=604800`). Access token chỉ ở bộ nhớ FE,
mọi API dữ liệu nhận `Authorization: Bearer <access_token>`; không nhận token trong URL hay cookie thay cho header.
Refresh token không trả trong JSON và không lưu trong localStorage/sessionStorage: BE đặt cookie host-only
`HttpOnly; Secure; SameSite=None`, thời hạn 7 ngày. Cục bộ dùng cookie không Secure với SameSite=Lax;
FE/API phải dùng cùng hostname (localhost hoặc 127.0.0.1). Chỉ lưu SHA-256 refresh token trong SQLite.

FE gọi `POST /api/auth/refresh` / `POST /api/auth/logout` với `credentials: include` và Origin hợp lệ;
API client có thể gửi refresh token qua `Authorization: Bearer <refresh_token>`. Token refresh cũ dùng lại sẽ thu hồi
cả phiên. Logout thu hồi access và refresh. Quyền được đọc lại trên mỗi request. FE tự refresh trước hết hạn
hoặc retry một lần khi 401; gộp refresh trong tab và dùng Web Locks để tuần tự giữa các tab.
Response auth có `Cache-Control: no-store`. Session token cũ phải đăng nhập lại sau nâng cấp.
Triển khai BE và FE cùng đợt; trên domain Vercel khác site, trình duyệt chặn third-party cookie có thể ngăn refresh:
ưu tiên domain FE `crypto.nguyenchitrai.id.vn`, cùng site với API.

CORS mặc định chỉ cho localhost và domain FE chính, không còn cho toàn bộ `*.vercel.app`.
`CORS_ALLOW_ORIGINS` phải liệt kê chính xác domain bạn sở hữu; không dùng wildcard.
Nếu `.env` cũ có `CORS_ALLOW_ORIGIN_REGEX` rộng, bỏ giá trị đó hoặc đặt trống khi nâng cấp.
API cookie refresh/logout kiểm tra Origin chống CSRF; `/api/auth/google` cũng chặn Origin lạ.
Headers bảo mật/CSP có ở BE và cả hai cấu hình Vercel. Body POST tối đa 64 KiB, kể cả chunked body.
OpenAPI/docs public tắt; endpoint admin vẫn luôn kiểm tra role. Secret và DB không nằm trong static frontend.

Scheduler mặc định chạy đủ 5 pipeline mỗi 4h và cập nhật plan giữa chu kỳ mỗi 15 phút.
Pipeline chưa hoàn thành trong chu kỳ hiện tại chạy trước, theo thứ hạng sản phẩm;
trạng thái hoàn thành từng pipeline lưu ở SQLite nên giữ được qua restart. Một plan lỗi vẫn thử các plan còn lại,
đánh dấu cycle failed và thử lại sau 60 giây; startup chạy bù chu kỳ bị thiếu. Các job v205 cũ chỉ chạy khi admin yêu cầu.

Ngay khi bật BE, scheduler luôn kiểm tra dữ liệu thực tế, kể cả khi marker cũ báo đã hoàn thành.
Trước mỗi chu kỳ 4h và mỗi lần cập nhật 15 phút, nó kiểm tra khoảng trống trong nến và tải bù,
cập nhật archive/live flow rồi bù các mốc quyết định O1/Coinbase thiếu từ lúc bắt đầu paper.
Không còn giới hạn chạy bù 14 ngày; mốc mới nhất cũng được kiểm tra. Mỗi mốc chạy bù dùng `ADVISOR_ASOF`
đúng thời điểm đó; dòng trễ hơn 6h được gắn `backfill`, không tính là bằng chứng prospective.
Coinbase và Binance spot tải bù cả khoảng trống giữa dữ liệu; spot phân trang cho các đợt tắt BE dài.

Flow archive và Coinbase/spot kiểm tra phần đầu vào cần cho paper hiện tại từ tháng 03/2026 (120 ngày recent + 90 ngày warmup trước freeze).
Các khoảng trống nghiên cứu cũ hơn vẫn giữ nguyên. File nguồn bị thiếu hàng được tải lại và thay thế hàng cũ,
không cộng trùng notional. Live flow lưu con trỏ khi còn backlog, báo lỗi để retry tiếp thay vì báo hoàn tất giả.
Nến 4h/1m dùng cho replay và các agent phải đủ đến mốc đóng gần nhất; nến đang hình thành không bị coi là thiếu.

Nếu đầu vào chưa đủ, chu kỳ báo lỗi và retry sau 60 giây trước khi tạo plan mới.
Một plan lỗi vẫn thử bốn plan còn lại; chỉ đánh dấu hoàn tất sau khi plan đúng mốc và lịch sử paper đã lưu thành công.
Khi máy thức dậy sau nhiều mốc đóng nến, scheduler chạy bù ngay thay vì chờ mốc kế tiếp.
`/health.input_check` cho biết `checking`, `failed` (kèm bước lỗi) hoặc `complete`; chi tiết lỗi ở admin jobs/log.

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

Lần chạy đầu, nếu DB trống, scheduler tự tải nến và chạy cả 5 trade plan. Backfill walk-forward dùng job admin
`walkforward_tm` khi cần. Log nằm ở `artifacts/web/backend.log`. Kiểm tra bằng `http://127.0.0.1:8724/health`.

### Xem web trên chính máy server, không cần đăng nhập

Double-click `run_frontend.bat` (hoặc chạy `.
un_frontend.ps1`) để mở `http://localhost:5500`.
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

- **Công khai:** `GET /health`, `GET /api/public/config`, `POST /api/auth/google`. `GET /api/auth/me` cần Bearer access token (hoặc chế độ local admin).
- **Viewer:**
  - `/api/overview`
  - `/api/signals/latest`
  - `/api/signals?source=live|walkforward&symbol=&start=&end=&limit=`
  - `/api/signals/at?t=`
  - `/api/signals/{id}`
  - `/api/candles?symbol=&interval=1h|4h|1d&start=&end=&limit=`
  - `/api/orders?symbol=&kind=book|dip&source=walkforward`: mỗi lệnh gồm lúc phát, giá vào trung bình, SL, TP, tỷ trọng, lúc/giá thoát, lý do, kết quả
  - `/api/orders/stats`
  - `/api/positions`, `/api/trades`, `/api/equity?source=walkforward|forward`
- **Admin:**
  - `POST /api/admin/run {kind: cycle|signal|candles|forward|walkforward}`
  - `GET /api/admin/jobs`
  - `GET|POST /api/admin/users`
  - `GET|POST /api/admin/pipelines`: `order` (đủ 5 mã, không trùng; `null` = tự động), `locked` (boolean cho từng mã), `revision` (phiên bản GET gần nhất).

## Hiệu năng

- SQLite chạy WAL, `synchronous=NORMAL`, mmap 256 MB, cache 64 MB. Bảng dùng `WITHOUT ROWID` với khoá chính khớp các truy vấn theo khoảng thời gian.
- Mỗi luồng có kết nối riêng và chỉ có một luồng ghi. Người đọc không bị chặn khi pipeline đang ghi.
- Response nóng được cache dưới dạng bytes JSON đã gzip, kèm ETag (trả 304 khi không đổi). Cache bị xoá sau mỗi job.
- Giới hạn tốc độ theo IP (`CF-Connecting-IP`): 10 request/giây, burst 40.
- Test cục bộ: khoảng 3–7 ms mỗi request, khoảng 200 request/giây với 20 người dùng đồng thời trên một process.
