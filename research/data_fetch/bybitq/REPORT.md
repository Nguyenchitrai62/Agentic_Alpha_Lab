# data_bybitq: Bybit quarterly/dated futures + spot hourly (2026-10-06)

Scope: PUBLIC Bybit V5 market endpoints only (no keys), polite rate 4 req/s,
resume-safe, rerun: `.venv/Scripts/python.exe research/data_fetch/bybitq/fetch_bybitq.py`
(recompute: `.../analyze_bybit_carry.py`). Writes ONLY `research/data_fetch/bybitq/`
(this folder) and `data/raw/bybit_quarterly_20261006/` (gitignored).
Read with `research/tournament/oc_cashcarry/{PLAN,REPORT}.md` (the frozen rule).

## 1. Contract inventory (instruments-info, status=Closed+Trading)

Every BTC and ETH dated futures contract that ever existed on Bybit: **442**
(`inventory.json`: symbol, category, status, contractType, base/quote/settle,
launchTime, deliveryTime; delivery timestamps are exact ms from the venue).

| venue | BTC | ETH | first launch -> first delivery | last delivery |
|---|---|---|---|---|
| linear USDT `BTCUSDT-…` Closed | 80 | 80 | 2025-02-18 -> 2025-04-04 | 2026-10-02 |
| linear USDT Trading | 8 (5 weekly + DEC26/MAR27/JUN27 quarterly) | 8 | — | 2027-06-25 |
| linear USDC `BTC-…` Closed (weekly + 3 quarterlies) | 109 | 109 | 2023-03-20 -> 2023-03-24 | 2025-12-26 |
| inverse `BTCUSD(H/M/U/Z)` Closed (quarterly) | 22 (M21..U26) | 22 (M21..U26) | BTC 2021-03-11 / ETH 2021-04-20 -> 2021-06-25 | 2026-09-25 |
| inverse Trading (quarterly) | Z26, H27 | Z26, H27 | — | 2027-03-26 |

USDT-settled dated futures start 2025-02-18: NOTHING exists for anchor years
2021-2024. USDC dated are weeklies 2023-03..2025-03 only. The only Bybit
quarterly chain covering all five anchor years is INVERSE coin-margined
(H/M/U/Z cycle, deliveries ~Mar/Jun/Sep/Dec matching the Binance `um_*`
quarterly codes).

## 2. Download / kline coverage (interval=60, per-contract [launch, delivery+1h])

- 442/442 dated contracts serve klines (0 with zero rows; delisted contracts
  still serve history when `start`/`end` fall in their lifetime — verified for
  inverse `BTCUSDZ23` and linear `BTC-01SEP23` before bulk fetch).
- 444 parquet files under `data/raw/bybit_quarterly_20261006/`
  (`inv_*` 48, `lin_*` 394, `spot_BTCUSDT/spot_ETHUSDT_1h` 2): 713,236 contract
  rows + 2 x 46,051 spot rows. Spot is perfectly continuous (46,050/46,050
  exact 1h steps, 2021-07-05 12:00 UTC -> 2026-10-06 06:00 UTC, 0 gaps).

## 3. Recompute: oc_cashcarry rule UNCHANGED on Bybit data

Same code path as `oc_cashcarry/analyze_cashcarry.py` (7-day roll, 4 %/yr
threshold, hold to delivery, settlement = spot 4h close of the delivery bar,
fees spot 0.001/side + futures 0.00055 + delivery 0.0002). Bybit hourly ->
4h grid 00/04/… UTC; F(t) = last futures 4h close with close_time <= spot
close_time (causal). Per anchor year, grouped by ENTRY (ret_alloc = P&L per
allocated unit):

| year | Binance USDT-q (basis) | Bybit INVERSE-q | Bybit USDT-lin dated |
|---|---|---|---|
| 2021-09-24 | 0.0470, n=4 | 0.0411, n=3 | 0 (no contracts) |
| 2022-09-24 | 0.0528, n=4 | 0.0411, n=3 | 0 (no contracts) |
| 2023-09-24 | 0.2960, n=8 | 0.2845, n=8 | 0 (no contracts) |
| 2024-09-24 | 0.1219, n=8 | 0.1242, n=8 | 0.0079, n=35 (weeklies) |
| 2025-09-24 | 0.0058, n=1 | 0.0064, n=1 | 0.0180, n=32 (weeklies) |
| 5y pooled | **0.5234**, 25 trades | **0.4973**, 23 trades | 0.0259, 67 weekly trades |

2021/2022 shortfall on Bybit (3 vs 4 trades) is honest venue difference: two
quarters' entry basis printed just under 4 % on Bybit (skipped: 5+5 in those
years) while clearing it on Binance (e.g. ETH Jun-22 + BTC Jun-23); Bybit spot
also starts 2021-07-05 (2 pre-window trades vs Binance 8). Per-trade economics
match: e.g. Mar-24 BTC — Binance basis 13.1 % ret +0.0525, Bybit 12.6 % +0.0504.

Sleeve contribution at f = 0.25 per coin (account units):
Bybit-inverse +12.43 % over 5y = **+0.207 %/mo arithmetic (+0.202 %/mo geometric)**
vs Binance +13.09 % = +0.218 (+0.213). At f = 0.50: +24.86 % (+0.414/+0.396)
vs +26.17 % (+0.436/+0.416). Worst MtM on allocated (2021..2025): Bybit
-0.42 / -0.74 / -2.49 / -0.52 / -1.36 % vs Binance -1.01 / -0.71 / -2.65 /
-0.39 / -2.17 % (account at f = 0.25: worst -0.62 % in 2023 on both venues).

## 4. Bybit contract coverage gaps

1. No USDT-settled dated history before 2025-02-18 (anchor years 2021-2024
   cannot be traded as spot+USDT-quarterly on Bybit).
2. USDC dated are weeklies 2023-03..2025-03 plus 3 longer quarterlies
   (JUN25/SEP25/DEC25, launched 2024-07..2025-01); nothing before 2023-03
   (wrong settle + mostly wrong tenor for the quarterly rule; listed in
   `inventory.json`, not recomputed).
3. Inverse quarterlies are complete (M21..U26 + Z26/H27 live) but coin-margined:
   the P&L currency is BTC/ETH, so the price-return formula used here is an
   approximation (convexity not modelled — second order next to a ~2 %/yr premium).
4. Bybit spot starts 2021-07-05 (first anchor year's pre-window is shorter).
5. Conservative bias: Bybit `deliveryFeeRate` = 0 on these contracts vs the
   assumed 0.0002 delivery fee — live cost is weakly lower than reported.

## Verdict

**YES — executable on Bybit with comparable yield, via inverse quarterlies,
not USDT quarterlies.** The Bybit-native quarterly chain (long spot + short
inverse quarterly, same 4 %/7-day/hold-to-delivery rule) yields +0.497 per
allocated unit over the 5 walk-forward years vs +0.523 on Binance data (-5 %),
i.e. **+0.20 %/month geometric at f = 0.25 (+0.40 at f = 0.50)** with worst
incremental account MtM -0.6 % (-1.2 % at f = 0.50) — the same "small, honest,
nearly risk-free" add-on, no new DD source, same idle-in-2025 behaviour (1 of
6 entered). The USDT-linear venue cannot replicate the 2021-2024 backtest
(it did not exist); its 2025+ weekly carry (+0.018 on allocated, 32 trades) is
consistent with the low-premium regime, not a substitute series.
