# OpenCode task oc_vrprobust - is the G2 + weekly short-straddle overlay real? (pricing break-even, term structure, gaps, MANUAL)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_vrprobust/` and `tests/test_oc_vrprobust.py`.
Read research/tournament/oc_vrpstraddle/ fully (PLAN.md, REPORT.md, vrp.py, run_vrp.py) and REUSE its code by copying (do not edit it).

## Context
oc_vrpstraddle: V2 = weekly naked ATM straddle on BTC + ETH (sold Fri 08:05 UTC at 0.97 x DVOL, SL at -1 x premium checked hourly with
marks at 1.05 x DVOL, TP buy-back at 0.3 x premium on 4h closes, else settle vs the 07:30-07:59 mean), q = 0.5 x f x E / S per coin. Alone it
fails (DD 25.8, one losing dev year), but as an overlay on G2 in one account it gave 5y 6.41 %/month, worst year 4.37, yearly DD 16.10,
full-path DD 16.01 at f = 0.25 (G2: 5.41 / 2.59 / 16.91 / 16.82) - the first overlay that moves the frontier. Main doubt: PRICING. DVOL is a
30-day ATM index; a 7-day ATM straddle has its own IV, and fills were BS mids (no bid/ask). Everything below is a pre-registered robustness
study of the SAME rule (no new variants of the rule itself).

## A. Pricing break-even (dev4 only; then the most recent year once for the same rows)
Re-run V2 standalone and the G2 overlay (f = 0.25) with sigma_sell = k x DVOL for k in {0.97 (reproduce exactly first), 0.92, 0.88, 0.85, 0.80},
marks unchanged (1.05 x DVOL). Report the k at which the overlay's dev4 mean gain over G2 falls to 0 and the k at which the overlay's DD exceeds
G2's. This k* is the margin of safety against mispricing.

## B. Term structure from traded prices (preliminary; data still downloading)
From `data/raw/deribit_strike_20261007/{BTC,ETH}/*.parquet` (hourly per-instrument VWAP of Deribit option trades: hour, instrument_name,
expiry (date; Deribit expiries are 08:00 UTC that day), strike, cp, vwap_iv (vol points), vwap_index, sum_amount, taker_buy_amount,
taker_sell_amount) - use ONLY the complete months present when you start (list them), read-only: for every Friday in those months, take the
trades in hours 08:00-11:59 UTC of options expiring the NEXT Friday (6-8 days), |K / index - 1| <= 2 %, calls and puts; amount-weighted IV =
IV_7d_ATM. Compare with DVOL at 08:00 (data/raw/deribit_dvol_20261005): ratio r = IV_7d_ATM / DVOL per Friday; report the distribution (mean,
median, p10, p90) per month and pooled, and the share of Fridays with r < k* (from A). Also the taker-sell-only proxy: amount-weighted IV of
hours where taker_sell_amount > taker_buy_amount (seller-initiated prints ~ bid side) vs buyer-initiated - the difference approximates the
half spread in vol points.

## C. Execution realism rows (overlay f = 0.25, dev4; labelled)
1. Bybit fees: option fee per leg per side min(0.0003 x S, 0.07 x price); same settlement fee.
2. SL checked every 15 minutes on 1m closes (instead of hourly) with marks at 1.05 x DVOL - closer to a bot.
3. 1m-marked combined DD: at the G2 top-20 DD minutes and the sleeve's worst 10 hours, mark the open straddles on the 1m price (same sigma
   rule) and report the combined 1m-marked yearly / full-path DD (gate DD is max of close and 1m-marked).
4. Gap stress: at the worst historical minute for the combined book, an instantaneous all-coin move of -10 % / -15 % / +10 % / +15 % applied to
   G2's open dip + book exposure (method of research/tournament/oc_gapstress, with G2's gross cap 2.0) and the open straddles (BS at
   1.5 x DVOL after the gap); loss in % of equity vs G2 alone.

## D. Sizing and MANUAL (labelled; f chosen on dev4 only)
- Overlay f in {0.10, 0.25, 0.50} on G2 and on G2 + carry f 0.25 (build as research/tournament/oc_carrycompound does) - robust criterion on dev4.
- MANUAL: overlay f in {0.25, 0.50} on the honest MANUAL M5_human hourly equity (found by oc_putwrite in research/tournament/oc_manualcap)
  - does any row reach the MANUAL floor (>= 5 %/month, DD < 20, no losing year) on dev4? A human can sell one straddle per coin per week and
  place a stop (state how: Bybit options order types / stop availability - check https://api.bybit.com/v5/market/instruments-info?category=option&baseCoin=BTC
  for weekly expiries and the docs if reachable).

## Verdict
In bold: k*, the observed r distribution, and whether r is typically above k*. Adopt-worthiness needs: k* clearly below the typical r, gains
surviving C1-C3, gap losses not worse than G2's by > 3 pp, and the result labelled "screen; strike-level full validation pending".
