# Kronos BTC đa khung — thí nghiệm Kaggle v1

Đọc `AGENTS.md` trước. Đây là nghiên cứu, không phải bot đặt lệnh và không phải RL.

## Kiến trúc đã triển khai

`nến đóng 5m/15m/1h/4h → tokenizer Kronos-2k → shared Kronos-mini → attention đa khung → điểm cho 8 bracket → LONG/SHORT/WAIT + entry/SL/TP1/TP2`

- Mỗi khung 64 nến. Chuẩn hóa riêng từng cửa sổ quá khứ, clip ±5; không fit trên tương lai.
- Tokenizer và backbone **pretrained Kronos thật**, giữ frozen trong v1.
- Lấy hidden cuối + mean hidden, bổ sung embedding khung và tuổi nến khung cao.
- Fusion Transformer 128 chiều, 4 attention heads; head có điều kiện theo bracket.
- 8 phương án: 2 hướng × entry offset 2/5 bps × hai bộ SL/TP1/TP2 theo ATR.
- Đầu ra: mean net, net quantiles P10/P50/P90 có thứ tự, OHLC-fill score, positive-net score.
- Model học **chọn bracket trong menu cố định**, chưa hồi quy tự do mọi mức giá.
  Giá cụ thể thay đổi với close/ATR hiện tại; không chọn entry/TP nhìn từ tương lai.
- WAIT nếu không có mean net > 2 bps và win score >= 0.55. Ngưỡng cố định trước run.
  Các score **chưa calibration**, không được coi là xác suất đáng tin để tăng leverage.
- Kronos backbone chưa fine-tune. Chỉ cân nhắc mở block cuối khi frozen head và các
  cheap baselines có bằng chứng validation/walk-forward; không tự đổi tokenizer hoặc chạy RL.

## Dữ liệu và nhãn

Nguồn local: `data/processed/btc_3y_20260905_v1/candles.parquet`, snapshot 3 năm.
Dataset mới: `data/processed/kronos_mtf_20260905_v1`.
3.875 train + 971 validation, lấy quyết định mỗi 48 nến 5m (4 giờ), không phải infer mỗi 5 phút.
Hai khung quyết định có thể còn nhãn chồng 1 nến timeout; số mẫu không đồng nghĩa số quan sát độc lập.
Giữ split/embargo từ snapshot trước; chỉ bỏ các mẫu thiếu đủ 64 nến 4h.
Train thuộc 2023–06/2025, validation 06–12/2025. Không gọi đây là forward test mới.
Chưa kiểm toán sự trùng lặp dữ liệu pretraining upstream với lịch sử đánh giá.

Nhãn cho mỗi bracket dùng trực tiếp engine `ohlc-v2`, vốn 100, 1x:

- entry limit có hiệu lực nến kế tiếp, hết hạn sau 1 nến;
- giữ tối đa 48 nến kể từ fill; TP1 đóng 50%; TP2 đóng phần còn lại;
- 0.02% mỗi fill entry/exit; long trả 0.01% tại 00/08/16 UTC khi giữ vị thế;
- short funding bằng 0; unfilled payoff = 0; stop-first khi OHLC mơ hồ;
- stop/timeout là market-like tại phí giả định, không bảo đảm maker;
- TP trên nến entry intrabar bị chặn vì không biết thứ tự giao dịch.

Không có mark price, queue/orderbook hay OI; nhãn không chứng minh khả năng khớp post-only thực tế.
Backtest portfolio không mở vị thế chồng nhau, dùng vốn lãi kép 100 và DD close-sampled.
Validation dùng chọn checkpoint theo loss, không dùng chọn lợi nhuận đẹp nhất.
Có báo cáo fee stress 0.055% mỗi fill (kịch bản, không phải biểu phí đã xác minh).
Chưa có calibration, untouched-test report, walk-forward hoặc acceptance cho live.

## Lệnh tái lập

Chạy từ repo này, không phải upstream Kronos. Mọi tên output phải mới, không ghi đè:

