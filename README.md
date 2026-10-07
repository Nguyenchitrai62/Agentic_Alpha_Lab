# Agentic Alpha Lab

Môi trường nghiên cứu và paper trading cho BTC, ETH, SOL, BNB, XRP: dự báo,
trader policy, walk-forward replay, web hiển thị kế hoạch lệnh và bot mô phỏng
khớp lệnh trên dữ liệu thị trường. Quyết định dùng nến 4h đã đóng; execution và
rủi ro intrabar được kiểm tra trên nến 1m.

> Agent tiếp quản hoặc máy vừa clone: đọc [AGENTS.md](AGENTS.md) và
> [NEXT_AGENT.md](NEXT_AGENT.md) trước. Trạng thái nghiên cứu nằm ở
> [CONTINUOUS_RESEARCH.md](CONTINUOUS_RESEARCH.md); các hướng đã đóng nằm ở
> [docs/CLOSED_DIRECTIONS.md](docs/CLOSED_DIRECTIONS.md).

## Trạng thái hiện tại — 07/10/2026

Pipeline BOT đang thu bằng chứng paper là **G2 + carry quý, f = 0,25**. G2 chạy
book và thang dip trên bốn pha giờ, dùng chung plan `trade_plan_v376.json`;
carry giữ long spot + short quarterly BTC/ETH. Tab BOT trên web gọi pipeline
này là `g2c`, bí danh hiển thị của plan `v376`.

| Sản phẩm | Kết quả nghiên cứu | Trạng thái |
| --- | --- | --- |
| BOT G2 + carry f=0,25 | Trung bình hình học 5 năm 5,634%/tháng; năm tệ nhất 2,778%/tháng; năm gần nhất 4,698%/tháng; DD năm tối đa 16,75%, DD toàn đường 16,66% | Đang paper; năm gần nhất chưa đạt sàn 5%, chưa đạt mục tiêu BOT 8%/tháng và DD <15% |
| MANUAL theo lịch đặt tay | Khoảng 3,73%/tháng; thêm carry khoảng 3,993%/tháng | Chưa đạt sàn 5%/tháng |

Các số BOT là ước lượng replay có tái đầu tư lãi carry. Win rate book + dip
của G2 khoảng 65,3%, không phải win rate riêng của book hay kết quả paper.
Toàn bộ 5 năm nghiên cứu đã được xem; bằng chứng sạch tiếp theo là log prospective.
Không diễn giải trung bình 5 năm thành lợi nhuận đạt được mỗi tháng.
Nguồn và giới hạn: [báo cáo hợp nhất](docs/FINAL_REPORT_VI.md) và
[tóm tắt cho chủ tài khoản](docs/SUMMARY_FOR_OWNER_20261007_VI.md).

Live cần yêu cầu rõ ràng của chủ tài khoản, testnet sạch và đủ các cổng paper
đã đăng ký trong [kế hoạch triển khai](docs/DEPLOYMENT_PLAN_VI.md).

## Cấu trúc repo

| Thư mục | Nội dung |
| --- | --- |
| `backend/` | FastAPI + SQLite WAL; scheduler tạo plan và thu thập dữ liệu |
| `frontend/` | Site tĩnh: Google login, kế hoạch entry/SL/TP, History, Performance, BOT |
| `bot/` | Mirror plan, paper exchange, bảo vệ vị thế, carry và risk guard |
| `scripts/` | Chạy pipeline, kiểm tra sức khỏe, scorecard và công cụ vận hành |
| `research/parallel/rounds/` | Mã thí nghiệm theo phiên bản và registry |
| `research/tournament/` | Mã sàng lọc, audit, kế hoạch và báo cáo nghiên cứu |
| `src/agentic_alpha_lab/` | Data, model adapter, training và backtest nền tảng |
| `tests/` | Kiểm thử timing, chi phí, execution, bot và API |
| `docs/` | Hướng dẫn hiện tại; tài liệu cũ ở `docs/legacy/` và `docs/research_reports/` |

`../Kronos` là upstream tham chiếu, không sửa từ repo này.
`archive/legacy_web_dashboard/` là demo snapshot cũ, không phải web hiện tại.

## Cài đặt Windows

