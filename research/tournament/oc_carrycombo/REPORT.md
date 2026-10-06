# oc_carrycombo REPORT — BOT/MANUAL account + locked cash-and-carry sleeve

Question: does overlaying the frozen oc_cashcarry sleeve (long spot + short
quarterly to delivery, enter iff annualised basis >= 4 %/yr, fees
spot 0.1 %/side + futures 0.055 %/0.02 %) on the G2 BOT or the M5_human MANUAL
account change the walk-forward verdict? Method: carry trades are FROZEN from
`oc_cashcarry/results.json` (33 entered; entry set re-derived here bit-exact).
Combined account = base 4-phase mix (each phase 1/4, reset metric) + sleeve at
f in {0.25, 0.50} of equity, marked HOURLY (Binance spot 1h closes downloaded
from public klines + quarterly 1h closes, causal: marks at hour H use only 1h
bars with open_time < H; base legs are 4h equities ffilled per v388.hourly),
sized/rebalanced ONLY at rolls (pair legs = f x total equity at entry hour,
held to delivery). Per-year R/DD use exactly `reset_metric.year_reset`
arithmetic; full-path DD uses the v421 formula. f=0 reproduces v421_result G2
(5.41/W 2.588/DD 16.91/full 16.82) and oc_manualcap M5_human
(3.728/W 0.847/maxDD 17.94/full 17.79) TO THE DIGIT (asserted in-script).
Repro: `research/tournament/oc_carrycombo/analyze_carrycombo.py` (one process,
~44k hourly rows, no 1m, no engine rerun) + `tests/test_oc_carrycombo.py`.
All five years are research data; prospective paper is still the clean check.

## (1) Combined paths vs base alone

BOT (G2 = R2B1D17BFG2; per anchor year R %/mo, DD %):

| year | G2 alone | +carry f=0.25 | +carry f=0.50 |
|---|---|---|---|
| 2021-09-24 | 2.588 / 10.86 | 2.647 / 10.79 | 2.705 / 10.72 |
| 2022-09-24 | 3.282 / 16.91 | 3.283 / 16.78 | 3.285 / 16.65 |
| 2023-09-24 | 6.045 / 15.81 | 6.168 / 15.72 | 6.296 / 15.64 |
| 2024-09-24 | 10.677 / 8.27 | 10.559 / 8.08 | 10.450 / 7.88 |
| 2025-09-24 | 4.648 / 12.90 | 4.593 / 12.57 | 4.536 / 12.24 |
| 5y mean / worst / maxDD | 5.410 / 2.588 / 16.91 | 5.413 / 2.647 / 16.78 | 5.418 / 2.705 / 16.65 |
| full-path DD (marked/close) | 16.82 / 16.05 | 16.34 / 15.60 | 15.86 / 15.15 |

MANUAL (M5_human; book win 64.8 % unchanged — carry adds 29 settled pairs,
all net positive, combined all-trade win 65.1 % vs book 64.8 %):

| row | 5y R | worst | max yearly DD | full-path DD |
|---|---|---|---|---|
| MAN alone | 3.728 | 0.847 | 17.94 | 17.79 |
| MAN + carry f=0.25 | 3.746 | 0.916 | 17.78 | 17.19 |
| MAN + carry f=0.50 | 3.765 | 0.987 | 17.63 | 16.61 |

Headline: the sleeve adds REAL absolute wealth every year (settled carry P&L
is strictly positive, 29/29 in-window pairs) but the compounded MONTHLY RATE
barely moves (+0.00 .. +0.04 pp/mo, linear in f). Mechanism, not noise: the
sleeve is rebalanced only at rolls, so on a fast-growing account its weight
decays intra-year (2024: account x3.3 while the sleeve earns its fixed ~5 % on
entry notional) — a lower-return overlay dilutes the blended rate while
raising absolute wealth. DD improves a little at every f (-0.1 .. -1.0 pp,
full-path marked 16.82 -> 16.34 -> 15.86) because sleeve marks are small and
uncorrelated with BOT troughs. No losing year appears or disappears anywhere.
Funded-capital note: the overlay needs up to 2f EXTRA cash for spot legs when
both coins are open (f=0.25 -> up to 1.5x funded); the R above uses base
equity as denominator, same convention as oc_cashcarry. On total funded
capital the rate lift is even smaller.

## (2) USDT-margined (um_) vs COIN-M (cm_) quarterlies

`data/raw` HAS USD-M quarterly closes (`um_BTCUSDT_YYMMDD`), so both series
were compared at the SAME entry bars, same spot S_entry, same DTE (signal
only; cm settles in coin, um in USDT). 33/33 entered pairs have a same-date
cm contract: mean (cm-um) -8.4 bps, median +11.7, mean |diff| 121.9, p90 328.8;
entry-decision agreement 32/33 (one flip: ETH 2023-09-29, um 5.74 % enter vs
cm 3.56 % skip). Skipped/incomplete um contracts with cm data: 15,
agreement 13/15 (flips: ETH 2023-06-30 um 3.71 % skip vs cm 4.19 % enter;
ETH 2026-12-25 um 3.58 % skip vs cm 4.01 % enter; the um-enter case is
BTC 2026-12-25, excluded as incomplete for lack of delivery data, both agree
enter). Verdict: same signal in practice; live venue stays USDT-margined
(linear), so the um series is the right proxy. Gap stated: cm margin/P&L is
coin-denominated (quanto effect) and was NOT simulated.

