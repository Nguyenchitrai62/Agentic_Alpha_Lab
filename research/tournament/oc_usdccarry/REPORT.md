# oc_usdccarry REPORT — Bybit USDC-settled (linear) dated futures as carry leg (POST-HOC)

Question: would a linear (USDC-margined) dated short be a better carry leg than the
inverse one (no coin-margin convexity, same UTA collateral)? Method: the SAME frozen
rule as `oc_cashcarry/PLAN.md` (one entry per QUARTERLY contract, next-quarter when
front has <= 7d left else first availability, ENTER iff annualised basis
ln(F/S)*365/DTE >= 4 %/yr, equal-notional spot long + dated short, hold to delivery,
settlement = spot 4h close of the delivery bar; fees spot 0.001/side + fut 0.00055 +
delivery 0.0002, drag 0.00275 of allocated; f = 0.25), run on the Bybit USDC quarterly
chain from local public-kline parquets (`data/raw/bybit_quarterly_20261006/`, Bybit V5
`instruments-info` category linear + `kline` interval 60 via stored
`research/data_fetch/bybitq/inventory.json`). POST-HOC: the USDC-quarterly chain was
picked AFTER seeing inventory.json, so all USDC-vs-inverse comparisons are labelled
POST-HOC. Coins BTC + ETH. Repro: `research/tournament/oc_usdccarry/fetch_usdccarry.py`
(+ `results.json`, `MANIFEST.json` sha256); test `tests/test_oc_usdccarry.py`. 4h data
only, one process, public data only, no orders.

## 1. Inventory: which Bybit USDC dated futures ever existed

Stored V5 `instruments-info` (2026-10-06, Closed+Trading, BTC/ETH dated only, 442):

| series | BTC | ETH | status | first launch -> first delivery | last delivery |
|---|---|---|---|---|---|
| linear USDC `BTC-…` dated (all tenors) | 109 | 109 | ALL Closed | 2023-03-20 -> 2023-03-24 | 2025-12-26 |
| linear USDC QUARTERLY only (last-Friday Mar/Jun/Sep/Dec, same predicate as `scripts/carry_paper.py`) | 12 | 12 | ALL Closed | 2023-03-21 -> 2023-03-31 | 2025-12-26 |
| inverse quarterly (for reference) | 22 | 22 | Closed | 2021-03-11 / 2021-04-20 -> 2021-06-25 | 2026-09-25 |
| inverse quarterly live | 2 (Z26, H27) | 2 (Z26, H27) | Trading | — | 2027-03-26 |

USDC quarterly chain: 12 expiries/coin 2023-03-31, 2023-06-30, 2023-09-29, 2023-12-29,
2024-03-29, 2024-06-28, 2024-09-27, 2024-12-27, 2025-03-28, 2025-06-27, 2025-09-26,
2025-12-26 — delivery dates IDENTICAL to the inverse quarterlies (direct leg
comparison). Nothing exists before 2023-03 (anchor years 2021/2022 entries uncovered)
and nothing after 2025-12-26; as stored, ZERO USDC dated contracts are Trading today,
vs 4 live inverse quarterlies. Non-quarterly USDC dated (194 weeklies/monthlies) are
listed in inventory.json but EXCLUDED by the quarterly-only rule.

## 2. Liquidity (turnover from stored hourly klines, quote USDC)

| contract (BTC leg) | 1h rows | turnover total | /day |
|---|---|---|---|
| BTC-31MAR23 (stub, 10d life) | 243 | 1.08M | 0.11M |
| BTC-30JUN23 | 2209 | 24.9M | 0.27M |
| BTC-29SEP23 | 4537 | 51.1M | 0.27M |
| BTC-29DEC23 | 6385 | 84.5M | 0.32M |
| BTC-29MAR24 | 6384 | 130.8M | 0.49M |
| BTC-28JUN24 | 6385 | 241.7M | 0.91M |
| BTC-27SEP24 | 6385 | 323.3M | 1.22M |
| BTC-27DEC24 | 6385 | 512.8M | 1.93M |
| BTC-28MAR25 | 8257 | 656.8M | 1.91M |
| BTC-27JUN25 | 8569 | 502.0M | 1.41M |
| BTC-26SEP25 | 8569 | 390.9M | 1.09M |
| BTC-26DEC25 | 8400 | 275.7M | 0.79M |

ETH legs are the same shape (per-contract totals 0.5M stub -> 60-380M later, ~0.1-1.4M/day;
full table in `results.json:liquidity`). Verdict on size: plenty for the sleeve (each leg
<= 0.25 x <10k USDT ~ $2.5k notional; daily turnover is 40-700x that even in 2023), but
1-2 orders thinner than the majors' perps/inverse quarterlies and dead after 2025-12.