Cần Python >=3.11. Nếu dùng GPU NVIDIA, cài wheel Torch theo phiên bản đã ghi
trong `requirements.txt` trước khi cài các thư viện còn lại:

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install --upgrade pip
./.venv/Scripts/python.exe -m pip install torch==2.12.1 --index-url https://download.pytorch.org/whl/cu126
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
./.venv/Scripts/python.exe -m pip install -e .
```

Cấu hình local theo [.env.example](.env.example); `.env` và khoá truy cập không
đưa vào Git. Clone mã nguồn không kèm dữ liệu, checkpoint hay plan đã tạo:
cần phục hồi các artifact phù hợp trước khi chạy pipeline nghiên cứu hiện tại.
Heavy training dùng Kaggle private/free GPU; GTX1650 local dành cho inference,
replay và backtest. Entry point GPU trên Windows phải import `torch` trước `pandas`.

## Web và paper

Backend chạy local tại `127.0.0.1:8724`, public qua Cloudflare Tunnel;
frontend chạy trên Vercel hoặc local ở `localhost:5500`.

```powershell
# Kiểm tra backend hiện có; chỉ khởi động nếu chưa chạy
./run_backend.ps1 -Status
./run_backend.ps1 -Background

# Mở frontend local
./run_frontend.ps1
```

Backend tạo plan theo lịch; request API đọc dữ liệu đã lưu. Bot paper đọc plan
và dùng Bybit 1m public để mô phỏng fills. Chạy thử khô một cycle:

```powershell
./.venv/Scripts/python.exe -m bot.run --once --equity 5000 `
  --corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0 `
  --adopt-fresh --carry-f 0.25 --interval 25

# Chỉ chạy một runner cho mỗi tag/thư mục state
./.venv/Scripts/python.exe -m bot.run --mode paper --equity 5000 `
  --corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0 `
  --adopt-fresh --carry-f 0.25 --interval 25 --tag d17bfg2c

# Kiểm tra trạng thái và bảo vệ vị thế
./.venv/Scripts/python.exe scripts/daily_status.py --fast
./.venv/Scripts/python.exe scripts/bot_health.py artifacts/bot/paper_d17bfg2c
```

Sau reboot, dùng [scripts/restart_all.ps1](scripts/restart_all.ps1) theo runbook
để khôi phục backend và paper runners. Hướng dẫn chi tiết:
[Quickstart](docs/QUICKSTART_VI.md), [Bot runbook](docs/BOT_RUNBOOK_VI.md),
[Bot execution](docs/BOT_EXECUTION.md), [Web deploy](docs/WEB_DEPLOY.md).

## Quy tắc kiểm định và lưu file

- Feature tại `t` chỉ dùng dữ liệu có sau khi nến `t` đóng. Lệnh mới không fill
  trong 5 phút đầu; từ phút 5 dùng 1m trade-through, không suy ra vị trí hàng đợi.
- Fit và chọn model/tham số trước mỗi anchor với embargo >= forecast horizon.
  Chỉ chọn biến thể trên bốn năm đầu; năm cuối chấm một lần cho finalist.
- Entry limit, TP limit, SL market; unfilled entry hết hạn, không fallback
  market. SL được ưu tiên nếu SL và TP cùng chạm trong một nến 1m.
- Gate costs: maker 0,02%, taker 0,055%; long trả funding 0,01%/8h, short
  không nhận. Carry quarterly có báo cáo riêng, không suy ra funding income
  cho perp. DD gate là max DD toàn đường 4h-close và 1m-marked.
- Báo cáo gross PnL, phí, funding, net PnL, DD, số lệnh, coverage và các giả định
  execution; lưu range dữ liệu, checkpoint, tham số và nguồn artifact.
- Commit mã nguồn, test, config và tài liệu. Dữ liệu tải về, model, prediction,
  kết quả JSON/CSV, log và scratch giữ local qua `.gitignore`; model triển khai
  ở `models/frozen/`, trạng thái bot ở `artifacts/bot/`. Không xoá dữ liệu local
  để làm sạch Git. Kế hoạch và báo cáo Markdown được giữ để truy lại nghiên cứu.

Chạy kiểm thử trước khi bàn giao:

```powershell
./.venv/Scripts/python.exe -m pytest
```

Một số test nghiên cứu đối chiếu dữ liệu và artifact local đã audit; clone mới
cần phục hồi đúng snapshot để chạy các test này. `SKIP_SLOW=1` bỏ qua các replay
dài có hỗ trợ tùy chọn đó; kết quả kiểm thử cần ghi rõ số pass, fail và skip.

Baseline Kronos/Colab cũ: [docs/legacy/TRAINING.md](docs/legacy/TRAINING.md).
Các kết quả engine cũ phải ghi rõ phiên bản khi so với replay hiện tại.
