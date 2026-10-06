# Paper post-restart (restart 2026-10-06 04:37 UTC, code 990e26d; check ~05:40 UTC)

Read-only: không sửa code, không commit, không chạm state.json/process. Đọc: AGENTS.md, PAPER_DAY2_20261006.md, BOT_EXECUTION.md (bot_opsfix + bot_testnetfix), paper_report.py, bot_health.py + actions/exchange/backup/cache.
Plan tươi `2026-10-06T05:01:04Z` (0.7h). Backup `_bak_20261006T043735Z` đủ 5 dir.

## 1. Từng runner kể từ restart (op post-restart; fill/P&L; sức khỏe)

| bot | sức khỏe | op từ 04:37 UTC | fills/P&L từ restart |
| --- | --- | --- | --- |
| paper | WARNING (15 rate-limit CŨ, dòng cuối `2026-10-05T12:01:04 cycle_error BybitError 10006`, 0 mới) | cancel 25 / place 25 | fill 0; eq 4998.44→4999.10 (+0.66 unrealized, fees 0.1118/fund 0.1083 không đổi) |
| paper_d17bf | OK | bear 1 / cancel 25 / amend 6 / place 25 | fill 0; eq 4999.24→4999.49 (+0.25, fees/fund không đổi) |
| paper_d17bfg2 | CRITICAL lúc check (`last cycle 24.1m ago`, actions cuối `2026-10-06 05:16:04.454655`) — NHƯNG state.json mtime 12:41:27+0700 (=05:41 UTC) tươi: kẹt ~25p rồi heartbeat lại | bear 1 / cancel 24 / amend 2 / place 24 | fill 0; eq 4999.24→4999.49 (+0.25) |
| paper_g2k20 | OK | bear 1 / cancel 21 / amend 5 / place 21 (amend `05:38:02/05:39:19 d1XRP30hrvscE qty 65.7→65.6`) | fill 0; eq 4999.24→4999.49 (+0.25) |
| paper_d13bf | OK | bear 1 / cancel 25 / amend 13 / place 25 | fill 0 (exec cuối 02:54); eq 4999.48→4999.67 (+0.19, fees 0.0325/fund 0.0 không đổi) |

0 `postonly_reject / risk_reject / stale_plan / error / market_exit` cả 5 từ restart. Max exec toàn là 02:35 (d13bf 02:54) → drift equity là mark-to-market vị thế mở, không phải fill mới. Unprotected none, qty_mismatch none cả 5.

## 2. skipped_below_minimum: chưa kiểm chứng live được

- 0 event từ restart cả 5. Lần cuối trước restart toàn format cũ mỗi cycle: d17bfg2 `2026-10-06T04:12:06 ... {"links": ["d2SOL30hrvncE"]}`, g2k20 `04:12:28 ... ["d2ETH30hrvncE"]`, paper `02:59:42 ... ["d3BTC40hrvicE", ...]` (mỗi ~20-25s).
- Kết luận: dedupe "1 dòng/(link, bar 4h)" không có dữ liệu live để xác nhận; chỉ thấy noise cũ đã im (kỳ vọng sau restart).

## 3. GTC→PostOnly: KHÔNG có cancel/re-place nào chỉ vì đổi TIF

- Same-link đổi TIF = 0 cả 5. Cancel ~05:00 là xoay bar: `d1*hrvloE` (GTC, bak) → `d1*hrvscE` (PostOnly, now), vd stdout `{"orderLinkId": "d1BTC50hrvscE", ..., "timeInForce": "PostOnly"}`.
- Entry mới toàn PostOnly (25/25/24/21/25 theo thứ tự bảng); TP/SL giữ GTC/market; vài amend qty nhỏ cùng giá (vd `d2XRP35hrvncE 88→88.1`), không phải hệ quả TIF.

## 4. Kline cache chia sẻ: có dấu hiệu chạy

- 5 JSON tươi `12:39:2x +0700` (=05:39 UTC, sau restart 04:37 UTC); lock từ 11:38. 0 rate-limit mới cả 5 (paper WARNING chỉ do 15 lỗi cũ 24h).
- Read-only nên không chứng minh từng runner đọc qua cache, nhưng hết lỗi 10006 mới là tín hiệu tốt.

## 5. Bất thường cần theo dõi

1. HIGH: `paper_d17bfg2` im actions 05:16:04→~05:41 (health CRITICAL), heartbeat state.json mới lại — xem log tiếp có lặp lại không.
2. LOW: git HEAD `ebd71fa` ≠ code restart nêu `990e26d` (commit này vẫn tồn tại trong history) — read-only không xác minh code đang chạy; log PostOnly cho thấy testnetfix đang active.
3. INFO: `paper` WARNING chỉ vì rate-limit cũ; hết khi qua 24h.
