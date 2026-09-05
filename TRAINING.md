# Training / Colab — vòng supervised đầu tiên

Đọc `AGENTS.md` trước. Đây là research/paper trading, không có kết nối đặt lệnh.
Các lệnh chạy từ root của **Agentic_Alpha_Lab**, không phải repo Kronos sibling.

## Đã có gì

- 36 feature từ nến đã đóng 5m/15m/1h/4h, join backward theo thời điểm đóng nến.
- Label hướng SHORT/WAIT/LONG và return 1h/4h/24h. WAIT band 8 bps vượt phí khứ hồi 4 bps;
  đây chỉ là band cố định, không bao quát mọi funding/slippage tương lai.
- Label phụ: excursion lên/xuống từ close và next-bar limit-touch. Đây **không** phải
  MFE/MAE sau khi entry thực sự khớp, hay xác suất khớp maker trong hàng đợi.
- Chia thời gian train/validation/calibration/test, purge label chồng biên và embargo 289 nến.
- Mean/std chỉ fit train. MLP hai hidden layer 64, nhiều head direction và P10/P50/P90
  được ép đúng thứ tự; early stopping trên validation. Temperature fit calibration riêng.
- Logistic regression mỗi horizon làm baseline validation. Chưa có tree baseline,
  Kronos embeddings, fusion attention, head excursion/fill đã train, hay RL.
- Quy tắc trading cố định: probability >= 0.60, median cùng hướng >= 8 bps,
  entry offset 2 bps; SL/TP1/TP2 dựa ATR 5m, 1x, TP1 đóng 50%, timeout 48 nến.
  Đây là hướng + quantile gate, **chưa phải model tự học giá entry/TP/SL**.
- Export safetensors + JSON với schema feature, scaler, config, seed, temperature,
  hash data/model/source và Git SHA. Khi code chưa commit, source hashes mới là dấu vết chính xác.

## 1. Chuẩn bị dataset bất biến

```powershell
.\.venv\Scripts\python.exe scripts/build_training_dataset.py --output data/processed/btc_20260905_v1
```

Output tồn tại sẽ báo lỗi, không ghi đè. Chọn tên version mới khi dữ liệu/config đổi.
Snapshot gồm candles, bốn tập Parquet, config và manifest SHA-256. Nến thiếu, trùng,
không hữu hạn, sai OHLC/grid hoặc chưa đóng bị từ chối; không fill dữ liệu thiếu giả.

Dataset đã tạo local: 4.263 train / 560 validation / 182 calibration / 849 test.
Source 2026-08-06 08:10 → 2026-09-05 08:04:59.999 UTC, chỉ 30 ngày.
Calibration cực ngắn; nhãn chồng thời gian nên số quan sát độc lập thấp hơn số dòng.
Khoảng này đã từng dùng nghiên cứu Kronos: dù tách chronological, **không gọi là forward test mới**.

Để thu thập lịch sử dài hơn mà không đụng nguồn 30 ngày:

```powershell
.\.venv\Scripts\python.exe scripts/download_btc.py --days 1095 --output data/raw/binance_usdm/BTCUSDT/5m/history_3y.parquet
.\.venv\Scripts\python.exe scripts/build_training_dataset.py --data data/raw/binance_usdm/BTCUSDT/5m/history_3y.parquet --output data/processed/btc_3y_v1
```

Downloader hiện dùng REST với `days` tương đối và có thể cập nhật file raw;
snapshot processed mới là bản đóng băng dùng tái lập. Lưu manifest, không chỉ tên file.
Chưa tải 3 năm trong vòng smoke này; vẫn thiếu mark/index, funding thực, OI và risk tiers.

## 2. Train local hoặc trên Colab

Local (torch đã cài trong venv):

```powershell
.\.venv\Scripts\python.exe scripts/train_baseline.py --dataset data/processed/btc_20260905_v1 --output artifacts/checkpoints/mlp_new_run
```

Mặc định tự chọn CUDA nếu có, `--device cpu` dùng CPU. FP32 có chủ đích vì head rất nhỏ;
chưa triển khai AMP. `--epochs 2` chỉ dành smoke và được ghi vào metadata.
Training **không mở test**. Không đổi config sau khi xem kết quả test của cùng vòng.

Colab:

```powershell
.\.venv\Scripts\python.exe scripts/package_colab.py --dataset data/processed/btc_20260905_v1 --output artifacts/colab_btc_new_bundle.zip
```

1. Mở `notebooks/train_colab.ipynb` trong Colab, dùng runtime mới, Python >= 3.11.
2. Upload ZIP của chính bạn. Notebook kiểm tra đường dẫn ZIP và hash, cài dependency,
   dùng PyTorch sẵn của runtime (phiên bản được ghi metadata), rồi train bằng subprocess.
