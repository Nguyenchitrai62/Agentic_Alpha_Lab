# OpenCode task ops_straddlepaper - prospective PAPER ledger for the weekly short-straddle sleeve with REAL Bybit option quotes
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. EXCEPTION to the common write scope (leader-assigned implementation): you may CREATE
`scripts/straddle_paper.py` and `tests/test_straddle_paper.py`, and write `docs/opencode/STRADDLEPAPER_20261007.md`. Do not edit any other file
(not carry_paper.py, not bot/, not backend/). Public Bybit V5 GET endpoints only - never signed, never POST, never an order, never read .env.
Do NOT start the hourly loop yourself (the leader starts it); you may run `--once --dry-run` for testing.

## Why
research/tournament/oc_vrpstraddle (V2, blind audit PASS-WITH-NOTES) is the first overlay that moves the G2 frontier in research, but its
prices were Black-Scholes at 0.97 x DVOL. The only clean evidence is prospective, and Bybit's live option quotes let the paper ledger use REAL
bid / ask / mark prices (docs/opencode/BYBIT_OPTIONS_20261007.md: weekly expiries Fri 08:00 UTC, USDT-settled, fees maker 0.02 % / taker
0.03 % capped at 7 % of price, delivery 0.015 % capped at 12.5 %, settlement = average index 07:30-08:00).
The FIRST entry must be possible on Friday 2026-10-09 08:05 UTC: be done well before.

## Frozen rule (copy the oc_vrpstraddle V2 rule; prices from Bybit instead of BS)
- Every Friday at the first run >= 08:05 UTC (and < 09:00; if the loop misses that hour, skip the week and log it): per coin (BTC, ETH) take the
  option expiry of the NEXT Friday 08:00 UTC (6.99 days); S = Bybit index / underlying price from the option tickers at that moment; strike K =
  the listed strike nearest to S (ties -> lower). Sell 1 call + 1 put at K: fill price = the BEST BID of each leg (we sell into the bid; record
  bid, ask, mark, mark IV, bid IV); if a leg has no bid, skip the coin for the week (log). Fee per leg min(0.0003 x S, 0.07 x price) (taker,
  since we hit the bid). Also record DVOL-free research comparison: BS price at 0.97 x DVOL (GET https://www.deribit.com/api/v2/public/
  get_volatility_index_data, currency, resolution 3600, last closed candle) so research pricing and real pricing can be compared every week.
- Size: q = 0.5 x f x E / S per coin (E = paper equity at entry; default --equity 5000 --f 0.25; Bybit qty step 0.01 BTC / 0.1 ETH? read
  instruments-info lotSizeFilter and round DOWN; if 0, skip and log).
- Hourly (each run >= the next whole hour): mark both legs at Bybit MARK price; SL: if (premium received - fees - cost to close at the current
  ASK of both legs) <= -1.0 x premium received -> buy back both legs at the ASK + taker fee (log reason sl). TP at 4h closes (00/04/08/12/16/20
  UTC runs): if the cost to close at the ASK <= 0.3 x premium -> buy back at the ASK + fee (maker fee 0.02 % would need a resting order; log the
  taker version as the conservative fill and the mark-based maker version as a side field).
- Otherwise at expiry: settle at Bybit's delivery price (GET /v5/market/delivery-price?category=option&baseCoin=..., fallback index mean
  labelled); payoff -q x (|S_settle - K|) for the ITM leg + delivery fee min(0.00015 x S, 0.125 x intrinsic).
- Equity curve hourly (mark-to-market at mark prices), realised P&L per week, and a research-vs-real table per week (premium at bid vs BS @
  0.97 DVOL; mark IV vs DVOL).
- State `artifacts/bot/paper_straddle/state.json`, actions `artifacts/bot/paper_straddle/actions.jsonl`, rule sha256 printed at start like
  carry_paper.py; `--once`, `--equity`, `--f`, `--tag`, `--dry-run` (no state write), robust to API errors (retry, log, exit 0), idempotent per
  hour (never two entries the same week; restart-safe).

## Tests (tests/test_straddle_paper.py, mocked HTTP, no network)
Friday window logic (entry only 08:05-08:59, skip logged otherwise), nearest-strike tie rule, fill at bid / buy back at ask, fee caps, SL / TP
math on a synthetic path, settlement payoff, restart idempotence (no double entry), qty rounding. Then run once against the live API with
`--once --dry-run` and paste the output (today is not Friday -> it must only mark nothing and print "no entry window").
Doc (<= 30 lines): how the leader starts it (hourly loop command like the carry loop), files, fields.