```powershell
.\.venv\Scripts\python.exe scripts/build_kronos_trading_dataset.py --output data/processed/kronos_mtf_NEW
.\.venv\Scripts\python.exe scripts/train_kronos_trading.py --dataset data/processed/kronos_mtf_NEW --output artifacts/checkpoints/kronos_mtf_NEW
.\.venv\Scripts\python.exe scripts/package_kaggle.py --dataset data/processed/kronos_mtf_NEW --output artifacts/kaggle/kronos_mtf_NEW --owner YOUR_KAGGLE_USERNAME --slug kronos-btc-mtf-NEW
```

Slug phải chữ thường/số/dấu gạch nối. Muốn smoke, builder có `--max-rows 16`, trainer
có `--epochs 2`. Packager từ chối smoke dataset khi đóng gói thí nghiệm đầy đủ.

Bundle allowlist gồm source, pretrained mini/tokenizer, upstream source + MIT LICENSE,
raw windows và development candles cắt ở 2025-12-05. **Không có calibration/test candles,
API token, venv, node_modules**. Metadata chỉ có ngày biên test, không có dữ liệu test.
Toàn bộ data/artifacts bị Git ignore. Không đưa `.kaggle/access_token` vào repo.

## Kaggle CLI trên Windows

CLI 2.2.4 đã cài trong venv. Token ở `%USERPROFILE%/.kaggle/access_token` (ngoài repo).
Không in token, không đưa vào notebook. Tài khoản đã xác thực: `nguynchtrai`.
Không tạo/gửi lại token qua chat; đổi token cũ đã lộ trong ảnh sau phiên sử dụng.

CLI bản này lỗi upload nếu `-p` là đường dẫn nhiều thành phần trên Windows.
Chuyển cwd vào chính thư mục staging rồi dùng `-p .`:

```powershell
# cwd = artifacts/kaggle/kronos_mtf_20260905_v1/dataset
C:\TRAI_NC\Source_code\Agentic_Alpha_Lab\.venv\Scripts\kaggle.exe datasets create -p . --keep-tabular
# Không dùng --public. Chờ datasets status <owner/slug-data> = ready.
# cwd = artifacts/kaggle/kronos_mtf_20260905_v1/kernel
C:\TRAI_NC\Source_code\Agentic_Alpha_Lab\.venv\Scripts\kaggle.exe kernels push -p . --accelerator NvidiaTeslaT4 --timeout 3600
```

Job private; bootstrap kiểm đúng 2 T4 trước khi training. Hai GPU chia batch encode
Kronos bằng DataParallel, **không cộng VRAM thành một GPU**. Fusion head nhỏ train GPU0.
Giữ PyTorch/CUDA/numpy/pandas runtime Kaggle; ghi phiên bản thực tế vào `runtime.json`.
Dependency nhỏ cài lúc khởi động; pretrained weights tải từ bundle, không tải từ HF lúc run.

Job: https://www.kaggle.com/code/nguynchtrai/kronos-btc-mtf-20260905-v1
Dataset private: https://www.kaggle.com/datasets/nguynchtrai/kronos-btc-mtf-20260905-v1-data
Bundle 50,279,878 bytes; SHA256 `bed9001be546bef60cb3799bc31ff338a22b0a7d361a6926318ec649bbca8bc6`.
Job v1 đã push thành công; trạng thái/kết quả cuối ghi ở phần cập nhật dưới đây.
Không push lại cùng job trong lúc chạy vì sẽ tạo phiên bản/run khác và tiêu quota.

## Đọc kết quả / infer

```powershell
.\.venv\Scripts\kaggle.exe kernels status nguynchtrai/kronos-btc-mtf-20260905-v1
.\.venv\Scripts\kaggle.exe kernels output nguynchtrai/kronos-btc-mtf-20260905-v1 -p artifacts/kaggle/results_v1
```

Kaggle output gồm `checkpoint/` và `kronos-btc-checkpoint.zip`: fusion.safetensors,
metadata/source/weights hashes, runtime GPU, loss history, validation predictions,
trades và report. Checkpoint fusion phải đi cùng đúng pretrained mini/tokenizer và source
upstream có hash đã lưu; không phải file độc lập thay được bằng Kronos-small/base.