## 3. Frozen-rule recompute on USDC quarterlies (f = 0.25, POST-HOC)

24 quarterly contracts seen -> 20 entered, 4 skipped (BTC-30JUN23, ETH-30JUN23,
ETH-29SEP23, ETH-29DEC23, all basis < 4 %), 0 incomplete. All 20 entered trades net
positive (min +0.0004 on allocated: the Mar-23 stubs, 10d DTE, fee drag eats the premium).

| year (by ENTRY) | USDC n / sum_alloc | inverse n / sum | Binance USDT-M n / sum |
|---|---|---|---|
| 2021-09-24 | 0 / 0.0000 | 3 / 0.0411 | 4 / 0.0470 |
| 2022-09-24 | 4 / 0.0277 | 3 / 0.0411 | 4 / 0.0528 |
| 2023-09-24 | 8 / 0.2675 | 8 / 0.2845 | 8 / 0.2960 |
| 2024-09-24 | 8 / 0.1292 | 8 / 0.1242 | 8 / 0.1219 |
| 2025-09-24 | 0 / 0.0000 | 1 / 0.0064 | 1 / 0.0058 |
| 5y pooled | 20 / 0.4244 | 23 / 0.4973 | 25 / 0.5234 |

At f = 0.25: USDC sleeve +10.61% over 5y = +0.177 %/mo arithmetic (+0.1725 %/mo geometric)
vs inverse +12.43% (+0.207/+0.202) vs Binance +13.09% (+0.218/+0.213). Where data exists
(entries in 2022-2024 anchor years): USDC 0.4244 vs inverse 0.4498 (-5.6%) vs Binance
0.4707 (-9.8%); per-trade mean USDC 0.0212 vs inverse 0.0237 vs Binance 0.0235. Worst
4h-close MtM on allocated per year: 2022 -1.54%, 2023 -2.20%, 2024 -0.61% (account at
f = 0.25: -0.38 / -0.55 / -0.15%) — same shape as inverse (-0.74 / -2.49 / -0.52%).

## 4. Annualised basis: USDC vs inverse vs Binance (same deliveries, POST-HOC)

Per-delivery entry basis, USDC minus inverse (11 shared BTC + 9 shared ETH deliveries):
range -0.0060 .. +0.0032, typical |diff| <= 0.004 (e.g. Mar-24 BTC: USDC 11.76% vs inverse
12.58% vs Binance 13.10%; Jun-24 BTC: 18.07% vs 19.29% vs 21.37%; Sep-25 BTC: 5.77% vs
5.37% vs 4.94%; Dec-25 ETH: 6.87% vs 6.72% vs 6.82%). Net-return diff per shared trade
(USDC minus inverse): range -0.0060 .. +0.0032, mean -0.0006. No systematic USDC premium:
2023 favours inverse/Binance (-6 to -10% on the year), 2024 favours USDC (+4 to +6%) —
venue microstructure noise, not a leg edge. The Mar-23 stubs exist ONLY as USDC
(basis ~11.5-11.9% but DTE ~10d, ret +0.0004 each after the 0.00275 drag).

## Verdict

NO — a linear (USDC-margined) dated short is NOT a better carry leg than the inverse one
(POST-HOC comparison). Where both exist it is parity: per-trade basis within ~+-0.6 pp/yr
and returns within ~+-0.006/alloc, 2023 -6% vs inverse then 2024 +4% — noise, no convexity
benefit visible at sleeve size (each leg <= $2.5k; the coin-margin convexity of the
inverse leg is second-order next to a ~2 %/trade premium, as already noted in
`research/data_fetch/bybitq/REPORT.md`). Worse, the USDC chain covers LESS: no
2021/2022 entries, no 2025 entries, no 2026+ deliveries, and ZERO USDC dated contracts
are Trading in the stored 2026-10-06 inventory (all 218 Closed) vs 4 live inverse
quarterlies — the leg cannot even be entered today. Keep the inverse quarterly leg;
treat USDC quarterlies as a history-only cross-check, not a replacement.

Ba dòng kết luận (tiếng Việt): Chân USDC tuyến tính không tốt hơn chân inverse —
nơi so sánh được thì ngang nhau (chênh basis chỉ +-0,6 điểm %/năm, nhiễu sàn).
USDC thiếu hẳn 2021/2022 và 2025/2026+, hiện không còn hợp đồng nào đang Trading.
Giữ chân inverse quarterly, coi USDC chỉ là kiểm chứng lịch sử, không thay thế.
