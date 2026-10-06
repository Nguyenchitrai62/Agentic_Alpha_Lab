# oc_margin REPORT — Bybit cross-margin / leverage for R2B1D17BFG2 (2026-10-06; PLAN pre-registered)

RISK / ops report (no selection rule, no PROMISING verdict). Deployment config
R2B1D17BFG2 = registry v421 (R2B1D17BF + dip gross cap G = 2.0) on Bybit USDT
perps, cross margin, Hedge Mode. Positions rebuilt minute-by-minute from the
oc_kpi_g2 s=0..3 replica events with the exact oc_gapstress q-units method
(book flats zeroed, dip FIFO, hourly marks, fractions of current equity;
Hedge-Mode gross = |book_net| + |dip_net| per coin, PnL on net). Samples tile
the 5 years (event minutes + 4h bar ends, minute-weighted; ~17.5-19.3k open
samples/phase, 65.1k mix; coverage 98.9% mix). Check: rebuilt book gross vs
barsum median diff 0.0006-0.0013, max 0.07-0.17 (hourly vs minute-0 timing).
All five years are research data; needs prospective validation. Repro:
research/tournament/oc_margin/{PLAN.md,compute_margin.py,results.json}; test
tests/test_oc_margin.py.

Tier assumption (no Bybit tier table found in the repo — stating it): all five
majors inside tier-1 for an account < 10k USDT (max combined notional here
~3.4-3.8x equity ≈ 35-75k USDT, far below tier-1 value limits); flat MMR =
0.5% on gross. Engine's 1% MM check is the conservative side row. Bybit
IM = notional / leverage; blocked iff IM > 95% equity; liquidation (cross)
when equity <= MM; d_liq = (1-0.005*G)/(G*0.995), all-long-weighted worst case
(≈ 1/G); gap loss = S*g + 0.055%*G*(1-g), liquidated iff loss >= 1-MM*(1-g).

## Gross notional / equity G (minute-weighted)

| scope | median | p99 | max | book max | dip max |
|---|---|---|---|---|---|
| phase s0 | 0.363 | 1.358 | 3.775 | 1.688 | 2.088 |
| phase s1 | 0.367 | 1.461 | 3.552 | 1.324 | 2.229 |
| phase s2 | 0.353 | 1.369 | 3.680 | 1.590 | 2.089 |
| phase s3 | 0.315 | 1.376 | 3.610 | 1.585 | 2.026 |
| 4-phase mix | 0.334 | 1.318 | 3.411 | 1.560 | 1.851 |

MM = 0.5%*G: mix median 0.17%, p99 0.66%, max 1.71% of equity (per-phase max
1.78-1.89%). Maintenance is negligible next to the gap moves below.

## Initial margin / order blocking (IM = G / L, blocked iff > 95% equity)

| scope | 3x max IM / blocked open min | 5x max IM / blocked | 10x | 20x |
|---|---|---|---|---|
| phase s0 | 125.8% / 45 samples (0.022%) | 75.5% / 0 | 37.8% / 0 | 18.9% / 0 |
| phase s1 | 118.4% / 31 (0.018%) | 71.0% / 0 | 35.5% / 0 | 17.8% / 0 |
| phase s2 | 122.7% / 41 (0.015%) | 73.6% / 0 | 36.8% / 0 | 18.4% / 0 |
| phase s3 | 120.3% / 38 (0.013%) | 72.2% / 0 | 36.1% / 0 | 18.1% / 0 |
| 4-phase mix | 113.7% / 22 (0.003%) | 68.2% / 0 | 34.1% / 0 | 17.1% / 0 |

Minimum leverage setting that never blocks an order (IM <= 95% at every open
minute): **5x** — on all four phases and on the mix. 3x would have blocked
22 mix minutes (31-45 per phase, ~0.01-0.02% of open time). 10x/20x also never
block but add no margin safety in cross margin (liquidation is IM-independent)
and only raise the size a fat-finger can take — 5x is the runbook pick.

## At 5x: free-margin buffer and liquidation distance (minute-weighted)

free = 1 - G/5 (share of equity not locked as IM).
d_liq = uniform adverse move liquidating the account, all-long-weighted.

