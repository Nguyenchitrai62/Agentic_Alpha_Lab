# OpenCode task oc_optflow - does INFORMED option flow (strike-level, short-dated, large / block) predict the majors? (descriptive first)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_optflow/` and `tests/test_oc_optflow.py`.
Print progress at least every 10 minutes (idle-watchdog kills silent workers).

## Why
Option flow was only used AGGREGATED (v150 options-flow member: call/put buy-sell notional per 4h, closed; v337 options-informed member,
closed). The new strike-level data lets us isolate the part of the flow most likely to be INFORMED: short-dated (<= 9 days to expiry),
out-of-the-money, large or block trades, taker-initiated. Never tested.

## Data
`data/raw/deribit_strike_20261007/{BTC,ETH}/` + `data/raw/deribit_strike_20261007_b/{BTC,ETH}/` (hourly per-instrument aggregates 2021-01..
2026-09: hour, instrument_name, expiry (date; 08:00 UTC), strike, cp, n, sum_amount, vwap_price_usd, vwap_iv, vwap_index, taker_buy_amount,
taker_sell_amount, block_amount). Files on disk are complete months; overlapping months are identical (dedupe).

## Features (fixed now; per coin BTC / ETH; hourly, known at the END of the hour)
For instruments with 1..9 days to expiry and moneyness |K/index - 1| in [0.03, 0.15] (OTM only: puts K < index, calls K > index):
- NPB(h) = taker_buy - taker_sell notional (USD = amount x index) of OTM PUTS; NCB(h) = same for OTM CALLS; BLK(h) = block_amount notional
  of OTM puts minus OTM calls.
- Signals at each 4h bar open T (standard grid): F1 = sum over the last 24 h of (NCB - NPB) / trailing-30-day mean of |NCB| + |NPB| (net
  bullish informed flow), F2 = same with BLK, F3 = sum over the last 4 h of (NCB - NPB) normalised the same way.
SOL / BNB / XRP: use BTC's features (market-wide; disclose).

## Descriptive study (dev years 2021-09-24 .. 2025-09-23 only; no rule selection)
(a) BOOK: per year, Spearman IC of F1 / F2 / F3 vs the next 1-bar (4h) and next 6-bar (24h) open-to-open return of each coin (pooled and per
    coin), vol-normalised by trailing 360-bar sigma; bootstrap CI (block 42 bars).
(b) DIPS: join to the dip replica of research/tournament/oc_placebo_dip/compute_placebo_dip.py (reproduce base 7.718 first) - per year
    Spearman of F1 / F3 (as of the last full hour before the bar open) vs rung outcome and stop rate by tercile.
Consistency rule (fixed): a feature is a CANDIDATE only if its IC has the same sign in >= 4 of 4 dev years for (a) or >= 4 of 4 for (b), with
pooled |IC| >= 0.02. Report all; mark candidates. NO trading rule is scored in this task (a candidate goes to a separate pre-registered test).
Vietnamese 3-line verdict.
