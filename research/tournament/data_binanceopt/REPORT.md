# data_binanceopt: coin-specific IV on Binance EAPI for BNB / SOL / XRP?

## Answer
No walk-forward-usable coin-specific IV exists. EOHSummary (the only
per-symbol IV archive) covers 2023-05-18..2023-10-23 only (~5 months, then
discontinued); BVOLIndex (continuous to now) is BTC/ETH only; SOL has no
options IV history anywhere on Binance.

## Coverage table (verified 2026-10-07, public keyless GETs)
| coin | EAPI live | EOHSummary archive | BVOLIndex archive |
|---|---|---|---|
| BTC | yes (666 symbols) | 2023-05-18..2023-10-23, 147/159 days, no gaps >1d | 2023-06-20..2026-10-06, 1179/1179 days |
| ETH | yes (576) | 2023-05-18..2023-10-23, 147/159 days | 2023-06-20..2026-10-06, 1179/1179 days |
| BNB | yes (136) | 2023-05-18..2023-10-23, 121/159 days (38 missing: 07-22..08-03, 08-19..08-29, 09-08..09-18 blocks) | NONE |
| XRP | yes (52) | 2023-05-19..2023-10-20, 99/155 days (56 missing, same blocks + late-Sep/early-Oct) | NONE |
| SOL | yes (80) | NONE (no SOLUSDT prefix on data.binance.vision) | NONE |

## Probe findings (raw in data/raw/binance_eapi_20261007/)
- exchangeInfo: 10 underlyings, 1628 live symbols; NO listing dates exposed.
- klines: per-symbol only (live symbols, from listing week); expired symbol ->
  HTTP 400 -1121 (no history). Weekly/monthly tenors list ~2-6 weeks back.
- mark: live snapshot only (markPrice/markIV/greeks per symbol, 1628 rows saved).
- historicalTrades path -> WAF 404 page; /trades (recent) works but is tape, not history.
- exerciseHistory: recent weeks only; startTime filter returns nothing older.
- S3 enumeration via s3-ap-northeast-1 bucket listing: data/option/ holds ONLY
  daily/{BVOLIndex,EOHSummary}; no monthly aggregates, no other option data.

## Downloads (162 MB < 500 MB limit; 560/560 ok, 0 fail)
- All BNB+XRP EOHSummary zips (220) -> BNB_iv_daily.parquet (121 rows),
  XRP_iv_daily.parquet (99 rows); daily = OI-weighted mean + median of mark_iv
  (mark_iv>0, OI>0 rows). Means: BNB oiw 0.725/med 0.635, XRP oiw 1.221/med 1.067.
- BVOLIndex BTC+ETH weekly sample (340 zips, every 7th day + last) ->
  BTC/ETH_bvol_daily.parquet (170 rows each, day-close tick).
- manifest.json: per-zip URL + sha256 + date; per-parquet sha256 + span.

## BTC/ETH cross-check vs Deribit DVOL (167 overlap days, 2023-06-20..2026-09-20)
- BTC: level corr 0.9862, daily-change corr 0.9388 (means BVOL 51.24 / DVOL 49.28).
- ETH: level corr 0.9919, daily-change corr 0.9618 (means 65.91 / 62.59).
- Binance venue IV tracks Deribit almost 1:1 -> BTC-IV-as-proxy was already fine.

## Walk-forward verdict
Needs history >= 2021-09: BNB/XRP have 5 months in 2023, SOL nothing. NOT possible.

## Leakage note
Archive files are dated by UTC day, used strictly as-of that date; no fit,
threshold or quantile was estimated (coverage study only); nothing from
>= 2025-09-24 was used for any choice (Deribit comparison uses pre-cutoff
overlap, weekly sampling fixed before download).

## Vietnamese verdict
- KHONG DUNG DUOC cho walk-forward: IV rieng BNB/XRP chi co 5 thang 2023, SOL khong co gi.
- Giu BTC-IV proxy hien tai: BVOL Binance gan nhu trung khit DVOL Deribit (corr ~0.99).
- De nghi: dong huong du lieu nay, khong chay engine.
