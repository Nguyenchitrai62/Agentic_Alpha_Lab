# oc_putwrite REPORT (2026-10-07) — weekly cash-secured put-write sleeve, BTC+ETH

## Verdict first: REJECT. No variant is profitable; the sleeve subtracts from G2.

## 1. Standalone dev4 (fresh 1.0 per anchor year, f = 1, R = geom %/mo, DD = hourly-marked)

| variant | 2021 | 2022 | 2023 | 2024 | mean | worst | maxDD | losing |
|---|---|---|---|---|---|---|---|---|
| P1 z=1.0 | -0.459 / 10.02 | 0.440 / 2.21 | 0.585 / 2.61 | 1.097 / 6.75 | 0.414 | -0.459 | 10.02 | 1 |
| P2 z=1.5 | -0.548 / 7.17 | -0.049 / 2.00 | -0.012 / 1.68 | -0.087 / 6.94 | -0.174 | -0.548 | 7.17 | 4 |
| P3 z=2.0 | -0.267 / 3.29 | -0.069 / 1.02 | -0.072 / 0.88 | -0.216 / 4.05 | -0.156 | -0.267 | 4.05 | 4 |
| P4 spread | -3.604 / 37.96 | -1.361 / 20.29 | -0.789 / 14.38 | -2.440 / 39.81 | -2.054 | -3.604 | 39.81 | 4 |

Win rates 62-82% (TP 64-84/yr, SL 18-40/yr, expiry ~0/yr) yet net ≤ +0.4 %/mo:
short 7d puts collect ~0.03-0.85 %/wk premium but TP (+0.8×prem) vs SL (−2×prem)
asymmetry + ~22 % round-trip fee drag (BTC z=1.5 scale) + the 0.95 sell / 1.05
mark vol haircut bleed every week. P4 is catastrophic: the z=3.0 long leg costs
~1.0-1.6 %/wk premium and almost never pays; tiny width ⇒ huge leverage.
Qualifying set (DD ≤ 20, no losing dev year) is EMPTY. Fallback disclosed:
literal worst-year rule on the DD ≤ 20 pool ⇒ P3 (worst −0.267). (P1 noted as
the mean alternative: +0.414, 3/4 winning years; leader may overrule.)

## 2. Chosen P3, most recent year ONCE (2025-09-24..2026-09-23)

R −0.115 %/mo, DD 1.57, 102 trades, win 70.6 %, TP 72 / SL 30 / expiry 0,
worst week 2026-06-05 −0.242 %, mean premium yield 0.042 %/wk. Still losing.

## 3. Sensitivity rows, P3 dev4 (labelled extra)

sigma_sell 0.90 (deeper haircut): mean −0.210, worst −0.404, DD 4.82 — worse
(lower premium, same SL multiple). Fees ×2: mean −0.159, worst −0.274,
DD 4.11 — immaterial (fees already capped by the 0.125×price term most weeks).

## 4. Overlay on G2 (labelled, UTA assumption — needs Bybit UTA portfolio margin)

| row | R | W | maxDD | full-path DD | losing |
|---|---|---|---|---|---|
| G2 alone (reproduced to the digit) | 5.410 | 2.588 | 16.91 | 16.82 | 0 |
| G2 + put f=0.25 | 5.371 (−0.039) | 2.520 | 16.96 | 16.87 | 0 |
| G2 + put f=0.50 | 5.332 (−0.078) | 2.451 | 17.01 | 16.92 | 0 |

Daily-P&L sleeve-vs-G2 correlation per year: −0.08..+0.08 (≈0; no hedge, just
drag). Worst 5 combo weeks (f=0.25, Fri→Fri): 2023-12-29 −9.65, 2024-06-07
−8.71, 2023-08-11 −8.06, 2024-07-12 −7.81, 2025-10-10 −7.25 — G2's own crash
weeks; the sleeve moves them by basis points either way.

## 5. MANUAL view (labelled, M5_human hourly equity found in oc_manualcap)

MANUAL alone R5 3.728 (matches stored 3.728/W 0.847); + put f=0.25 → 3.689
(−0.039); f=0.50 → 3.651. No MANUAL product either (base far below floor).

## 6. Leakage statement

No fits/thresholds (z fixed pre-registration). Feature timing: entry σ from
the 4h bar closed 08:00 + S from minute 08:04, both known at 08:05 entry;
marks use the latest CLOSED 4h IV bar / closed hourly DVOL candle only;
settlement uses 07:30..07:59 closes known at 08:00 expiry; exit checks only at
closed 4h/1h bars (nothing before Fri 12:00). Label windows: expiry payoff uses
only post-entry minutes. Fill timing: N/A (option premium/marks, no book).
Verified by tests/test_oc_putwrite.py (exact-close boundary tests) + zero
`inexact_px` lookups in the runs.

## 7. Caveat (assignment §4)

Aggregated 4h OTM IV is not a strike-level quote (skew, spread, liquidity):
at z=1.5-2.0 the smile/skew and the option bid-ask (we modelled only a 5 %
vol haircut + capped fee) almost surely make realised fills WORSE than this
screen; results are a screen, a strike-level check needs
data/raw/deribit_strike_20261007. Other simplifications favour the sleeve:
entries applied at the 09:00 hourly step (55 min late, negligible over 7d);
P4 long leg settles to intrinsic with no fee; combo close path reuses sleeve
marks (disclosed in PLAN/runner).

## 8. Reproduce

`run_putwrite.py` (dev4 + G2 baseline validation) then `run_overlay.py`
(recent year once + overlays + sensitivities); `pytest tests/test_oc_putwrite.py`.

---
Kết luận: từ chối. Không biến thể nào có lãi sau phí ở dev4 (tốt nhất P1
+0.41 %/tháng, vẫn lỗ năm 2021) nên không đạt bất kỳ ngưỡng gate nào.
Lớp phủ put-write làm giảm lợi nhuận G2 (~−0.04 điểm %/tháng ở f=0.25) mà không
giảm DD hay tương quan phòng hộ. Cần bằng chứng khác trước khi xem xét lại.
