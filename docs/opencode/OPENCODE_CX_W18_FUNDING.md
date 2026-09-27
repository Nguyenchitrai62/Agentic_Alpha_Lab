# cx W18: cross-exchange funding history for majors (read OPENCODE_VF_COMMON.md first; data + study)
Files: `research/cx/fetch_funding.py`, `research/cx/funding_spread_study.py`,
`data/raw/cx_funding_20260925/*`, `artifacts/research/cx/*`.
Symbols: BTC, ETH, SOL, BNB, XRP USDT-margined linear perpetuals.
1. Fetch full public funding history (no auth):
   - Bybit: `https://api.bybit.com/v5/market/funding/history?category=linear&symbol=BTCUSDT&limit=200&endTime=<ms>`
     (paginate backwards by endTime; fields fundingRateTimestamp, fundingRate).
   - OKX: `https://www.okx.com/api/v5/public/funding-rate-history?instId=BTC-USDT-SWAP&limit=100&after=<ms>`
     (paginate; note OKX may only return the recent ~3 months; record the available range).
   - Binance already exists: `data/raw/xs_universe_20260924/{SYM}_funding.parquet`.
   Save one parquet per exchange/symbol with UTC timestamps; manifest with ranges and hashes.
   Sleep 0.2 s between calls; retry with backoff; never write outside the workspace.
2. Study (no trading claims): align settlements (Binance/Bybit/OKX settle at 00/08/16 UTC for these
   symbols; check and record any symbol with a different interval), compute per-settlement spread
   s = rate_A - rate_B for each exchange pair, and report per year: mean |s|, mean s, share of
   settlements with |s| > 0.01% and > 0.03%, persistence (autocorrelation of s at lags 1/3/9), and
   the annualised gross yield of a rule known in advance: at each settlement hold short-A/long-B
   (or the reverse) according to the SIGN OF THE PREVIOUS settlement's spread, per unit notional.
   Also report the same with a 7-settlement trailing mean sign. Development years only for
   conclusions (< 2025-09-14); report 2025-09-24.. separately and label it hidden.
3. SUMMARY.md (<= 15 lines).
