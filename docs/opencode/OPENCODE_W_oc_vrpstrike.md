# OpenCode task oc_vrpstrike - the weekly short-straddle rule (V2) priced from REAL Deribit traded prices per strike
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_vrpstrike/` and `tests/test_oc_vrpstrike.py`.
Read research/tournament/oc_vrpstraddle/PLAN.md (the rule), research/tournament/oc_vrpconsistent/REPORT.md and
research/tournament/oc_vrprobust/REPORT.md (why: DVOL pricing overstated the premium; consistent r = 0.87 leaves +0.14 pp on G2).

## Data (read-only; two folders being filled by fetchers right now)
`data/raw/deribit_strike_20261007/{BTC,ETH}/<CUR>_YYYY-MM.parquet` (forward from 2021-01) and `data/raw/deribit_strike_20261007_b/{BTC,ETH}/`
(backward from 2026-09): hourly per-instrument aggregates of Deribit option trades: hour (UTC), instrument_name, expiry (date; expiry time is
08:00 UTC that day), strike, cp, n, sum_amount, vwap_price (coin), vwap_price_usd, vwap_iv (vol points), min_price, max_price, vwap_index,
taker_buy_amount, taker_sell_amount, block_amount. Use only COMPLETE months (manifest.json of each folder); list which months you used. If a
month exists in both folders, check they are identical and use one.

## Rule (frozen; V2 with traded prices)
- Friday entry: for each coin, the instrument pair (call, put) expiring the NEXT Friday with strike nearest to the index at 08:00 (vwap_index of
  that hour or the nearest hour). Entry price per leg = IV-based: take the amount-weighted vwap_iv of that exact instrument over hours
  08:00-10:59 Friday (if < 0.1 coin traded in that window for a leg, skip the coin-week and count it); SELL premium = BS(S_entry, K, T, 
  (vwap_iv - h) / 100) with h = 0.5 vol point for BTC, 1.0 for ETH (half-spread from docs/opencode/BYBIT_OPTIONS_20261007.md spreads + a
  margin), S_entry = Binance perp 1m close at 10:59 (the end of the entry window; label: a bot can sell inside the window). This replaces
  0.97 x DVOL by the traded IV of the actual instrument.
- Marks for SL (hourly) / TP (4h closes): BS at the latest traded vwap_iv of the SAME instrument (last hour with a trade, as-of) + h (ask
  side) for SL buy-back and the SL check; TP check at the traded IV (mid); if no trade for that instrument in the last 24 h, fall back to
  r x DVOL with r = the ratio (instrument IV / DVOL) at entry. Settlement, fees, SL -1 x premium, TP 0.3 x premium, q = 0.5 f E / S exactly as V2.
- Rows: standalone (f = 1) per year available; G2 overlay f = 0.25 per year (oc_carrycompound convention; reproduce G2 first). Years: report
  every anchor year whose months are COMPLETE; for incomplete years report monthly-chained partial results labelled PARTIAL.
- Diagnostics per year: entry IV / DVOL ratio distribution (cf. B.json 0.87), share of skipped coin-weeks, premium % of S, IV - realised.
- Run first on what is complete now; write `STATUS.md` with the months used; the leader will re-dispatch you to extend when the fetch finishes.
Verdict (Vietnamese 3 lines): with real traded prices, does the straddle overlay beat G2 on dev4 mean and worst year with DD <= G2 + 0.5?
