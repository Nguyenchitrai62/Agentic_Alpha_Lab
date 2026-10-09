# REPORT.md — data_hlfunding (Hyperliquid funding history + descriptive look)

Data-only task: no trading rule, no engine run, no return statistic anywhere.
Scripts: `fetch_hl_funding.py` (fetch), `analyze_hl_vs_binance.py` (descriptives).
No price data was loaded at any step (funding-to-funding only).

## 1. Coverage (fetched 2026-10-07, `POST api.hyperliquid.xyz/info`)

| coin | HL first | HL last | HL rows | 8h windows | 1-row windows | overlap w/ Binance |
|---|---|---|---|---|---|---|
| BTC | 2023-05-12 00:00 UTC | 2026-10-07 06:00 UTC | 29,293 | 3,733 | 81 | 2023-05-12 .. 2026-08-31 (3,624) |
| ETH | 2023-05-12 00:00 UTC | 2026-10-07 06:00 UTC | 29,293 | 3,733 | 81 | same (3,624) |
| SOL | 2023-05-12 00:00 UTC | 2026-10-07 06:00 UTC | 29,293 | 3,733 | 81 | same (3,624) |
| BNB | 2023-05-12 00:00 UTC | 2026-10-07 06:00 UTC | 29,293 | 3,733 | 81 | same (3,624) |
| XRP | 2023-06-18 00:00 UTC | 2026-10-07 06:00 UTC | 28,972 | 3,622 | 0 | 2023-06-18 .. 2026-08-31 (3,513) |

Files: `data/raw/hyperliquid_20261007/HL_<COIN>_funding_1h.parquet`
(time UTC, fundingRate, premium; 0 nulls, 0 duplicate times) + `manifest.json`
(rows/first/last/sha256, fetch window, endpoint) + one `metaAndAssetCtxs_*Z.json`
snapshot. No coin missing; BNB was NOT late (listed from day one, same as
BTC/ETH/SOL); XRP listed ~5 weeks later (2023-06-18).
Cadence: 8h (1 row/window, 2023-05-12..~2023-06-08) then hourly (8 rows/window);
only 3 hourly rows missing in the whole span (one hour each in the windows
2023-07-02 16:00, 2023-08-23 16:00, 2024-08-15 08:00 UTC). Binance settled
funding (`data/raw/binance_premium_20260928`) ends 2026-08-31, which caps the
overlap. Binance BNB funding is exactly 0.0 in ~half of all windows (venue
truth, 3,577/7,184) — the BNB sign test below runs on the nonzero subset.

## 2. Descriptive: HL 8h-sum vs Binance 8h funding (per coin-year, `hl_vs_binance_8h.csv`)

corr = Pearson(HL-sum, Binance); spread = HL-Binance per 8h in bps;
opp = share of windows with opposite signs (both legs nonzero).

| coin | year | n | corr | spread mean | spread p90 | opp share |
|---|---|---|---|---|---|---|
| BTC | 2023 | 702 | 0.48 | +0.49 | +3.25 | 32% |
| BTC | 2024 | 1,098 | 0.70 | +1.12 | +3.36 | 11% |
| BTC | 2025 | 1,095 | 0.39 | +0.50 | +1.15 | 15% |
| BTC | 2026 | 729 | 0.41 | +0.18 | +0.93 | 29% |
| ETH | 2023 | 702 | 0.57 | +1.07 | +4.31 | 16% |
| ETH | 2024 | 1,098 | 0.64 | +0.83 | +2.98 | 9% |
| ETH | 2025 | 1,095 | 0.39 | +0.33 | +1.15 | 21% |
| ETH | 2026 | 729 | 0.43 | +0.33 | +1.06 | 29% |
| SOL | 2023 | 702 | 0.64 | +0.56 | +5.26 | 25% |
| SOL | 2024 | 1,098 | 0.78 | +1.33 | +4.10 | 14% |
| SOL | 2025 | 1,095 | 0.54 | +0.45 | +1.72 | 36% |
| SOL | 2026 | 729 | 0.64 | +0.07 | +1.15 | 31% |
| BNB | 2023 | 702 | 0.61 | -0.23 | +2.64 | 5% (of 360 nonzero) |
| BNB | 2024 | 1,098 | 0.69 | +1.05 | +3.93 | 17% (of 516) |
| BNB | 2025 | 1,095 | 0.54 | +0.44 | +1.21 | 12% (of 384) |
| BNB | 2026 | 729 | 0.46 | +0.29 | +1.00 | 7% (of 325) |
| XRP | 2023 | 591 | 0.71 | -0.70 | +2.61 | 39% |
| XRP | 2024 | 1,098 | 0.72 | +0.43 | +2.07 | 11% |
| XRP | 2025 | 1,095 | 0.46 | +0.47 | +1.72 | 25% |
| XRP | 2026 | 729 | 0.61 | +0.11 | +1.00 | 30% |

All-overlap corr: BTC 0.65, ETH 0.61, SOL 0.67, BNB 0.61, XRP 0.65.
Reading: venues agree on direction most of the time (corr 0.4-0.8, strongest
2024); the spread averages near zero (+/-1.3 bps) with a fat right tail
(p90 +1..+5 bps — HL dearer than Binance in crowded longs); opposite-sign
windows are common (10-40%), most frequent in 2025-2026. Spreads are small vs
the ~4-8 bps round-trip, so the level is not a cost edge — the B1 hypothesis
(disagreement as a crowding flag, not a level) is the only form consistent
with these magnitudes.

## 3. Walk-forward usability

History covers anchors 2023-09-24 and 2024-09-24 ONLY (nothing for 2021/2022).
Pre-anchor history (minus 7d embargo): 2023 anchor ~128 days (BTC/ETH/SOL/BNB;
first ~4 weeks at 8h cadence), ~91 days XRP — thin, screen-only; 2024 anchor
~16 months (~15 XRP) — enough for a trailing-1y spread-z screen. A B1 screen
can be judged on overlap + paper only, never as a dev4 selection input.

## 4. Leakage / protocol notes

No G2 reproduction (no overlay built — data task, nothing to compare).
No price/return input; each year-row uses only that year's funding windows;
no thresholds/quantiles/models fitted; nothing from any test year feeds any
choice. Feature-timing discipline for a future screen: HL rows timestamped per
hour, joinable as-of any 4h close; quantiles must be fit pre-anchor + 7d
embargo (HL covers 2023-2024 overlap only).

## 5. Vietnamese verdict

- Dữ liệu đủ dài cho anchor 2023-2024 (không cho 2021-2022); nên chạy screen B1.
- Spread trung bình ~0, đuôi phải dày — chỉ hợp giả thuyết disagreement, không phải level.
- Đề xuất: pre-register screen v290-style trên overlap + paper, không chọn dev4.
