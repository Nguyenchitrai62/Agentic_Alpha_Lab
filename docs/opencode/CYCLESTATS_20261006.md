# Cycle stats 2026-10-06 (sampler 20 phút + summary từ 06:40 UTC)
Read-only: chỉ đọc state.json/actions.jsonl + RAM CIM; không chạm process/state, không commit.
Sampler: `--sample 60 --every 20` (~06:32–06:52 UTC) trên 5 runner paper* (bỏ _retired, paper_carry).
Summary: `cycle_stats.py --summary --since 2026-10-06T06:40:00Z`.
## 1. Sampler (median / p95 / max cycle ms, stage trội, gap mtime)
| runner | med/p95/max (ms) | stage trội | gap max | gap>2min |
| paper | 464/925/1002 | kline_ms | 19s | 0 |
| paper_d17bf | 483/708/944 | kline_ms | 23s | 0 |
| paper_d17bfg2 | 430/826/966 | kline_ms | 22s | 0 |
| paper_g2k20 | 446/889/913 | kline_ms | 23s | 0 |
| paper_d13bf | 441/683/771 | kline_ms | 23s | 0 |
Max cycle ~1s, xa ngưỡng slow_cycle 60s; stage trội luôn kline_ms (cache/shared fetch).
Không gap nào > 2 phút: stall 25 phút của paper_d17bfg2 (05:16→05:41) không tái diễn.
## 2. Summary actions.jsonl từ 06:40 UTC
| runner | slow_cycle | lock_wait | rate_limit | error | n |
| paper | 0 | 0 | 0 | 0 | 0 (action cuối 06:16, chỉ heartbeat state.json) |
| paper_d17bf | 0 | 0 | 0 | 0 | 8 |
| paper_d17bfg2 | 0 | 0 | 0 | 0 | 8 |
| paper_g2k20 | 0 | 0 | 0 | 0 | 4 |
| paper_d13bf | 0 | 0 | 0 | 0 | 0 (action cuối 06:17, chỉ heartbeat) |
## 3. RAM host (PowerShell CIM FreePhysicalMemory, mẫu mỗi tick)
Tương quan RAM trống vs cycle trung bình/tick: r=-0.29 → không tương quan (|r|<0.5).
Kết luận: 5 runner đều heartbeat đều (~20s), không slow/lock_wait/rate-limit mới.
