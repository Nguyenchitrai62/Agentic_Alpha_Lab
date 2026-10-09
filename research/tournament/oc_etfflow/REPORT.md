# oc_etfflow REPORT — spot-ETF outflow book-long throttle (idea B2, SHORT-SPAN)

Descriptive only. ETF flows exist 2024-01-11..2026-09-23 (capped), so NO dev4
selection was possible or attempted. Pre-registered T1 (S5<p5) / T2 (S5<p10) /
C0 (constant x0.95) in PLAN.md before any outcome; no changes after outcomes.

## Data

- Farside verified reachable (HTTP 200, one GET each 2026-10-07): /btc/ (272 kB),
  /eth/ (195 kB), robots.txt lists only Twitterbot (no bar on research GETs).
  Landing pages carry only the recent ~15-row window, so history comes from the
  same publisher's linked all-data pages, one GET each (BTC 823 kB / 702 rows
  2024-01-11..2026-10-06; ETH 625 kB / 564 rows 2024-07-23..2026-10-06).
- Saved `data/raw/etf_flows_20261007/btc|eth_etf_flows_daily.csv`
  (date,total_net_flow_usd_m; Total column, `(x)`=negative, `-`=0) + manifest
  (URLs, fetch UTC, sha256, spans, parser, robots note). Signal+engine capped at
  D<=2026-09-23 (693 trading days); CSV rows after the cap are never used.
- Availability (conservative): day-D value known from D+1 08:00 UTC.

## Signal

S5(B)=sum of BTC+ETH net flow over last 5 published trading days as of 4h bar B
(close>=D+1 08:00); H(B)=last 250 distinct-day S5 strictly before B (min 120,
else OFF); T1_ON=S5<p5(H), T2_ON=S5<p10(H), global book-long x0.5, shorts
untouched; z diagnostic only. Grid = standard book rows (10950 bars).
First gates: T2 2024-08-07, T1 2024-09-04 (120-day warm-up). Panel:
`research/tournament/oc_etfflow/panel.parquet` (T,Dstar,S5,p5,p10,z,n_hist,
T1_on,T2_on); T1 378 bars / T2 678 bars total.

## Engine (4-phase, exactly like v426_book_brake.py, heavy_slot tag oc_etfflow)

G2 = inv k1.0 kd1.7 bear G2.0 from the v421 cache, reproduced TO THE DIGIT
(5.41/W2.588/DD16.91/full16.82 asserted in-script). Gate applied per (T,sym)
long weight after the bear filter, before shifted-clock ffill. Costs: maker
0.0002 / taker 0.00055, longs funding 0.0001/8h, shorts 0; 1m trade-through,
5-min ban, stop-first. Metric: reset per anchor year (fresh 1.0) R %/mo / DD %.

## Overlap years: R / DD vs G2 + gated weeks + exposure control C0

| year | G2 R/DD | T1 R/DD (ΔR) | T2 R/DD (ΔR) | C0 R/DD | gated bars wks T1 / T2 | mean long-mult T1/T2 |
|---|---|---|---|---|---|---|
| 2021 NO-DATA | 2.588/10.86 | 2.588/10.86 (+0.000) | same | 2.783/10.85 | 0 (0w) / 0 (0w) | 1.0000/1.0000 |
| 2022 NO-DATA | 3.282/16.91 | same | same | 3.204/16.78 | 0/0 | 1.0000/1.0000 |
| 2023 PARTIAL | 6.045/15.81 | 6.045/15.81 (+0.000) | same | 6.312/15.84 | 42 (2w) / 54 (3w) | 0.9904/0.9877 |
| 2024 OVERLAP | 10.677/8.27 | 10.628/8.27 (-0.049) | 10.499/8.27 (-0.178) | 10.678/8.58 | 132 (8w) / 276 (14w) | 0.9699/0.9370 |
| 2025 OVERLAP* | 4.648/12.90 | 4.521/13.08 (-0.127) | 4.335/13.05 (-0.313) | 4.556/12.47 | 204 (14w) / 348 (19w) | 0.9534/0.9205 |
| 5y (context) | 5.410/16.91 full16.82 | 5.375/16.91 full16.82 | 5.313/16.91 full16.82 | 5.468/16.78 full16.74 | — | — |

*2025 scored once with the rest (no re-pick); weeks = distinct Mon-Sun UTC weeks
with ≥1 gated bar. T1/T2 shift 716/1134 long (T,sym) cells per phase engine run.

Read: the throttle never helps. Both full overlap years lose return under both
gates (2024 −0.05/−0.18pp, 2025 −0.13/−0.31pp), 2025 DD worsens +0.15–0.18pp,
2024 DD flat, full-path DD flat at 16.82. The exposure-matched constant C0
(x0.95) is flat-to-better than G2 in the overlap (2024 +0.001, 2025 −0.092 with
DD 12.47 better than both gates), so the gate's TIMING destroys value versus
just holding less. 2023 partial tail (2–3 gated weeks) moves nothing.

## Leakage checks

- Feature timing: S5(B) uses only F(D) with D+1 08:00 UTC ≤ close(B); panel
  recomputed from date-truncated CSVs is bit-identical (test_truncation); a bar
  1 minute before a publication does not see it (test_availability_edge).
- Fit windows: no pooled fit anywhere; p5/p10 are trailing-only (last 250
  distinct prior days, min 120); satisfies the 7-day embargo by construction
  (strictly-before rows only).
- Label windows: engine forward returns start at the next 4h open after close
  (inherited v426 path, unchanged code except the gate tensor).
- Fill timing: inherited engine (limit trade-through, 5-min ban, stop-first);
  gate only scales standard-row book weights, never touches fills/stops/TPs.
- Cap: no flow dated after 2026-09-23 enters any S5/H/gate or engine bar.

## Caveats

Short span (~2 gated episodes/yr, 8–19 gated weeks/yr) → wide CI; 2021–2022 are
mechanical zeros; trailing quantiles need a 120-day warm-up so 2024-H1 can
never gate; holiday zero-rows enter S5 as 0 (disclosed); book-trade win-rate
split is not retained by this 4-phase path (R/DD only per the assignment).

## Verdict

REJECT as a deployment gate on this evidence: outflow throttle loses return in
both overlap years and adds DD in 2025, underperforming a constant-exposure
cut. At best log the gate prospectively alongside paper (no capital effect).

---
Kết luận (3 dòng):
1. Không triển khai gate ETF-outflow: cả hai năm overlap đều mất return và 2025 tăng DD.
2. Hiệu ứng thời điểm là âm so với chỉ giảm exposure hằng số (C0 tốt hơn cả T1/T2).
3. Cùng lắm ghi log prospective gate này (không tác động vốn), chờ dữ liệu ngoài mẫu dài hơn.
