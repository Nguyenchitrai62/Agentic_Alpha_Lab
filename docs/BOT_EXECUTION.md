# BOT execution: order mirror for R2-4P (Bybit USDT perps)

`bot/` turns the merged multi-phase paper plan (`artifacts/research/advisor_shadow/trade_plan_v376.json`, refreshed hourly by the backend)
into exchange orders. Logic: `bot/mirror.py` (pure, tests in `tests/test_bot_mirror.py`); exchange client: `bot/bybit_v5.py`; loop: `bot/run.py`.

## Modes
- `python -m bot.run --once --equity 2000` - DRY RUN: prints the orders that should rest now (public market data only, sends nothing).
- `python -m bot.run --mode testnet` - Bybit TESTNET, every 20 s. Put `BYBIT_TESTNET_API_KEY` / `BYBIT_TESTNET_API_SECRET` in `.env`
  (testnet keys from testnet.bybit.com; never commit them).
- `python -m bot.run --mode paper --equity 5000` - PAPER: the same bot against a simulated account filled from LIVE Bybit 1m klines
  (`bot/paper.py`: trade-through limits, stop-first, taker market / stops, adverse long funding); prospective evidence for the whole bot
  stack without keys. Running since 2026-10-05 04:46 UTC (state `artifacts/bot/paper/exchange.json`, log `runner.log`; one runner per mode,
  OS lock `runner.lock`).
- `--mode live` is LOCKED: it needs `BYBIT_API_KEY` / `BYBIT_API_SECRET` in `.env` AND `BOT_ALLOW_LIVE=yes-real-money` set by the
  account owner. Start live only after a clean testnet run and with a small account.

## Rules implemented (same as the research engine)
- Hedge mode: longs positionIdx 1, shorts 2 (a sub-book short never nets against a long dip rung).
- Book entries: GTC limits (a crossing limit fills at once as taker) from minute 5 after the plan's issue time until `valid_until`; unfilled -> cancelled, never chased.
- Every filled piece gets its own reduce-only exits: book = conditional market stop at the plan SL + limit TP (amended when the plan moves
  SL/TP, e.g. break-even / tighten); plan add / reduce / close = limit orders.
- Dip rungs: limit bids from minute 16 to the bar end, admitted shallow-first inside each sub-book's risk budget (0.26 x sub capital,
  stop distance + 2 %), TP limit + 8-sigma native backstop on the exchange, 4-sigma stop on a CLOSED 5m bar close (bot market exit), time
  exit at the bar end (market).
- The exchange is the truth for open pieces: when the paper plan has exited a book position that is still open on the exchange, the bot
  closes it at market after 3 minutes (logged `plan_closed_divergence`).
- Safety: a plan older than 2 h blocks new entries (exits keep running); orders below Bybit lot / notional minimums are skipped and logged
  (at ~2000 USDT some BTC rungs are below 0.001 BTC; see the small-account study).

State: `artifacts/bot/<mode>/state.json`; every action: `artifacts/bot/<mode>/actions.jsonl`.
Known caveats: plan levels come from Binance prices (Bybit within ~2 bps, BNB ~10 bps cheaper on Bybit); the backend must run
for fresh plans; a new fill has no exit orders until the next cycle (<= 20 s) places its stop and TP.

## CHANGES (bot_bookgap: dust + in-flight double-spend, mirror-only, default behaviour)
- `mirror.apply_fill` clamps ULP-level remainders (<= 1e-9 of the piece size) to exactly 0, so a closed piece never
  refires market exits every 2 minutes (parity window: one 1.5e-12 XRP leftover alone caused 3,781 futile placements).
- `mirror.desired` emits no other order (TP/stop/reduce/add/entry-remainder) for a piece with a market exit in flight
  (`exit_sent` < 2 min old): the market exit and a resting TP could otherwise both fill for the full piece qty out of
  the shared (symbol, positionIdx) net, spending other pieces' balances and stranding victims in an exit-retry loop
  (parity window: 25,435 exit placements for 143 fills). Stale markers restore protection, so a failed exit never
  disarms a piece. NOTE: `tests/test_bot_resilience.py::test_1` and `::test_6` still assert the old behaviour
  (protection rests alongside a fresh market exit) and need updating to the fixed behaviour.