3. Download `alpha_lab_checkpoint.zip`; giải nén vào một thư mục checkpoint mới local.
4. Giữ dataset local nguyên vẹn để đánh giá. ZIP training cố ý **không chứa test hoặc raw candles**.

Không cần Drive mount, API key hoặc quyền sàn. ZIP dùng allowlist source/config/splits,
không copy venv, node_modules, secrets hay checkpoint Kronos. Hash phát hiện thay đổi,
không bảo đảm một ZIP từ người lạ là an toàn. Chỉ chạy code từ bundle đáng tin.

Notebook đã kiểm tra cú pháp các code cell và đã chạy pipeline tương ứng local;
**chưa thực thi trên một Colab runtime thật**. Pin dependency có thể cần điều chỉnh theo
runtime tương lai; ghi version mới thành experiment mới, không sửa lặng lẽ checkpoint cũ.

## 3. Đánh giá checkpoint sau khi tải về

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_checkpoint.py --dataset data/processed/btc_20260905_v1 --checkpoint artifacts/checkpoints/mlp_new_run --output reports/supervised/new_run
```

Lệnh xác minh hash checkpoint, manifest, test và candle snapshot; áp policy lưu trong metadata.
Output gồm summary JSON, signals Parquet, trades CSV. Vốn ban đầu đúng **100**, tính lãi kép.
Phí entry/exit **0.02% mỗi fill**, long funding **0.01%/8h**, short funding **0**.
Thêm một kịch bản phí đều **0.055%/fill** để stress; đây không phải biểu phí sàn được xác minh,
và không thay cho mô phỏng hàng đợi/slippage.

Engine `ohlc-v2` bỏ TP không xác định thứ tự trên nến entry intrabar; reject cửa sổ
không đủ horizon; funding dùng quantity × trade-open tại boundary làm proxy mark price.
SL/timeout hiện là **market-like exit tính phí giả định**, không phải guarantee limit fill.
Max DD lấy mẫu equity theo close nến giữ lệnh và điểm exit, chưa đo mọi intrabar trough.
Liquidation vẫn gần đúng: thiếu mark/risk tiers, thay đổi margin do funding/phí và queue.
Vì thế không khẳng định mô phỏng hiện tại bảo thủ trong mọi trường hợp.

## 4. Kết quả smoke đã mở ngày 2026-09-05

Checkpoint chính: `artifacts/checkpoints/mlp_20260905_v2` (v1 trước đó thiếu source-hash metadata).
V1/v2 cho cùng chuỗi validation loss; lần v2 bổ sung provenance, không đổi model/config.
Báo cáo: `reports/supervised/mlp_20260905_v1/summary.json`.

| Chỉ tiêu | Kết quả |
|---|---:|
| Vốn 100 thành | 99,6459 |
| Net return | -0,3541% |
| Max DD close-sampled | -0,9029% |
| Gross PnL / phí / funding, vốn 100 | +0,13419 / 0,47832 / 0,00999 |
| Lệnh | 12 long, 0 short |
| Win rate / profit factor | 41,67% / 0,8051 |
| Coverage tín hiệu | 9,07% (77/849 quyết định) |
| Direction accuracy 4h / ECE 4h | 47,00% / 9,32% |
| P10–P90 coverage 4h | 71,97% (danh nghĩa 80%) |
| Net return với phí stress | -1,1882% |

Early stopping sau 12 epoch, checkpoint tốt nhất epoch 6, temperature 1,2.
Không đạt acceptance gate. Số lệnh ít, chỉ long, test/calibration ngắn và ECE còn cao.
Không thay ngưỡng để làm đẹp tập này; không bật leverage.

## 5. Việc tiếp theo — theo thứ tự

1. Lịch sử nhiều năm, nhiều regime, nguồn immutable/mark/funding và cửa sổ forward mới chưa xem.
2. Walk-forward nhiều fold, logistic + tree + MLP cùng policy/cost và cùng các fold.
3. Chỉnh execution thành post-only/queue-aware entry/TP, explicit stop-market vs stop-limit,
   order expiry/cancel và stress fill; kiểm thử gap/liquidation với mark data.
4. Nếu baseline có bằng chứng tốt hơn: cache Kronos-mini embeddings, train fusion head;
   sau đó mới thử unfreeze block cuối, excursion/fill heads và kiến trúc phức tạp hơn.
5. Forward paper trading; chưa live. Không tối ưu kiến trúc bằng reward backtest khi simulator còn dễ bị khai thác.
