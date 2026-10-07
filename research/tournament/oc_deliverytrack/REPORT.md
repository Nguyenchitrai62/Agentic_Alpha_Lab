# oc_deliverytrack REPORT — spot-leg sale tracking error around quarterly delivery

Question: the carry short settles at the delivery INDEX while the bot sells the
spot leg around 08:00 UTC — how far can the realised spot exit miss the index,
and what does it cost each trade? Repro:
`research/tournament/oc_deliverytrack/compute_deliverytrack.py` + `results.json`;
test `tests/test_oc_deliverytrack.py`. 1m data only, one process.

## Delivery definition (cited, not browsed)

`research/tournament/carry_audit/COMPARISON.md` (leader adjudication): "A
delivery future settles at the delivery INDEX (an average of spot prices), so
both legs converge by construction"; op rule "sell the spot leg at the
delivery time (08:00 UTC, ideally spread across the index averaging window)".
No exact minute-window definition exists in the repo docs or
`research/data_fetch/bybitq`; 07:30-08:00 is this task's operationalisation.

## Data (read-only)

Reference (index proxy) = 30-min TWAP of Binance USD-M perp 1m closes
07:30-08:00 (`data/raw/btc_intraday_20260924`, `data/raw/majors_intraday_20260924`;
spot proxy per the carry_audit precedent — no Binance/Bybit spot 1m exists
locally; spot is 4h/1h, Bybit spot 1h from 2021-07-05). Second venue: Bybit
linear perp 1m (`data/raw/bybit_linear_1m_20261004`, from 2021-06-01; covers
31/33 deliveries) + Bybit spot 1h 07:00 close (29/33). All 33 oc_cashcarry
deliveries score on the primary venue (33/33).

## Tracking error vs TWAP (bp) and trade-return effect (pp of allocated, frozen formula)

| sell point | te mean | te std | te worst | P(>20bp) | dret mean | dret worst |
|---|---|---|---|---|---|---|
| 08:00 open | +1.4 | 29.0 | 75.0 (BTC 2021-03-26) | 0.48 | +0.001 | 0.036 |
| 08:00-08:05 VWAP | +7.6 | 24.7 | 87.5 (BTC 2021-03-26) | 0.36 | +0.002 | 0.042 |
| 08:15 (late bot) | +5.5 | 34.9 | 91.5 (BTC 2024-12-27) | 0.55 | +0.000 | 0.051 |
| 6 slices 07:30-08:00 | -0.8 | 6.2 | 19.6 (ETH 2023-09-29) | 0.00 | -0.000 | 0.007 |

Mean-abs te: 22.9 / 18.2 / 27.9 / 4.7 bp. Single-point exits miss by >50bp in
6-18% of deliveries; the sliced exit never exceeds 20bp. Return effects are
small because the hedge nets: d(ret)/dS = 1/S_entry - 1/F_entry, so even a
90bp price miss moves net return by at most ~0.05pp (vs trade nets +0.18%..+6.9%).

## Settlement-model note

TWAP vs oc_cashcarry's modelled S_del (spot 4h close): mean +34bp, worst 938bp
(ETH 2021-09-24, trending delivery day) — but the P&L gap is only -0.26pp there
(worst over 33: 0.32pp, mean -0.016pp), again because both legs converge to the
index together. Venue check: Bybit-vs-Binance TWAP mean -0.2bp, worst 6.2bp —
the window is venue-robust; Bybit spot-1h 07:00 close vs TWAP worst 61bp (one
hourly-data point, not a tradable exit).

## Verdict

RECOMMEND: sell the spot leg in 6 equal slices across 07:30-08:00 (e.g. at
07:34/07:39/07:44/07:49/07:54/07:59 closes). It cuts exit-noise std 29->6bp,
worst miss 92->20bp, worst trade-return damage 0.051->0.007pp, and by
construction tracks the index average the future settles against. A single
08:00 print or a late 08:15 sale leaves a ~1-in-2 chance of >20bp slippage vs
the settlement index. Never sell at one print after a volatile night.

## Kết luận (tiếng Việt)

Bán spot một lệnh duy nhất quanh 08:00 UTC lệch trung bình ~20-28bp so với giá
thanh toán index, trường hợp xấu ~90bp (tuy thiệt hại lợi nhuận chỉ ~0,05 điểm
vì hai chân hedge trừ lẫn nhau). Chia 6 phần bán rải 07:30-08:00 giảm độ lệch
còn ~5bp trung bình, tối đa 20bp, hầu như khớp đúng giá index. Khuyến nghị chốt:
luôn bán rải 6 slices trong cửa sổ tính giá, không bán một lệnh, nhất là sau đêm
biến động mạnh.
