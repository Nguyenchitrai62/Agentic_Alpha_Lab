# oc_vrpstraddle REPORT — delta-hedged short ATM straddles (BTC+ETH weekly)

Frozen rule (PLAN.md, pre-registered 2026-10-07, no fitting of any kind): every
Friday 08:05 UTC sell one ATM straddle per coin (K = S rounded NEAREST to grid
BTC 1000 / ETH 50, S = 1m close 08:04), premium = BS call+put (r=q=0) at
0.97 x latest-known-DVOL/100. V1 = 1-week expiry + 4h-close delta hedge
(-q x BS delta at DVOL, +2 bps adverse + maker 0.0002, long hedge pays 0.0001/8h
settlement); V2 = 1-week no hedge (control); V3 = 4-week expiry + hedge, every
4th Friday non-overlapping. SL = full close when (straddle mark at 1.05x DVOL +
hedge P&L) <= -1.0 x premium (hourly; hedge closed taker); TP = buy back at
0.3 x premium (4h closes, maker); else settle vs mean 1m 07:30..07:59.
q = 0.5 x E / S per coin. Standalone sleeve resets to 1.0 each anchor year;
boundary weeks skipped (disclosed). Repro: `run_vrp.py dev4 | final V2` (via
heavy_slot) + `tests/test_oc_vrpstraddle.py`. G2 baseline reproduced to the
digit before any overlay (asserted in-script); f=0 overlay reproduces
v421_result G2 to the digit.

## Post-hoc change log (originals kept, nothing re-tuned)

1. IV-RV gap reported in vol points instead of decimals (reporting scale only;
   selection R/DD bit-identical across reruns).
2. Sensitivity `sigma_otmiv` divided points by 100 one line too late (first
   final run: all-SL garbage row, discarded, never reported); fixed, rerun.
3. Overlay marked path used M_prev x hh (compounds Pi(ms/es) decay over dips,
   gave absurd ~104% yearly DDs); fixed to the v421/carrycompound convention
   M = A_prev x hh + dU; rerun. Standalone legs, dU/g2 legs, correlations and
   all selection numbers unaffected (fix touches only overlay M).

## Standalone sleeve, dev4 (R %/mo geometric / DD % hourly-marked)

| year | V1 hedged 1w | V2 naked 1w | V3 hedged 4w |
|---|---|---|---|
| 2021-09-24 | 7.307 / 36.97 | 8.004 / 25.82 | -4.684 / 65.58 |
| 2022-09-24 | 2.541 / 29.82 | 4.197 / 18.24 | 0.509 / 31.17 |
| 2023-09-24 | -1.431 / 45.50 | -0.165 / 25.05 | -2.451 / 41.86 |
| 2024-09-24 | 0.627 / 33.01 | 1.903 / 23.40 | -2.733 / 42.89 |
| dev4 mean / worst / maxDD / losing | 2.210 / -1.431 / 45.50 / 1 | 3.441 / -0.165 / 25.82 / 1 | -2.357 / -4.684 / 65.58 / 3 |

V2 detail (trades / win / TP / SL / expiry / worst-week / IV-RV gap / opt-leg / hedge-leg):
2021: 104 / 0.71 / 24 / 13 / 67 / 2022-03-02 -16.85% / +0.097 (IV 86.9, RV 0.77) / +1.52 / 0.00.
2022: 102 / 0.72 / 34 / 17 / 51 / 2023-01-18 -13.84% / +0.095 (56.7, 0.47) / +0.64 / 0.00.
2023: 102 / 0.60 / 20 / 23 / 59 / 2024-07-10 -12.99% / +0.009 (57.5, 0.57) / -0.02 / 0.00.
2024: 102 / 0.66 / 36 / 17 / 49 / 2025-03-03 -16.05% / +0.012 (59.3, 0.58) / +0.25 / 0.00.
V1 P&L split (opt-leg / hedge-leg): +1.27/+0.06, +0.66/-0.31, +0.11/-0.27, +0.21/-0.14:
the premium is real in 4/4 years, the 4h delta hedge bleeds in 3/4 (trend-chasing
in trending years) AND raises DD (45.5 vs 25.8). Hedging buys nothing here.
V3 (28d holding) is destroyed by the same crash weeks with 4x the exposure time.

Selection: NO variant has DD <= 20 with no losing dev year (eligible set empty),
so the robust criterion falls back to the highest dev4 worst-year: V2 (-0.165 >
-1.431 > -4.684). `final V2` asserts this recomputation before scoring.

## Most recent year 2025-09-24..2026-09-23, scored ONCE (V2 + G2 ref only)

V2: 4.232 %/mo, DD 19.57, 102 trades, win 0.686, TP 33 / SL 15 / expiry 54,
worst week 2026-02-05 -11.56%, gap +0.006 (IV 53.4, RV 0.528), opt-leg +0.64.
(G2 ref: 4.648 / 12.90.) Notes: (a) fails the gate (standalone DD 25.82 dev,
one dev losing year) despite a decent last year; (b) the 2026-09-18 cycle is
absent (expiry past grid end, uncounted — boundary, not a skip); (c) the
pre-registered otmiv sensitivity was deliberately NOT scored on this year:
that would be variant comparison on the locked year.

