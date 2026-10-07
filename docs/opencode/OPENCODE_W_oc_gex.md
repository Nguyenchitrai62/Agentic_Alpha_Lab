# OpenCode task oc_gex - dealer gamma exposure (GEX) proxy from Deribit strike-level trades, and whether it predicts dip-rung outcomes
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_gex/` and `tests/test_oc_gex.py`.

## Why (new information class, never tested here)
Option dealers hedge their gamma: when dealers are net LONG gamma they sell rallies / buy dips (moves are dampened -> flushes revert);
when net SHORT gamma they chase (moves extend -> cascades). The G2 dip ladder is a rebound bet whose worst losses are multi-coin stop
cascades, so dealer gamma is a natural, untested state variable. Closed option work used only aggregated IV / skew / volume (v150, v337,
oc_optctx, oc_skewbook) - never positioning-weighted gamma.

## Data
`data/raw/deribit_strike_20261007/{BTC,ETH}/` and `data/raw/deribit_strike_20261007_b/{BTC,ETH}/` (hourly per-instrument aggregates of all
Deribit option trades 2021-01..2026-09; columns hour, instrument_name, expiry (date, 08:00 UTC), strike, cp, sum_amount, vwap_iv, vwap_index,
taker_buy_amount, taker_sell_amount, ...). Every file on disk is a complete month; dedupe overlapping months (identical).

## Proxy (fixed before any outcome)
- Customer net position per instrument q_i(t) = cumulative sum over hours <= t of (taker_buy_amount - taker_sell_amount) since the
  instrument's first trade in the data (assumption: takers = customers, makers = dealers; disclose). Instruments listed before 2021-01 have
  unknown history -> start the proxy at 2021-04-01 (weeklies / monthlies / quarterlies listed after 2021-01 are complete by then; state the
  share of open interest-like volume from older instruments that is missing).
- Dealer gamma GEX(t) = - sum_i q_i(t) * Gamma_BS(S_t, K_i, T_i, iv_i) * S_t^2 * 0.01 (dollar gamma per 1 % move), over instruments not yet
  expired at t, iv_i = last traded vwap_iv of that instrument (as-of), S_t = vwap_index of the hour (as-of). Normalise: GEXn = GEX / (S_t x
  trailing 30-day mean of hourly traded notional) or a z-score over the trailing 90 days (pick ONE normalisation now and state it).
- Hourly series for BTC and ETH; known at the END of each hour. For SOL/BNB/XRP use BTC's GEXn (market-wide dealer state; disclose).
- Sanity checks (no outcomes): GEX sign around known events (e.g. expiry days, 2022 crashes), correlation of GEXn with subsequent realised
  vol (should be NEGATIVE if the mechanism exists) - realised vol is an outcome, so compute it only on the four dev years.

## Screen (dev years 2021-09-24 .. 2025-09-23 only for selection; the most recent year once at the end)
1. Descriptive: join GEXn as of the last full hour before each dip rung's bar open to the G2 dip replica (copy
   research/tournament/oc_placebo_dip/compute_placebo_dip.py; reproduce base 7.718 first). Per year: Spearman(GEXn, rung outcome), outcome by
   GEXn tercile, stop-out rate by tercile. Hypothesis direction fixed now: HIGH (dealers long gamma) = better rungs / fewer stops.
2. Only if the sign is as hypothesised in >= 3 of 4 dev years: pre-registered size tilt T1 = rung x1.25 in the top GEXn tercile, x0.75 in
   the bottom (terciles from training rows before each anchor - 7 d), scored with the established dip gate (PROMISING legs + dSum5y >= +0.273,
   labelled 5-year calibration) AND the dev4 view; exposure-matched constant control. No other variants.
3. Report and Vietnamese 3-line verdict. If PROMISING, say so in bold; the leader decides on an engine run.
Print progress at least every 10 minutes (idle-watchdog).