```powershell
.\.venv\Scripts\python.exe scripts/infer_kronos_trading.py --checkpoint artifacts/kaggle/results_v1/checkpoint --candles data/processed/kronos_mtf_20260905_v1/development_candles.parquet
```

Lệnh infer không đặt lệnh. Thử trên development trước; muốn đọc khoảng test hoặc
fresh/latest data phải ghi nhận rõ đó là inference/evaluation, không lén dùng để tuning.
Web hiện vẫn là dashboard zero-shot/MLP cũ, **chưa nối inference mới**.

## Trạng thái kiểm thử local

- **30 tests pass**; tests mới cho as-of window, nến cao chưa đóng, ordered brackets, WAIT/nonfinite,
  label parity với engine, quantiles/gradient fusion và allowlist/privacy/hash bundle.
- Smoke 16 train / 16 validation, 2 epochs chạy trên GTX1650, lưu/load/infer thành công.
- Smoke trả WAIT, 0 lệnh; không dùng số này để chứng minh model tốt.

## Kết quả thực tế Kaggle v1 (2026-09-05)

**COMPLETE, đã tải output và kiểm hash/replay local thành công.**
Runtime xác nhận 2 × Tesla T4, torch 2.10.0+cu128, Python 3.12.13, numpy 2.0.2,
pandas 2.3.3. Frozen encode dùng DataParallel. Training script chạy khoảng 16,67 giây
(không gồm chờ máy, bootstrap/pip, upload/download); đây là head nhỏ trên cached embeddings.
Early stop epoch 16, checkpoint tốt nhất epoch 11.

| Validation (đã dùng chọn checkpoint, không phải test) | Kết quả |
|---|---:|
| Vốn 100 thành | 100 |
| Net return / close-sampled DD | 0% / 0% |
| Lệnh / coverage | 0 / 0% |
| Gross / phí / funding | 0 / 0 / 0 |
| Profit factor | Không xác định (không có lệnh) |
| Fusion validation loss | 0,172993 |
| Train-fitted constant predictor validation loss | 0,178436 |

Loss thấp hơn constant predictor **không chứng minh hiệu quả trading** hoặc tốt hơn tree/MLP.
Model WAIT cả 971 quyết định: 66 candidate có mean net dự báo >2 bps, nhưng không candidate
nào vượt positive-net score 0,55 (thực tế 0,2442–0,4680). Không đổi ngưỡng sau run.
Quan trọng: score này là P(net>0) **tính cả non-fill**, không phải win rate khi đã khớp.
Gate 55% chưa calibration có thể loại cả cơ hội kỳ vọng dương với payoff bất đối xứng.
Cả 8 candidate có net trung bình âm trong train và validation; không thể suy ra chỉ cần
hạ ngưỡng hoặc tăng độ phức tạp là sẽ có lãi.

Checkpoint: `artifacts/kaggle/results_v1/checkpoint/fusion.safetensors`.
SHA256 `b44eda32a69894e9c2c6d3792bff3ff7566d163a70fc1660d75b226cc050f943`.
Audit `artifacts/kaggle/results_v1/local_audit.json`: hash dataset/source/upstream/weights
đúng; replay 16 mẫu validation local sai khác tối đa 7,16e-7 so với Kaggle.
Infer toàn pipeline với checkpoint tải về thành công (development snapshot trả WAIT).
Không mở calibration/test và không nối live trading.

CLI download log cần `$env:PYTHONUTF8='1'` trên Windows để tránh lỗi ghi Unicode.
Output và log đã tải đủ; không chạy lại notebook chỉ vì thấy exit code từ lỗi encoding lần đầu.

## Bước nghiên cứu tiếp theo

Nếu chỉ WAIT hoặc vẫn lỗ, không hạ ngưỡng dựa trên test và không dùng leverage cứu chiến lược.
V2 nên tách P(fill) và outcome có điều kiện sau fill, calibration trên phần riêng,
chọn theo expected net/risk thay vì mặc định coi win-rate >55% là bắt buộc; policy mới
phải được ghi config version mới trước đánh giá. So sánh tree/MLP cùng labels và walk-forward.
Chỉ sau đó cân nhắc unfreeze block cuối; chưa tự động search kiến trúc hay train tiếp vô hạn.
