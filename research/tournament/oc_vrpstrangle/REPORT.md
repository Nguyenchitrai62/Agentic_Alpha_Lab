# oc_vrpstrangle REPORT — weekly short OTM strangle priced from traded OTM IV (BTC+ETH)

Frozen rule (PLAN.md, pre-registered 2026-10-07, no fitting of any kind):
every Friday 08:05 UTC sell one OTM strangle per coin (S = 1m close 08:04;
sigmas = traded OTM put/call IV / 100 of the 04:00 4h bar, per-leg DVOL
fallback; K_p = S exp(-z sig_p sqrt(T)) DOWN to grid, K_c = S exp(+z sig_c
sqrt(T)) UP, grids BTC 1000 / ETH 50; premium = BS put + call at 0.97x).
SL = buy back both legs when (mark at 1.05x sigmas) loss <= -1.0x premium
(hourly); TP = buy back at 0.3x premium (4h closes, TP first); else settle vs
mean 1m 07:30..07:59. No hedge. q = 0.5 E / S per coin. Repro:
`run_strangle.py dev4 | final Z2` (via heavy_slot) +
`tests/test_oc_vrpstrangle.py`. G2 baseline reproduced to the digit before any
overlay (asserted in-script); f=0 overlay reproduces v421_result G2 to the
digit (5.41 / 16.91 / 16.82). No post-hoc changes: the code that ran dev4 is
the code that ran final.

## Standalone sleeve, dev4 (R %/mo geometric / DD % hourly-marked)

| year | Z1 z=0.5 | Z2 z=1.0 |
|---|---|---|
| 2021-09-24 | 4.622 / 16.27 | 0.553 / 9.52 |
| 2022-09-24 | 2.856 / 6.99 | 0.609 / 4.14 |
| 2023-09-24 | 0.752 / 22.21 | 0.291 / 14.01 |
| 2024-09-24 | 5.322 / 9.81 | 1.076 / 8.19 |
| dev4 mean / worst / maxDD / losing | 3.373 / 0.752 / 22.21 / 0 | 0.632 / 0.291 / 14.01 / 0 |

Z1 detail (trades / win / TP / SL / expiry / worst-week / prem% / gap):
2021: 104 / 0.76 / 76 / 23 / 5 / -7.22% / 3.78 / +0.099.
2022: 102 / 0.79 / 81 / 21 / 0 / -5.78% / 2.09 / +0.113.
2023: 102 / 0.66 / 63 / 34 / 5 / -9.90% / 2.83 / +0.089.
2024: 102 / 0.75 / 73 / 24 / 5 / -5.75% / 3.63 / +0.213.
Z2 detail: 104-102 trades/yr, win 0.68-0.76, TP 70-78 / SL 24-33 / expiry
~0, worst weeks -3.0..-9.6%, prem 0.79-1.48% of S, gap +0.068..+0.213 every
year (entry sigma avg 58-87 points; DVOL fallback share 0.0 — IV coverage was
complete, fallback never triggered; inexact 1m lookups 0; boundary skips 2/yr).
Z1 earns 5x Z2's mean but one 2023 crash week (-9.9%) breaks the DD gate
(22.21 > 20). Z2 survives everywhere (no losing year, DD <= 20) but earns
almost nothing: the 1-sigma wings collect ~1% weekly premium at 68-76% win
rates and give it all back in SL weeks (24-33 SL/year).

Selection: eligible set (DD <= 20, no losing dev year) = {Z2} only; no
variant has dev4 mean >= 5, so the robust criterion falls back to the highest
dev4 worst-year inside the eligible set: Z2. `final Z2` asserts this
recomputation before scoring.

## Most recent year 2025-09-24..2026-09-23, scored ONCE (Z2 + G2 ref only)

Z2: 1.017 %/mo, DD 3.43, 102 trades, win 0.765, TP 78 / SL 24 / expiry 0,
worst week 2026-02-06 -2.92%, prem 1.03%, gap +0.068 (sig 59.6), fb 0.0.
(G2 ref: 4.648 / 12.90.) Clean year, same story: survives, earns ~1%/mo.

