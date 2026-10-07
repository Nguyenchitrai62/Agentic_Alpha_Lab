# oc_carrymore REPORT — SAME cash-carry rule on Binance COIN-M, extended to BNB/SOL/XRP

POST-HOC (all years 2021-09-24..2026-09-23 were seen; rule itself is frozen
from `oc_cashcarry/PLAN.md`, unchanged: 7-day roll, 4 %/yr threshold,
hold-to-delivery, fees spot 0.001/side + futures 0.00055/0.0002). Repro:
`research/tournament/oc_carrymore/{fetch_cm_quarterly.py,MANIFEST.json,
analyze_carrymore.py,results.json}` + `tests/test_oc_carrymore.py`.
4h + 1h data only, one process (via `scripts/heavy_slot.py`).

## 1. Inventory: which quarterly contracts exist per coin (Binance COIN-M)

112 `cm_*` files verified sha256-ok against `data/raw/qbasis_20261003/manifest.json`:

| coin | cm contracts | first -> last delivery | window coverage 2021-09-24..2026-09-23 |
|---|---|---|---|
| BTC | 26 | 2020-09-25 -> 2026-12-25 | FULL (quarterly chain complete) |
| ETH | 26 | 2020-09-25 -> 2026-12-25 | FULL |
| BNB | 25 | 2020-12-25 -> 2026-12-25 | FULL in-window (no 2020-09 contract; irrelevant) |
| XRP | 25 | 2020-12-25 -> 2026-12-25 | FULL in-window (same gap) |
| SOL | 10 | 2024-09-27 -> 2026-12-25 | GAP: nothing before 2024-09-27; 2021-09-24..2024-09-26 has NO SOL quarterly |

No coin was dropped, but SOL contributes only from the 2024-09-27 expiry
(3 entered trades). USDT-margined (`um_*`) quarterlies exist ONLY for
BTC/ETH (50 files) — cm is the only quarterly chain for BNB/SOL/XRP.
Coin-settlement convexity not modelled (same approximation as the Bybit
inverse recompute); prices are same-scale USD so ln(F/S) applies unchanged.

## 2. Sanity: BTC/ETH on COIN-M vs the Bybit-based oc_cashcarry (um) trades

cm BTC+ETH: 34 entered (22 in-window, 16 skipped, 2 incomplete) vs um
33 entered (25 in-window, 13 skipped, 2 incomplete). 30 shared deliveries:
24/30 entry dates identical (roll-date consequence of the 7-day rule on
near-identical expiries), mean |basis| diff 1.56 pp/yr, mean |ret| diff
0.63 pp/trade. Pooled in-window: cm 0.5091 vs um 0.5234 on allocated
(-2.7%). Same economics, small honest venue difference — sanity PASSES.

## 3. Extra coins with the SAME rule (fees included, hold to delivery)

55 entered total, ALL net positive (min +0.21% on allocated; positive-basis
pair held to delivery is mathematically > 0 minus 0.275% drag).
Mean annualised net per trade: BTC 11.1%, ETH 11.8%, BNB 30.8% (5 trades,
early-2021 mania pre-window), SOL 5.8% (3 trades), XRP 10.9% (13 trades).
BNB's filter is strict: 19 skipped (basis rarely clears 4 %/yr outside mania).

Per anchor year, cm ALL (grouped by ENTRY; ret_alloc per allocated unit):

| year | n (BTC/ETH/BNB/SOL/XRP) | sum_ret_alloc | worst MtM (alloc) |
|---|---|---|---|
| 2021-09-24 | 3 (1/1/0/0/1) | 0.0409 | -0.50% |
| 2022-09-24 | 4 (2/1/0/0/1) | 0.0427 | -2.41% |
| 2023-09-24 | 14 (4/4/1/1/4) | 0.5171 | -3.23% |
| 2024-09-24 | 14 (4/4/1/2/3) | 0.2274 | -0.95% |
| 2025-09-24 | 1 (1/0/0/0/0) | 0.0056 | -1.03% |

5y pooled (36 in-window trades, sum 0.8337 on allocated): at f = 0.25/coin
+20.84% over 5y = +0.347 %/mo arithmetic (+0.332 geometric). BTC+ETH alone:
+12.73% = +0.212 (+0.207 geometric) — reproduces the um result (0.218/0.213).

## 4. Overlay on G2, compounded method REUSED UNCHANGED (f = 0.25/coin)

(a) BTC+ETH cm validates the method: um BTC+ETH re-run reproduces
oc_carrycompound G2_f0.25 TO THE DIGIT (5.634/2.778/16.75/full 16.66).

| row (POST-HOC) | 5y %/mo | worst year | max yearly DD | full-path DD | losing yrs |
|---|---|---|---|---|---|
| G2 base (f=0) | 5.410 | 2.588 (2021) | 16.91 | 16.82 | 0 |
| (a) G2 + cm BTC+ETH | 5.626 (+0.216) | 2.746 | 16.91 | 16.82 | 0 |
| (b) G2 + cm ALL majors | 5.771 (+0.361) | 2.853 | 16.91 | 16.82 | 0 |

Per-year R for (b): 2.853 / 3.327 / 6.902 / 11.263 / 4.730 (DD 10.86 /
16.91 / 15.59 / 8.46 / 12.45). Extra coins add +0.145 pp/mo over BTC+ETH
with NO new DD (carry leg close-marked, lower bound; max DD unchanged
because the BOT's own DD dominates every year).

## 5. Margin needed (sum of carry notionals vs equity, f = 0.25/coin)

Roll overlaps (~7d, entries land before the front delivers) stack same-coin
pairs: peak 4 concurrent pairs for BTC+ETH (spot cash 1.0x equity, gross
2.0x — exactly at the equity boundary, no borrow but zero spare), peak 8
for ALL (spot cash 2.0x, gross 4.0x — NEEDS BORROW, flagged). The (b) row's
+0.361 pp/mo is therefore NOT fundable from idle cash alone; a funded
variant (f scaled so peak spot <= 1.0x, i.e. ~f = 0.125/coin) would earn
roughly half the lift (~+0.18 pp/mo). Shorts need IM at 5x on their mark;
pairs are delta-hedged so gap loss is only basis widening (worst -3.23%
alloc in 2023 = -0.81% account at f = 0.25 single-pair, stacks only if
correlated).

## Verdict

Extension WORKS arithmetically (+0.361 pp/mo, no losing year, no new DD)
but is NOT deployable as-is at f = 0.25/coin: peak spot cash 2.0x equity
needs borrow, and the extra coins' venue is Binance COIN-M, not Bybit —
`research/data_fetch/bybitq` inventoried BTC/ETH dated only (executable
there via inverse quarterlies, +0.202 geometric), so BNB/SOL/XRP carry
would need Binance execution (delivery/settlement mechanics unconfirmed on
any live venue). Funded-size variant (~f = 0.125) keeps ~+0.18 pp/mo with
peak spot <= 1.0x. Needs the same prospective paper check as everything else.

## Ket luan tieng Viet (4 dong, POST-HOC)

- Loi nhuan them: +0,36 %/thang (5,41 -> 5,77 %/thang), khong nam thua nao.
- Drawdown them: khong co (DD nam max 16,91 va full-path 16,82 giu nguyen).
- Khong chay duoc tren Bybit cho BNB/SOL/XRP (chi co BTC/ETH duoc kiem ke) — can san Binance COIN-M.
- Loi nhuan nay can vay (peak spot 2,0x von); neu chi dung tien nhàn (f nho hon) thi con khoang +0,18 %/thang.
