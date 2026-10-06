# Tăng trưởng đĩa (đo 2026-10-06 ~22:25 +07, chỉ đọc)
1. Ổ đĩa: còn trống ~144,1 GB / 487,2 GB. File lớn nhất là `artifacts/web/app.db` 170,8 MB (+wal 3,9 MB).
2. `data/raw/topbook_live` 35,1 MB; ngày đủ 05/10 là 19,27 MB -> ~19,3 MB/ngày; 30d ~615 MB, 180d ~3,5 GB, 365d ~7,1 GB.
3. `data/raw/liquidations_live` 0,34 MB; 05/10 là 0,19 MB -> ~0,18 MB/ngày; 30d ~5,7 MB, 180d ~32 MB, 365d ~65 MB.
4. Bot `actions.jsonl` mỗi bot chạy ~0,27-0,35 MB/ngày (paper 0,33; d13bf 0,28; d17bf 0,28; d17bfg2 0,30; g2k20 0,27); g2c 0,43 và g2k20c 0,78 là burst cửa sổ ngắn.
5. `stdout.log` song hành `actions.jsonl` (~0,26-0,35 MB/ngày/bot); `runner.log` paper 0,28 MB/ngày (chỉ 2 bot có file này).
6. Chiếu/file/bot: 30d ~8-13 MB, 365d ~100-160 MB nếu giữ tốc độ hiện tại và không xoay vòng.
7. `state.json` live 0,05-0,53 MB/bot (tổng ~1,6 MB), `exchange.json` 17-27 KB; cả hai VIẾT LẠI TOÀN BỘ mỗi cycle (mtime trùng tới giây, JSON dict).
8. Creep `state.json`: +39-57 KB trong ~7,5h kể từ bak 14:34Z -> ~0,13-0,18 MB/ngày/bot; chi phí I/O tăng theo size vì rewrite toàn bộ.
9. `_bak_*`: 4 snapshot/bot trong ngày 06/10 (0,08-0,51 MB/cái, tổng ~4,6 MB); `state.json.bak_*` 2 bản/bot (tổng ~2,9 MB). Tổng bot live ~13,7 MB.
10. `advisor_shadow/shadow.jsonl` 1,07 MB / 12 ngày -> 0,089 MB/ngày; 30d 3,7 MB, 180d 17 MB, 365d 34 MB; cả thư mục 19,9 MB (pkl ~18 MB tĩnh).
11. `trade_plan_v*.json` ~0,5 MB bộ đang chạy, ghi đè trong ngày (~0,2-0,3 MB/ngày churn); `app.db` upper-bound ~19 MB/ngày từ 27/09 -> 30d ~740 MB, 365d ~7 GB nếu không chặn.
12. Log nhỏ: `backend_logs` 0,013 MB; `cloudflared_api.log` 0,39 MB (~0,04/ngày); `backend.log` 0,94 MB đã dừng từ 03/10; `_kline_cache` 0,17 MB rewrite liên tục nhưng bị chặn; `_retired` 0,30 MB tĩnh.
13. Đề xuất xoay vòng (chỉ đề xuất, KHÔNG xóa): `_bak_*` giữ 2 bản/bot, `state.json.bak_*` giữ 1 bản, nén gzip bản cũ; `actions/stdout/runner.log` xoay theo ngày giữ 14 ngày.
14. `app.db` VACUUM + retention (giữ 30-90 ngày gần nhất, archive phần còn lại); `topbook_live`/`liquidations_live` giữ parquet 30 ngày nóng, còn lại nén/aggregate theo ngày; log API giữ 7-14 ngày.
15. Tạo bởi `scripts/disk_growth.py` (`--json`); kiểm tra bằng `tests/test_disk_growth.py`. Không đụng process/state đang chạy.