## Sensitivities, chosen variant V2, dev4 only (labelled)

| row | mean / worst / maxDD / losing |
|---|---|
| V2 base (DVOL sigma) | 3.441 / -0.165 / 25.82 / 1 |
| sigma_otmiv (0.5x(put+call) IV avg, DVOL fallback) | 6.522 / 1.508 / 25.71 / 0 |
| option fees x2 | 3.047 / -0.634 / 26.18 / 1 |
| hedge slip 5 bps | identical (V2 has no hedge — control behaves as control) |

The otmiv row is the only dev4-positive surprise (no losing year, worst +1.5%)
but keeps the fatal DD (25.71 > 20). It is a LEAD for its own pre-registered
direction, not an adoption: scoring it on the recent year now is forbidden.

## Overlay on G2, V2 sleeve (UTA, labelled; f of TOTAL equity; reset metric)

| year | G2 | G2+0.25 | G2+0.5 |
|---|---|---|---|
| 2021 | 2.588 / 10.86 | 4.655 / 11.18 | 6.681 / 12.70 |
| 2022 | 3.282 / 16.91 | 4.365 / 16.10 | 5.415 / 15.57 |
| 2023 | 6.045 / 15.81 | 6.073 / 15.59 | 6.058 / 17.59 |
| 2024 | 10.677 / 8.27 | 11.314 / 8.53 | 11.899 / 11.16 |
| 2025 (labelled, once) | 4.648 / 12.90 | 5.780 / 13.70 | 6.887 / 14.59 |
| 5y R / worst / maxDD / losing | 5.410 / 2.588 / 16.91 / 0 | 6.408 / 4.365 / 16.10 / 0 | 7.364 / 5.415 / 17.59 / 0 |
| full-path DD (marked/close/max) | 16.82 | 16.01 / 15.20 / 16.01 | 17.87 / 17.59 / 17.87 |

Daily-P&L corr (sleeve vs G2 legs, yearly-reset paths concatenated): -0.128
overall, -0.036 in G2's worst 20 days — roughly uncorrelated, NOT a crash hedge.
Worst 5 combo weeks (f=0.25, distinct dates): 2024-01-03 -11.84% (ETF
sell-the-news), 2024-01-04 -11.60%, 2024-07-16 -11.34%, 2025-10-17 -11.24%,
2024-01-05 -11.11% — the sleeve's own crash weeks, not G2's.

## Caveat paragraph (mandatory)

DVOL is a 30-day ATM index; a 7-day (V1/V2) or 28-day (V3) straddle owns its own
term-structure IV (usually lower in calm, higher in stress), so selling at
0.97 x DVOL systematically over/under-prices the short end — direction unknown
without the term structure. There are no strike-level quotes anywhere here (a
strike-level check needs data/raw/deribit_strike_20261007, being fetched by
another worker); fills are BS mids with Deribit-style fee caps, i.e. no real
bid/ask spread (wider in stress). Settlement uses the Binance perp 1m mean, not
Deribit's settlement index (basis risk unmodeled), and DVOL itself references
Deribit's index, not Binance perps. Marks are hourly closes: DD is a lower
bound (no intrabar). The hedge-on-close uses a research simplification (fill at
the close + 2 bps adverse, not a minute-5 resting limit).

## Leakage statement

Feature timing: DVOL candle known at its close (last close <= decision);
S at 08:04 known at 08:05; marks use latest closed hourly DVOL / closed 4h IV;
settlement uses 07:30..07:59 closes known at 08:00 (test: truncation +
hand-checked synthetic weeks). Label windows: payoff uses only post-entry
minutes. Fit windows: none (no thresholds, no quantiles, no calibration).
Fill timing: options at model marks (no book); hedge at known 4h closes +
adverse slippage; no position fills in the first 5 min after entry by
construction (first event 09:00). inexact 1m lookups: 0.

## Verdict

Negative result, honestly earned: the volatility risk premium IS visible
(positive option legs, 60-72% win rates, positive mean IV-RV gap every year)
but weekly short straddles at 1.0x sleeve notional cannot survive the crash
weeks — every variant fails DD <= 20, all have a losing dev year, and the
4h delta hedge makes both return and DD worse. The otmiv-sigma lead (dev4
6.52%/mo, no losing year, same DD disease) deserves its own pre-registered
direction, not adoption. No variant goes near real money.

Tiếng Việt:
Dòng này bị loại vì đòn DD vượt 20% và vẫn có năm lỗ trên dev4.
Hướng otmiv cần đăng ký mới và kiểm chứng prospective riêng.
Không dùng năm gần nhất để so sánh thêm bất kỳ biến thể nào nữa.
