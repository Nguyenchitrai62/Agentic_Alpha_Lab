# Agentic Alpha Lab

> Coding agent mới hoặc một máy vừa clone repo: đọc
> [`NEXT_AGENT.md`](NEXT_AGENT.md) trước khi cài đặt hay chạy thí nghiệm.

Môi trường nghiên cứu leakage-aware cho BTC futures: dữ liệu Binance USD-M,
Kronos zero-shot, chuyển forecast thành signal, backtest limit-order, và sau đó
mở rộng sang fine-tuning/agentic experiment search.

## Trạng thái vòng đầu

- Market: `BTCUSDT` Binance USD-M perpetual.
- Timeframe: nến 5 phút đã đóng.
- Model: Kronos mini/small/base từ checkpoint chính thức.
- Execution: tín hiệu tại cuối nến `t`, entry limit chỉ hoạt động từ nến `t+1`.
- Fee: 0.02% cho mỗi fill entry và exit (0.04% khứ hồi).
- Funding: long 0.01% tại mỗi mốc 8 giờ; short bằng 0 theo giả định nghiên cứu.
- Intrabar ambiguity: nếu TP và SL cùng chạm trong một nến, backtest ưu tiên SL.

Đây là research backtest, không phải hệ thống live trading.

## Cài đặt Windows + NVIDIA

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install torch==2.12.1 --index-url https://download.pytorch.org/whl/cu126
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

Kronos được giữ như repo sibling ở `..\Kronos`; không copy hoặc sửa mã upstream.

## Chạy

```powershell
# Lấy 30 ngày BTCUSDT 5m đã đóng
.\.venv\Scripts\python.exe scripts\download_btc.py --days 30

# Smoke/latency benchmark ba checkpoint công khai
.\.venv\Scripts\python.exe scripts\download_kronos_models.py --variants mini small base
.\.venv\Scripts\python.exe scripts\benchmark_kronos.py --variants mini small base

# Rolling forecast + bracket backtest (bắt đầu nhỏ vì autoregressive khá chậm)
.\.venv\Scripts\python.exe scripts\run_kronos_backtest.py `
  --variant mini --max-windows 256 --stride 3 --batch-size 8

# Kiểm thử execution/cost model
.\.venv\Scripts\python.exe -m pytest
```

Kết quả feasibility đầu tiên được tóm tắt trong `PHASE_A_RESULTS.md`.

Artifacts sinh ra trong `artifacts/` và `reports/`; raw data không được commit.

Drawdown hiện được mark-to-market theo nến trong thời gian giữ lệnh và engine đã
có sizing/đòn bẩy cùng liquidation gần đúng. Trước khi paper trade vẫn cần dữ liệu
mark price, lịch funding lịch sử, slippage và risk tier thật. OHLC không chứng minh
được vị trí hàng đợi của limit order.

## Quy tắc chống look-ahead

1. Mọi context kết thúc tại nến đã đóng `t`.
2. Future timestamp được biết trước, nhưng future OHLC không được truyền vào model.
3. Entry bắt đầu từ `t+1`; limit chỉ fill nếu OHLC thật chạm giá limit.
4. Model selection chỉ dùng validation; locked test không dùng để chỉnh threshold.
5. Funding được tính theo thời gian UTC thực tế giữ vị thế.