| scope | free median / p1 / min | d_liq median / p1 / min |
|---|---|---|
| phase s0 | 92.7% / 72.8% / 24.5% | 276% / 73.5% / 26.1% |
| phase s1 | 92.7% / 70.8% / 29.0% | 274% / 68.3% / 27.8% |
| phase s2 | 92.9% / 72.6% / 26.4% | 284% / 72.9% / 26.8% |
| phase s3 | 93.7% / 72.5% / 27.8% | 318% / 72.5% / 27.3% |
| 4-phase mix | 93.3% / 73.6% / 31.8% | 300% / 75.7% / 29.0% |

Reading: on a typical minute 93% of equity is free and it takes a ~300%
uniform drop to liquidate (impossible); 99% of minutes need > ~73-76% drop;
the single worst minute (2025-09-25 17:57 mix: G 3.41 = dip 1.85 + book 1.56)
still needs a -29.0% all-coin instant move (per-phase worst 26-28%).

## Instant -10% / -20% all-coin gaps (oc_gapstress formula; would it liquidate?)

| scope | -10%: median / p99 / max loss% | liquidated | -20%: max loss% | liquidated |
|---|---|---|---|---|
| phase s0 | 0.83 / 13.20 / 37.94 | 0 / 19.3k | 75.67 | 0 |
| phase s1 | 1.05 / 13.95 / 35.70 | 0 / 17.8k | 71.20 | 0 |
| phase s2 | 0.96 / 13.49 / 36.98 | 0 / 18.4k | 73.76 | 0 |
| phase s3 | 0.98 / 13.62 / 36.28 | 0 / 17.6k | 72.37 | 0 |
| 4-phase mix | 0.83 / 13.09 / 34.28 | 0 / 65.1k | 68.38 | 0 |

No open minute in 5 years is liquidated by a -10% or a -20% all-coin instant
gap (0 of 65.1k mix samples; liquidation needs ~98.5% equity loss at G ~3.4,
the -20% worst minute loses 68%). The worst -10% mix minute (2025-09-25 17:57,
loss 34.3%, G 3.41, d_liq 29.0%) and the per-phase worsts (37.9/35.7/37.0/
36.3%) all survive with > 60% equity left.

## Khuyến nghị cho runbook (tiếng Việt, ngắn gọn)

- Trên Bybit để tài khoản **Cross margin**, **không dùng Isolated** cho bot.
  Chỉnh đòn bẩy (Leverage) **tối thiểu 5x** (Bybit cho chỉnh theo từng coin —
  chỉnh cả 5 coin BTC/ETH/SOL/BNB/XRP lên >= 5x). 3x sẽ thiếu margin vào những
  phút full ladder (đã thấy 22-45 lần/phases trong 5 năm); 10x/20x không an
  toàn hơn trong cross margin mà chỉ làm lệnh nhầm tay to hơn — **giữ 5x**.
- Với trần dip 2x (G2, `--dip-gross-cap 2.0`): notional tối đa chỉ **~3.4x vốn**
  (không trần ~7.1x). Đặt 5x là dư: IM tối đa 68% vốn, phút thường chỉ ~7%.
- Gap -10% toàn thị trường phút thường mất < 1% vốn; 1% phút xấu mất > 13%;
  phút tệ nhất lịch sử mất ~34% (mix) và **không cháy** (cần -29% mới cháy;
  gap -20% tệ nhất mất 68% cũng chưa cháy). Lệnh vẫn sống — nhưng sau gap phải
  kiểm tra tay trước khi cho bot chạy tiếp.
- Nếu Bybit báo thiếu margin / `skipped_below_minimum` nhiều: dừng bot, kiểm
  tra lại leverage có bị reset về thấp không, rồi hỏi chủ tài khoản — **không
  tự ý hạ đòn bẩy khi đang có vị thế**.

Summary: G2 on Bybit cross needs at least 5x leverage to never block (3x
blocked 22 mix minutes); at 5x the account keeps >= 32% free margin and needs
a -29% all-coin instant move to liquidate at its worst minute, so neither the
-10% nor the -20% gap liquidates any minute in five years.