## (3) Bybit availability (fetched 2026-10-06, public endpoints, no keys)

- Linear (USDT-margined) quarterlies, status Trading: BTCUSDT-25DEC26,
  BTCUSDT-26MAR27, BTCUSDT-25JUN27 (same for ETHUSDT), plus weeklies
  09/16/23/30OCT26 and 27NOV26. settleCoin USDT, deliveryFeeRate "0",
  fundingInterval 0 (no funding, like the modelled delivery future),
  maxLeverage 50, unifiedMarginTrade true.
  (`/v5/market/instruments-info?category=linear&limit=1000`)
- Inverse (coin-margined) quarterlies, status Trading: BTCUSDZ26, BTCUSDH27,
  ETHUSDZ26, ETHUSDH27; settle BTC/ETH. (`...?category=inverse&limit=1000`)
- Fees VIP0 (help-center Trading-Fee-Structure, 2026-09-02): futures
  taker 0.055 % / maker 0.02 %, spot 0.1 %/0.1 % — exactly the gate pair and
  the carry fee assumptions used here. Futures settlement fee: instruments
  show deliveryFeeRate 0 for the listed quarterlies.
- UTA collateral: spot BTC and ETH count as collateral at 95 % (5 % haircut)
  base tier (help-center UTA intro article) — BETTER than oc_cashcarry's
  5 %/10 % haircut assumption. ASSUMPTION: tier breakpoints above base sizes
  were not pulled; a < 10k USDT carry stays in the base tier.
- ASSUMPTIONS (marked): Bybit delivery-index methodology vs the modelled
  spot-4h-close settlement (bounded by the delivery-bar spot range; nets to
  first order in the hedged pair); historical Bybit quarterly prices not used
  (Binance proxy); Bybit expiries are Fridays like Binance; tickers differ
  (BTCUSDT-25DEC26 vs BTCUSDT_241227).

## (4) MANUAL estimate + khuyen nghi tieng Viet (plain)

MANUAL tot nhat trung thuc (M5_human) dat 3.73 %/thang, DD 17.9, win book
64.8 %. Cong them sleeve carry (f=0.25, cung may hourly nhu BOT): ~3.75 %/thang
(+0.02 pp), DD nam 17.8, full-path 17.2, win book khong doi. f=0.50:
~3.77 %/thang, DD 17.6/16.6. Carry can dung 4 lan ra quyet dinh/nam (moi quy
dao han: khi basis >= 4 %/nam thi mua spot + short quarterly, nam toi dao han;
moi cap can 3 lenh tay: mua spot, short futures, ban spot khi dao han
— futures tu tat toan; trung binh ~5 cap/nam ≈ 15 lenh/nam).

KHUYEN NGHI: (a) MANUAL: carry la mon cong them nho, gan nhu khong rui ro
(DD giam nhe, chua tung lo von o cap nao), von ran h co the lam them — NHUNG
no khong dua MANUAL toi san 5 %/thang (con thieu ~1.3 pp; ke ca f=0.50 van
~3.77). San base MANUAL van FAIL; dung ky vong carry cuu duoc. Can them tien
mat toi 50 % (f=0.25) cho chan spot. (b) BOT: G2 5.41 + carry van ~5.41-5.42
(tien lai tuyet doi co tang, ty suat gop gan nhu khong doi vi pha loang),
DD do nhe. Co the trien khai nhu add-on f=0.25 (gan nhu mien phi ve DD/margin,
0 blocked closes ke thua tu oc_cashcarry) NHUNG phai xac nhan tren Bybit truoc:
quy mo toi thieu, cach dao han/tat toan, va chay paper rieng cho sleeve vi
du lieu backtest la Binance. Carry khong dua BOT toi 8 %/thang.

## Caveats

- 4 pre-window pairs delivered before the grid are excluded (no P&L imputed,
  like oc_cashcarry); 4 pairs spanning the grid start are inherited at market
  with MtM measured from their actual entries (sunk ~+-0.1 %, disclosed).
- Hourly spot 1h 2021-2026 was downloaded from public Binance klines during
  this study (cached outside the repo); futures 1h are repo data. No 1m used.
- Settlement uses the frozen delivery-bar spot-4h-close rule; near delivery
  the dead quarterly prints flat while spot still moves (e.g. Dec-2024) —
  genuine MtM of an unadjustable short, snaps to the frozen ret at settle.
- Bybit weeklies exist but the sleeve uses quarterlies only (fewer actions,
  matches the frozen rule).