## Overlay on G2, Z2 sleeve (UTA, labelled; f of TOTAL equity; reset metric)

| year | G2 | G2+0.25 | G2+0.5 |
|---|---|---|---|
| 2021 | 2.588 / 10.86 | 2.734 / 10.59 | 2.877 / 10.79 |
| 2022 | 3.282 / 16.91 | 3.441 / 16.50 | 3.598 / 16.09 |
| 2023 | 6.045 / 15.81 | 6.135 / 15.81 | 6.217 / 16.14 |
| 2024 | 10.677 / 8.27 | 10.980 / 8.24 | 11.280 / 8.23 |
| 2025 (labelled, once) | 4.648 / 12.90 | 4.913 / 13.18 | 5.177 / 13.45 |
| 5y R / worst / maxDD / losing | 5.410 / 2.588 / 16.91 / 0 | 5.601 / 2.734 / 16.50 / 0 | 5.789 / 2.877 / 16.14 / 0 |
| full-path DD (marked/close/max) | 16.82 | 16.41 / 15.63 / 16.41 | 16.00 / 15.21 / 16.00 |

Daily-P&L corr (sleeve vs G2 legs, yearly-reset f=0.25 paths concatenated):
-0.031 overall, +0.074 in G2's worst 20 days — uncorrelated, NOT a hedge.
Worst 5 combo weeks (f=0.25, distinct dates): 2024-01-03 -12.36%,
2024-01-04 -12.09%, 2024-01-09 -11.58%, 2024-01-05 -11.50%,
2024-01-10 -10.87% — G2's own ETF sell-the-news weeks, not the sleeve's.

## Caveat paragraph (mandatory)

Aggregated OTM IV mixes strikes and tenors <= 60 d, not the 7-day OTM quote
at K_p/K_c: smile/term-structure risk unmodeled (this time the bias direction
is visible — the IV-RV gap is positive every year yet the P&L is ~zero, so
the 0.97x sale plus SL-gap costs eat the apparent edge). No bid/ask (BS mids
with Deribit-style fee caps). Settlement uses the Binance perp 1m mean, not
Deribit's index. Marks are hourly closes: DD is a lower bound (no intrabar).
No hedge by design: crash weeks are borne in full.

## Leakage statement

Feature timing: 4h IV bar known at start+4h (last close <= decision; the 04:00
bar is the entry input; truncation test in the pytest file); hourly DVOL
known at close; S at 08:04 known at 08:05; marks use latest closed 4h IV /
closed hourly DVOL; settlement uses 07:30..07:59 closes known at 08:00.
Label windows: payoff uses only post-entry minutes. Fit windows: none (no
thresholds, no calibration; z = {0.5, 1.0} pre-registered). Fill timing:
options at model marks, no book; no position events before 09:00 Friday;
TP-before-SL at 4h closes. inexact 1m lookups: 0.

## Verdict

Independent VRP evidence, negative result: the traded-OTM-IV strangle confirms
the premium exists (positive IV-RV gap 5/5 years, 68-79% win rates) but it is
not harvestable at these wings — Z1 pays for its 3.37%/mo with a 22.21 DD,
Z2 passes DD (14.01) with a 0.63%/mo that adds only +0.19 pp/mo to G2 at
f=0.25 (+0.38 at f=0.5) while leaving full-path DD essentially unchanged. No
variant goes near real money; the direction is closed.

Tiếng Việt:
Dòng strangle OTM bị loại vì Z1 vượt DD 20% còn Z2 chỉ ~0,6%/tháng, không bù đắp rủi ro.
Lớp phủ lên G2 chỉ cộng thêm 0,19 điểm %/tháng ở f=0,25, tương quan gần bằng không.
Không dùng năm gần nhất để so sánh thêm bất kỳ biến thể nào nữa.