## CHANGES (v399/R2B1_130: correlation-aware dip sizing + risk multiplier, default off)
- `mirror.corr_mult(dips_of_phase, last_close, a) = 1/(1+n)`: n = other majors in the same phase whose last closed 1m
  close <= open_b*(1-2.5*sigma_b), with open/sigma from any rung row (`sigma=(1-stop/buy_limit)/4`,
  `open=buy_limit/(1-rung*sigma)`). `desired(..., risk_mult=1.0, corr=False, last_close=None)`: book entry/add qty x
  risk_mult; dip qty x risk_mult x corr_mult (when corr); budget `BUDGET x risk_mult` with UNSCALED-by-corr admission
  (shallow-first), so corr only shrinks size. Defaults keep every order identical.
- `run.py`: `--risk-mult` (default 1.0), `--corr-size` (default off), `--tag` (state dir
  `artifacts/bot/<mode>[_<tag>]`, default unchanged); paper passes the paper exchange `last_close`, other modes fetch
  the last closed 1m close per symbol (Bybit klines interval 1, limit 2, closed bar). Resting `entry` bids are amended
  on qty change ONLY when corr/risk options are on (`diff(..., amend_entry_qty=True)`; tp/stop amend as before).
- Bear-regime book filter (registry v410, R2B1D18BF; default off): `mirror.is_bear(opens)` is True while the latest
  BTCUSDT 4h bar OPEN < the mean of the last 1200 4h opens including it (min 600); `desired(..., bear_book=False,
  bear=False)` halves book ENTRY/ADD qty on the LONG side only when both flags are set (shorts, reduce/close/tp/stop,
  dips unchanged). `bybit_v5.Bybit.klines_4h_opens(symbol, n=1200)` pages the public kline endpoint (interval 240,
  limit 1000, `end` cursor) oldest-first; `run.py --bear-book` recomputes bear from BTCUSDT every 10 minutes (cached)
  and logs `op='bear_state'` on change.
- Closed gap (2026-10-05, bot_beartrim): `--bear-book` halves NEW book long entries / adds in the bear regime; the research engine (v410) halves the book
  long TARGET; the bot now also trims each open book long once per bear episode to half its plan size with one reduce-only limit.
- Dip stop-cascade controls (registry v417 rows C/X, default off): `run.py --dip-cooldown-h H` (default 0) records each dip
  stop-out (bot close5 market exit or native backstop fill; TP / time exits never) as `stop_exit_t` on its piece via
  `mirror.note_dip_stop`, and `desired(..., dip_cooldown_h)` places no NEW dip rung of the same coin+phase whose bar open B
  satisfies s < B <= s+H (open pieces keep TP/backstop; same-bar B <= s unaffected). `--dip-sl-coin SYM=M` (repeatable)
  replaces the 4-sigma dip close-stop for that coin (`mirror.dip_stop_price`, budget `frac*(M*sigma+GAP)`; backstop 8 sigma
  unchanged). Defaults reproduce every old order bit-for-bit.
- Dip gross-notional cap (research v421 G2 / v422 engine hook `sleeve_gross_cap`, default off): `run.py --dip-gross-cap G`
  (default 0 = off) keeps, per phase sub-book, open filled dip notional + resting dip entry bids <= G x sub equity
  (sub equity = equity x the phase cap used by the budget rule). The room (G x sub equity - open dip notional of that
  phase) is allocated to the resting bids in admission order (shallow rung first, then phase, then symbol); the last
  admitted bid is cut to the remaining room and the rest are dropped, recomputed every cycle (resting bids amend qty
  down/up, never chase price). Book orders and protection (tp/stop/reduce) are never touched.

## Failure modes (tests/test_bot_resilience.py, fake exchange, no network)
- Restart mid-position: new Runner adopts state.json + exchange stops/TPs, no duplicate entries, filled rungs never re-placed.
- Partial dip fill: TP/stop size to the filled qty, remainder stays resting (same link), budget counts only the filled part.
- Stop placement errors: retried next cycle; unprotected > 2 cycles -> market reduce-only close, logged `op=unprotected_close`.
- Rejected orders (lot/min-notional): `to_exchange` returns None, logged `skipped_below_minimum`, at most one attempt per cycle per link.
- Late cycle (20 min): time exits fire on `now >= t_exit`, stale-plan still blocks entries, entries never wanted inside the first 5 min.
- Missing/corrupt plan: logged `op=plan_error`, no crash, cached plan keeps protection with no new entries (no cache: ledger-only TP/stop).
- Duplicate fills: `sync_fills` applies each execId once (`seen_exec`); fixed `last_exec_ms=0` falsy-start bug.
