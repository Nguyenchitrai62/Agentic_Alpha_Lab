# oc_usdtdepeg REPORT — USDT-USD dislocation snap-back sleeve (idea B9)

Rule, variants, placebo, choice and adoption gate pre-registered in PLAN.md
(fixed before any outcome). Data: Coinbase USDT-USD 1h only
(`data/raw/coinbase_usdt_20261006/`, 47240 bars 2021-05-04..2026-09-23, 3 gaps
totalling 15 h); NO 1m/5m exist, so fills/exits use next-1h-bar low/high with
strict trade-through. G2 baseline reproduced TO THE DIGIT before overlay
(R 5.41 / W 2.588 / DD 16.91 / full 16.82, asserted in run.py).

## Standalone events (gate fees maker 0.0002 / taker 0.00055)

| year | E1 n / win / mean bps / sum | E1 exits TP/SL/cap | E2 n / win / mean / sum |
|---|---|---|---|
| 2021-09-24 | 6 / 66.7% / +15.34 / +0.009203 | 1/5/0 | 4 / 75% / +2.06 / +0.000822 |
| 2022-09-24 | 6 / 83.3% / +7.32 / +0.004393 | 3/2/1 | 2 / 50% / -26.90 / -0.005381 |
| 2023-09-24 | 0 | 0/0/0 | 0 |
| 2024-09-24 | 0 | 0/0/0 | 0 |
| 2025-09-24 (chosen E1 only, scored once) | 0 | 0/0/0 | — (never scored) |

E1 dev4: n=12, win 9/12 (75%), mean +11.33 bps, sum +0.013596, worst -80.8 bps,
best +64.7 bps. E2 dev4: n=6, win 4/6, mean -7.59 bps, sum -0.004558. No
incomplete positions. Retail stress row (0.004/0.006): E1 dev4 sum -0.090804
(mean -75.7 bps) — retail fees erase the edge completely.
Choice on dev4 only: E1 (higher sum). Five-year E1 total = 12 (>= 10 floor:
technically testable, but ALL 12 sit in 2021-2022 — Terra May-2022 and FTX
Nov-2022 stress; three of five years have zero events).

## Placebo (200 draws, seed 7, dev4, same N per year)

E1: actual sum +0.013596 vs placebo mean -0.011305 (p95 -0.007055) -> pct 100.0.
E2: actual -0.004558 vs placebo mean -0.008217 (p95 -0.005611) -> pct 98.0.
Trigger timing beats random hours, but random-hour longs average -8..-11 bps
(being long USDT at a random hour loses the entry fee + drift), so this only
proves "less bad than arbitrary", not an earnable edge at scale.

## Overlay on G2 (chosen E1, 5% sleeve, A(t)=A(t-1)(1+r_bot)+dSleeve)

| year | G2 R/DD | G2+E1 R/DD |
|---|---|---|
| 2021-09-24 | 2.588 / 10.86 | 2.592 / 10.86 |
| 2022-09-24 | 3.282 / 16.91 | 3.284 / 16.91 |
| 2023-09-24 | 6.045 / 15.81 | 6.045 / 15.81 |
| 2024-09-24 | 10.677 / 8.27 | 10.677 / 8.27 |
| 2025-09-24 | 4.648 / 12.90 | 4.648 / 12.90 |
| 5y mean / worst / maxDD / losing | 5.410 / 2.588 / 16.91 / 0 | 5.411 / 2.592 / 16.91 / 0 |

Lift: +0.001 pp/month. Daily-PnL correlation vs G2 (dev4): -0.002 (< 0.3).
How tiny: the sleeve's whole dev4 standalone sum (+136 bps of sleeve notional
over 4 years, at 5% size) is ~7 bps of account equity over four years.

## Verdict: REJECT (not adopted)

E1 meets the pre-registered necessary conditions (testable floor, dev4 sum >
0, placebo pct 100, corr -0.002, no DD/losing-year damage) yet fails economic
significance: +0.001 pp/mo cannot justify a second (Coinbase spot) account,
sleeve notional turnover, and monitoring. The 12 events are a crisis-clustered
microsample (zero events in 2023, 2024 and the most recent year); one extra
stop-out (-77..-95 bps observed) wipes the dev4 sum; retail fees make every
variant deeply negative. E2 (deeper trigger) is worse on return with 6 events.
Close the direction; no prospective paper (nothing to evidence at +0.001).

## Leakage checks

Signal uses only close_t at bar t's close; entry bars t+1..t+4; exits bars >=
fill bar; stop-first within-bar; no fits/thresholds/quantiles anywhere (all
levels assignment-fixed); data < 2026-09-24 only; E2's most-recent year never
touched (E1's scored once, n=0). Tests: tests/test_oc_usdtdepeg.py.

## Post-hoc log

None. No rule, threshold or fee changed after outcomes; retail row and
placebo were pre-registered.

## Verdict (tiếng Việt)

- Kết luận: LOẠI — sleeve snap-back USDT chỉ +0,001 pp/tháng trên G2, 12 lệnh gom hết ở 2021-2022, 3/5 năm không có lệnh nào, phí retail xóa sạch edge.
- Không triển khai, không mở paper (hiệu ứng quá nhỏ để đo prospective).
- Đóng hướng này; nếu USDT depeg trở lại thì đó là dữ liệu prospective mới, không dùng để hồi tố quy tắc này.
