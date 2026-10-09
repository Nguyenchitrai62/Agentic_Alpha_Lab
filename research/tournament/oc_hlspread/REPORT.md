# REPORT.md — oc_hlspread (SHORT-SPAN; no dev4 selection; no deployment)

## 1. What was done (PLAN-fixed)

Signal: `D(T)` = HL 8h-summed funding minus Binance 8h funding, averaged over
the last 7 days (21 settlements) with `w+8h <= T` (fully settled before the 4h
close); `z(T) = (D - trailing-1y mean)/std` over strictly prior `D` in
`[T-365d, T)`, min 720 finite values (120 days), else NaN -> no signal.
Rule H1: `z > +1.5` -> book LONG x0.5; `z < -1.5` -> book SHORT x0.5.
CTRL: per-year exposure-matched constants `cL_y`/`cS_y` (H1 realised mean mult
on long/short cells that year), no timing. G2 = `R2B1D17BFG2` from the v421
cache, reproduced 5.41 / 16.91 / 16.82 to the digit first (else stop).

## 2. Data / overlap

HL `data/raw/hyperliquid_20261007` (BTC/ETH/SOL/BNB from 2023-05-12, XRP from
2023-06-18) vs Binance settled `data/raw/binance_premium_20260928` (ends
**2026-08-31 16:00 UTC**, window end 2026-09-01 00:00 UTC — exact overlap end).
First `D`: 2023-05-19 (XRP 2023-06-25); first `z`: 2023-09-16 (XRP 2023-10-23).
Only anchors 2023-09-24 and 2024-09-24 usable (+2025 partial). SHORT-SPAN.

## 3. Descriptive (decisions 2023-05-01 .. <2025-09-23; vol-normalised 4h-open forwards)

| coin | n_z | share |z|>1.5 | z>+1.5 | z<-1.5 | IC24h | IC7d |
|---|---|---|---|---|---|---|---|
| BTC | 4434 | 6.13% | 5.32% | 0.81% | -0.031 | -0.072 |
| ETH | 4434 | 5.71% | 4.53% | 1.17% | -0.017 | +0.011 |
| SOL | 4434 | 8.46% | 6.43% | 2.03% | +0.032 | +0.050 |
| BNB | 4434 | 8.32% | 5.71% | 2.62% | -0.038 | -0.023 |
| XRP | 4212 | 13.98% | 11.42% | 2.56% | -0.008 | -0.058 |

Reading: events exist (6-14% of bars) but Spearman ICs are ~0 (max |IC7d|
0.072 BTC, 0.058 XRP, 0.050 SOL). No directional edge; magnitudes vs 4-8 bps
round-trip: spreads average ~0 (data_hlfunding), so only the disagreement
form was ever plausible — and it does not predict returns here.

## 4. Engine (4-phase; per-anchor-year reset metric %/month; DD %)

| year | G2 R/DD | H1 R/DD | CTRL R/DD |
|---|---|---|---|
| 2023-09-24 | 6.045 / 15.81 | 6.447 / 16.01 | 6.045 / 15.81 |
| 2024-09-24 | 10.677 / 8.27 | 10.959 / 8.70 | 10.677 / 8.27 |
| 2025-09-24 (most-recent-year, scored once) | 4.648 / 12.90 | 4.575 / 12.90 | 4.648 / 12.90 |
| 5y geo / max-DD / full-path DD: G2 5.410 / 16.91 / 16.82; H1 5.528 / 16.91 / 16.82; CTRL 5.410 / 16.91 / 16.82 |

Gate accounting (standard index): 2021/2022 zero gates (no z); 2023: 463 long
+ 6 short of 6511/4220 (cL 0.9644, cS 0.9993); 2024: 352 + 243
(cL 0.9731, cS 0.9698); 2025: 164 + 267 (cL 0.9804, cS 0.9793). CTRL rounds to
G2 to the digit (exposure cut ~2-3.5% is too small to move the metric); H1's
+0.40/+0.28 in 2023/2024 comes with +0.20/+0.43 DD, and reverses (-0.07) in the
most-recent year. Full-path DD unchanged (16.82).

## 5. What failed and why

The crowding-contrarian tilt does not transfer: descriptive IC ~0, engine gain
is two-year-only on a thin span with a DD cost, and the frozen rule loses in
the year scored once. CTRL equivalence shows the return wiggle is timing, not
exposure — but timing this weak on 2 usable years cannot be selected.

## 6. Leakage checks (how verified)

- Funding windows enter `D(T)` only when `w+8h<=T` (test: truncating windows
  after a cutoff leaves pre-cutoff `D` unchanged).
- `z(T)` uses strictly prior `D(T'<T)` (test: hiding future `D` leaves sampled
  `z` unchanged); thresholds fixed in PLAN.md, no fit on any test year.
- Descriptive decisions `<2025-09-24`; forwards/vol use `open[T+k]` as labels
  and trailing-30d vol only; engine gate joined as-of exact `(T,sym)`, applied
  after the bear filter and before ffill; CTRL constants per-year realised
  (2025 from 2025 H1 only); fills/costs/funding = gate model (engine_real:
  maker 0.0002, taker 0.00055, longs 0.0001/8h, shorts 0, 1m trade-through,
  5-min ban, stop-first).

## 7. Vietnamese verdict

- Không triển khai từ span ngắn này; hiệu ứng nhỏ (+0.40/+0.28 năm 2023/2024, âm ở năm gần nhất) và DD không cải thiện.
- Mô tả IC gần 0 (lớn nhất |IC7d| ~0.07); timing hơn CTRL hằng số không rõ ràng.
- Nếu theo đuổi: chỉ log prospectively z theo định nghĩa đóng băng này, không chọn dev4.
